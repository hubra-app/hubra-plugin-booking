"""Booking API: /api/v1/app/booking.

GET    /options                       what the caller may do, categories
GET    /resources?all=1               bookable resources (all: also inactive)
POST   /resources                     {name, kind, description?, location?, color?,
                                       inventoryItemId?, needsApproval?, feeFlat?,
                                       feePerHour?, categoryId?, maxHours?, advanceDays?}
                                      With Inventory running, equipment is an
                                      inventory item (name and place come from it)
PATCH  /resources/<id>                same fields, plus active, position
DELETE /resources/<id>                only without bookings; else switch it off
GET    /inventory-items               items of the Inventory plugin to pick from
GET    /bookings?from=&to=&resourceId= the calendar: pending and confirmed slots
GET    /bookings/mine                 the caller's bookings, upcoming and recent
GET    /bookings/pending              waiting for approval (approvers)
POST   /bookings                      {resourceId, startsAt, endsAt, title?, note?,
                                       memberId? and repeatWeeks? (approvers)}
POST   /bookings/<id>/decide          {approve, note?}
POST   /bookings/<id>/cancel          {series?}: own before it starts, or approvers
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from hubra.core.auth.helpers import get_current_member
from hubra.core.contracts import (
    SYSTEM,
    ActionFailed,
    ActionUnavailable,
    available,
)
from hubra.core.contracts import query as contract_query
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.finance import Invoice, TransactionCategory
from hubra.core.models.member import Member
from hubra.core.permissions import permission_required, require_member
from hubra.core.utils import log_audit

from .body import (
    Invalid,
    _body,
    _bool,
    _can,
    _category_id,
    _get,
    _int,
    _iso,
    _money,
    _names,
    _num,
    _text,
)
from .models import Booking, BookingResource
from .notify import notify

booking_bp = Blueprint("booking_bp", __name__)

RESOURCES = "booking.resources.update"
BOOKINGS = "booking.bookings.update"
KINDS = ("room", "equipment")
LIVE = ("pending", "approved")
# How far ahead members may book when a resource sets nothing.
DEFAULT_ADVANCE = 180
# Longest calendar range one request may read.
MAX_RANGE = timedelta(days=62)


@booking_bp.errorhandler(Invalid)
def _invalid(exc: Invalid):
    return api_error("VALIDATION_ERROR", exc.message, 400)


# ── Time ─────────────────────────────────────────────────────────────────────


def _zone() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config.get("MAIL_TIMEZONE") or "Europe/Zurich")
    except Exception:  # noqa: BLE001 - a bad setting falls back
        return ZoneInfo("Europe/Zurich")


def _local_now() -> datetime:
    return datetime.now(_zone()).replace(tzinfo=None, microsecond=0)


def _when(value, key: str) -> datetime:
    """A wall-clock time: "2026-11-05T18:00". A time with a zone is turned
    into the club's time."""
    if not value or not isinstance(value, str):
        raise Invalid(f"{key} is required")
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"{key} must be a time (YYYY-MM-DDTHH:MM)") from None
    if moment.tzinfo is not None:
        moment = moment.astimezone(_zone()).replace(tzinfo=None)
    return moment.replace(second=0, microsecond=0)


def _day_label(moment: datetime) -> str:
    return moment.strftime("%d.%m.%Y %H:%M")


# ── Output ───────────────────────────────────────────────────────────────────


# Inventory items come through the Inventory plugin's contracts
# (docs/contracts.md in hubra-app/hubra), never its tables.
_GET_ITEMS = "inventory.items.get"
_LIST_ITEMS = "inventory.items.list"


def _inventory_available() -> bool:
    return available(_GET_ITEMS)


def _inventory_items(ids) -> dict[int, dict]:
    """The Inventory items with these ids that still exist, by id."""
    ids = sorted({i for i in ids if i})
    if not ids or not _inventory_available():
        return {}
    try:
        items = contract_query(_GET_ITEMS, ids=ids[:500], actor=SYSTEM)
    except (ActionUnavailable, ActionFailed):
        return {}
    return {item["id"]: dict(item) for item in items}


# Inventory statuses in which a linked item can't be booked.
_OUT_OF_USE = ("maintenance", "broken", "lost", "retired", "archived")


def _name(r: BookingResource, items: dict[int, dict]) -> str:
    """A linked item's own name; the copy kept here when it is unreachable."""
    item = items.get(r.inventory_item_id or 0)
    return item["name"] if item else r.name


def _resource(r: BookingResource, items: dict[int, dict]) -> dict:
    item = items.get(r.inventory_item_id or 0)
    return {
        "id": r.id,
        "name": _name(r, items),
        "kind": r.kind,
        "description": r.description,
        "location": (item.get("location") if item else None) or r.location,
        "color": r.color,
        "inventoryItemId": r.inventory_item_id,
        "inventoryItemName": item["name"] if item else None,
        "inventoryItemStatus": item.get("status") if item else None,
        "needsApproval": r.needs_approval,
        "feeFlat": _num(r.fee_flat),
        "feePerHour": _num(r.fee_per_hour),
        "categoryId": r.category_id,
        "maxHours": r.max_hours,
        "advanceDays": r.advance_days,
        "active": r.active,
        "position": r.position,
    }


def _booking(
    b: Booking, resources: dict, items: dict, names: dict, viewer, manager: bool
) -> dict:
    mine = viewer is not None and b.member_id == viewer.id
    r = resources.get(b.resource_id)
    out = {
        "id": b.id,
        "resourceId": b.resource_id,
        "resourceName": _name(r, items) if r else None,
        "memberId": b.member_id,
        "memberName": names.get(b.member_id or 0),
        "title": b.title,
        "startsAt": b.starts_at.isoformat(timespec="minutes"),
        "endsAt": b.ends_at.isoformat(timespec="minutes"),
        "status": b.status,
        "seriesId": b.series_id,
        "mine": mine,
    }
    if mine or manager:
        out.update(
            {
                "note": b.note,
                "fee": _num(b.fee),
                "invoiceId": b.invoice_id,
                "decisionNote": b.decision_note,
                "decidedAt": _iso(b.decided_at),
            }
        )
    return out


def _bookings(rows, viewer, manager: bool) -> list[dict]:
    rows = list(rows)
    resources = {
        r.id: r
        for r in db.session.scalars(
            select(BookingResource).where(
                BookingResource.id.in_({b.resource_id for b in rows} or {0})
            )
        )
    }
    items = _inventory_items(r.inventory_item_id for r in resources.values())
    names = _names(b.member_id for b in rows)
    return [_booking(b, resources, items, names, viewer, manager) for b in rows]


# ── Options ──────────────────────────────────────────────────────────────────


@booking_bp.get("/options")
@require_member
def options():
    member = get_current_member()
    can = {"resources": _can(member, RESOURCES), "bookings": _can(member, BOOKINGS)}
    out = {"can": can, "memberId": member.id}
    if can["resources"]:
        out["categories"] = [
            {"id": c.id, "name": c.name}
            for c in db.session.scalars(
                select(TransactionCategory).order_by(TransactionCategory.name)
            )
        ]
        out["inventory"] = _inventory_available()
    if can["bookings"]:
        out["pending"] = (
            db.session.scalar(
                select(db.func.count())
                .select_from(Booking)
                .where(Booking.status == "pending")
                .where(Booking.ends_at >= _local_now())
            )
            or 0
        )
    return jsonify(out)


# ── Resources ────────────────────────────────────────────────────────────────


def _resource_fields(r: BookingResource, data: dict, creating: bool) -> None:
    if creating or "kind" in data:
        kind = data.get("kind") or "room"
        if kind not in KINDS:
            raise Invalid("kind must be room or equipment")
        r.kind = kind
    item = None
    if creating or "inventoryItemId" in data:
        item_id = _int(data, "inventoryItemId", 1, 2**31 - 1)
        if item_id is not None:
            item = _inventory_items([item_id]).get(item_id)
            if item is None:
                raise Invalid("inventoryItemId: no such inventory item")
            taken = db.session.scalar(
                select(BookingResource.id)
                .where(BookingResource.inventory_item_id == item_id)
                .where(BookingResource.id != (r.id or 0))
                .limit(1)
            )
            if taken is not None:
                raise Invalid("inventoryItemId: this item is already a resource")
        r.inventory_item_id = item_id
    elif r.inventory_item_id:
        item = _inventory_items([r.inventory_item_id]).get(r.inventory_item_id)
    # Equipment is what the club owns, so with Inventory running it is an
    # inventory item, not a second list of things. Rooms may be either.
    if r.kind == "equipment" and not r.inventory_item_id and _inventory_available():
        raise Invalid("inventoryItemId: pick the equipment from the inventory")
    for key, attr, limit in (
        ("description", "description", 5000),
        ("location", "location", 200),
        ("color", "color", 20),
    ):
        if creating or key in data:
            setattr(r, attr, _text(data, key, limit))
    if item is not None:
        # Name and place follow the item; the copy kept here is the fallback
        # for when Inventory is off.
        r.name = item["name"][:120]
        if item.get("location"):
            r.location = item["location"][:200]
    elif creating or "name" in data:
        r.name = _text(data, "name", 120, required=True)
    if creating or "needsApproval" in data:
        r.needs_approval = _bool(data, "needsApproval")
    if creating or "feeFlat" in data:
        r.fee_flat = _money(data, "feeFlat")
    if creating or "feePerHour" in data:
        r.fee_per_hour = _money(data, "feePerHour")
    if creating or "categoryId" in data:
        r.category_id = _category_id(data)
    if creating or "maxHours" in data:
        r.max_hours = _int(data, "maxHours", 1, 24 * 31)
    if creating or "advanceDays" in data:
        r.advance_days = _int(data, "advanceDays", 1, 3650)
    if "active" in data:
        r.active = _bool(data, "active")
    if "position" in data:
        r.position = _int(data, "position", 0, 10000, 0)


@booking_bp.get("/resources")
@require_member
def list_resources():
    member = get_current_member()
    query = select(BookingResource).order_by(
        BookingResource.position, BookingResource.id
    )
    if not (request.args.get("all") and _can(member, RESOURCES)):
        query = query.where(BookingResource.active.is_(True))
    rows = list(db.session.scalars(query))
    items = _inventory_items(r.inventory_item_id for r in rows)
    return jsonify([_resource(r, items) for r in rows])


@booking_bp.post("/resources")
@permission_required("resources", "update", "Add and change bookable resources")
def create_resource():
    member = get_current_member()
    data = _body()
    r = BookingResource(active=True, position=0)
    _resource_fields(r, data, creating=True)
    db.session.add(r)
    db.session.flush()
    log_audit(member.id, "booking.resource.create", "BookingResource", r.id, r.name)
    db.session.commit()
    return jsonify(_resource(r, _inventory_items([r.inventory_item_id]))), 201


@booking_bp.patch("/resources/<int:resource_id>")
@permission_required("resources", "update", "Add and change bookable resources")
def update_resource(resource_id: int):
    member = get_current_member()
    r, err = _get(BookingResource, resource_id)
    if err:
        return err
    _resource_fields(r, _body(), creating=False)
    log_audit(member.id, "booking.resource.update", "BookingResource", r.id, r.name)
    db.session.commit()
    return jsonify(_resource(r, _inventory_items([r.inventory_item_id])))


@booking_bp.delete("/resources/<int:resource_id>")
@permission_required("resources", "update", "Add and change bookable resources")
def delete_resource(resource_id: int):
    member = get_current_member()
    r, err = _get(BookingResource, resource_id)
    if err:
        return err
    used = db.session.scalar(
        select(Booking.id).where(Booking.resource_id == r.id).limit(1)
    )
    if used is not None:
        return api_error(
            "RESOURCE_IN_USE", "it has bookings; switch it off instead", 409
        )
    log_audit(member.id, "booking.resource.delete", "BookingResource", r.id, r.name)
    db.session.delete(r)
    db.session.commit()
    return "", 204


@booking_bp.get("/inventory-items")
@permission_required("resources", "update", "Add and change bookable resources")
def inventory_items():
    """Inventory items to pick a resource from; ``resourceId`` marks the ones
    that already are one."""
    if not available(_LIST_ITEMS):
        return jsonify([])
    try:
        items = contract_query(
            _LIST_ITEMS,
            search=request.args.get("search") or None,
            limit=500,
            actor=SYSTEM,
        )
    except (ActionUnavailable, ActionFailed):
        return jsonify([])
    linked = dict(
        db.session.execute(
            select(BookingResource.inventory_item_id, BookingResource.id).where(
                BookingResource.inventory_item_id.is_not(None)
            )
        ).all()
    )
    return jsonify(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "location": i.get("location"),
                "category": i.get("category"),
                "status": i.get("status"),
                "resourceId": linked.get(i["id"]),
            }
            for i in items
        ]
    )


# ── Bookings ─────────────────────────────────────────────────────────────────


@booking_bp.get("/bookings")
@require_member
def calendar():
    member = get_current_member()
    today = _local_now().date()
    try:
        start = date.fromisoformat(request.args.get("from") or today.isoformat())
        end = date.fromisoformat(
            request.args.get("to") or (start + timedelta(days=7)).isoformat()
        )
    except ValueError:
        raise Invalid("from and to must be dates (YYYY-MM-DD)") from None
    if end <= start or end - start > MAX_RANGE:
        raise Invalid("to must be after from, at most 62 days")
    query = (
        select(Booking)
        .where(Booking.status.in_(LIVE))
        .where(Booking.starts_at < datetime.combine(end, datetime.min.time()))
        .where(Booking.ends_at > datetime.combine(start, datetime.min.time()))
        .order_by(Booking.starts_at)
    )
    resource = request.args.get("resourceId", type=int)
    if resource:
        query = query.where(Booking.resource_id == resource)
    return jsonify(_bookings(db.session.scalars(query), member, _can(member, BOOKINGS)))


@booking_bp.get("/bookings/mine")
@require_member
def my_bookings():
    member = get_current_member()
    since = _local_now() - timedelta(days=30)
    rows = db.session.scalars(
        select(Booking)
        .where(Booking.member_id == member.id)
        .where(Booking.ends_at >= since)
        .order_by(Booking.starts_at)
        .limit(500)
    )
    return jsonify(_bookings(rows, member, _can(member, BOOKINGS)))


@booking_bp.get("/bookings/pending")
@permission_required("bookings", "update", "Approve and manage bookings")
def pending_bookings():
    member = get_current_member()
    rows = db.session.scalars(
        select(Booking)
        .where(Booking.status == "pending")
        .where(Booking.ends_at >= _local_now())
        .order_by(Booking.starts_at)
        .limit(500)
    )
    return jsonify(_bookings(rows, member, True))


def _fee(r: BookingResource, start: datetime, end: datetime) -> Decimal | None:
    total = Decimal("0")
    if r.fee_flat:
        total += r.fee_flat
    if r.fee_per_hour:
        hours = Decimal((end - start).total_seconds()) / Decimal(3600)
        total += r.fee_per_hour * hours
    total = total.quantize(Decimal("0.01"))
    return total if total > 0 else None


def _clash(resource_id: int, start: datetime, end: datetime, skip=None):
    query = (
        select(Booking)
        .where(Booking.resource_id == resource_id)
        .where(Booking.status.in_(LIVE))
        .where(Booking.starts_at < end)
        .where(Booking.ends_at > start)
    )
    if skip is not None:
        query = query.where(Booking.id != skip)
    return db.session.scalars(query.limit(1)).first()


def _bill(b: Booking, r: BookingResource, actor_id: int) -> None:
    """Puts the fee on the member's invoice once the booking is confirmed."""
    if not b.fee or not b.member_id or b.invoice_id:
        return
    from hubra.core.contracts import SYSTEM, call

    today = _local_now().date()
    # As the booking itself: whoever confirms it needn't hold invoice rights.
    invoice = call(
        "finance.invoice.create",
        member_id=b.member_id,
        issued=today,
        due=max(today + timedelta(days=30), b.starts_at.date()),
        amount=b.fee,
        purpose="other",
        description=f"Buchung {r.name}: {_day_label(b.starts_at)}"[:512],
        category_id=r.category_id,
        actor_id=actor_id,
        actor=SYSTEM,
    )
    b.invoice_id = invoice["id"]


def _unbill(b: Booking, actor_id: int) -> None:
    """Withdraws an unpaid fee invoice; a paid one stays for the books."""
    if not b.invoice_id:
        return
    invoice = db.session.get(Invoice, b.invoice_id)
    if invoice is None or invoice.status == "Paid":
        return
    from hubra.core.contracts import SYSTEM, call

    b.invoice_id = None
    db.session.flush()
    call(
        "finance.invoice.delete", invoice_id=invoice.id, actor_id=actor_id, actor=SYSTEM
    )


def _approvers() -> list[int]:
    from hubra.core.permissions import member_has_permission

    members = db.session.scalars(
        select(Member)
        .where(Member.status == "active")
        .where(Member.archived_at.is_(None))
    )
    return [m.id for m in members if member_has_permission(m, BOOKINGS)]


@booking_bp.post("/bookings")
@require_member
def create_booking():
    member = get_current_member()
    manager = _can(member, BOOKINGS)
    data = _body()
    resource_id = _int(data, "resourceId", 1, 2**31 - 1)
    if resource_id is None:
        raise Invalid("resourceId is required")
    # Lock the resource so two people can't take the same slot at once.
    r = db.session.scalar(
        select(BookingResource)
        .where(BookingResource.id == resource_id)
        .with_for_update()
    )
    if r is None or (not r.active and not manager):
        return api_error("NOT_FOUND", "no such resource", 404)
    if r.inventory_item_id and _inventory_available():
        item = _inventory_items([r.inventory_item_id]).get(r.inventory_item_id)
        if item is None or item.get("status") in _OUT_OF_USE:
            return api_error(
                "RESOURCE_OUT_OF_USE",
                f"{r.name} is out of use in the inventory right now",
                409,
            )
    start = _when(data.get("startsAt"), "startsAt")
    end = _when(data.get("endsAt"), "endsAt")
    if end <= start:
        raise Invalid("endsAt must be after startsAt")
    if end - start > timedelta(days=31):
        raise Invalid("a booking is at most 31 days long")
    for_id = member.id
    weeks = 0
    if manager:
        for_id = _int(data, "memberId", 1, 2**31 - 1, member.id)
        if db.session.get(Member, for_id) is None:
            raise Invalid("memberId: no such member")
        weeks = _int(data, "repeatWeeks", 0, 52, 0)
    else:
        if "memberId" in data and data.get("memberId") not in (None, member.id):
            return api_error("FORBIDDEN", "you can only book for yourself", 403)
        now = _local_now()
        if start < now - timedelta(minutes=5):
            raise Invalid("startsAt is in the past")
        if r.max_hours and end - start > timedelta(hours=r.max_hours):
            raise Invalid(f"at most {r.max_hours} hours at a time")
        ahead = r.advance_days or DEFAULT_ADVANCE
        if start.date() > now.date() + timedelta(days=ahead):
            raise Invalid(f"at most {ahead} days ahead")
    title = _text(data, "title", 200)
    note = _text(data, "note", 500)
    series = str(uuid.uuid4()) if weeks else None
    status = "pending" if r.needs_approval and not manager else "approved"
    made: list[Booking] = []
    for week in range(weeks + 1):
        s, e = start + timedelta(weeks=week), end + timedelta(weeks=week)
        clash = _clash(r.id, s, e)
        if clash is not None:
            db.session.rollback()
            return api_error(
                "BOOKING_CONFLICT",
                f"{r.name} is taken from {_day_label(clash.starts_at)} "
                f"to {_day_label(clash.ends_at)}",
                409,
            )
        b = Booking(
            resource_id=r.id,
            member_id=for_id,
            title=title,
            note=note,
            starts_at=s,
            ends_at=e,
            status=status,
            series_id=series,
            fee=_fee(r, s, e),
            created_by=member.id,
        )
        if status == "approved" and manager:
            b.decided_by, b.decided_at = member.id, datetime.now(timezone.utc)
        db.session.add(b)
        db.session.flush()
        if status == "approved":
            _bill(b, r, member.id)
        made.append(b)
    log_audit(
        member.id,
        "booking.create",
        "Booking",
        made[0].id,
        f"{r.name} {_day_label(start)} x{len(made)}",
    )
    if status == "pending":
        who = member.name
        notify(
            [m for m in _approvers() if m != member.id],
            lambda de: (
                ("Buchung wartet auf Freigabe", f"{who}: {r.name}, {_day_label(start)}")
                if de
                else (
                    "Booking awaits approval",
                    f"{who}: {r.name}, {_day_label(start)}",
                )
            ),
            "/app/booking/requests",
        )
    elif for_id != member.id:
        notify(
            [for_id],
            lambda de: (
                ("Für dich gebucht", f"{r.name}, {_day_label(start)}")
                if de
                else ("Booked for you", f"{r.name}, {_day_label(start)}")
            ),
            "/app/booking/mine",
        )
    db.session.commit()
    out = _bookings(made, member, manager)
    return jsonify(out[0] if len(out) == 1 else out), 201


@booking_bp.post("/bookings/<int:booking_id>/decide")
@permission_required("bookings", "update", "Approve and manage bookings")
def decide(booking_id: int):
    member = get_current_member()
    b, err = _get(Booking, booking_id)
    if err:
        return err
    if b.status != "pending":
        return api_error("NOT_PENDING", "this booking was already decided", 409)
    data = _body()
    approve = _bool(data, "approve")
    r = db.session.get(BookingResource, b.resource_id)
    b.status = "approved" if approve else "rejected"
    b.decided_by, b.decided_at = member.id, datetime.now(timezone.utc)
    b.decision_note = _text(data, "note", 500)
    if approve:
        _bill(b, r, member.id)
    label = f"{r.name}, {_day_label(b.starts_at)}"
    notify(
        [b.member_id],
        lambda de: (
            ("Buchung bestätigt" if approve else "Buchung abgelehnt", label)
            if de
            else ("Booking confirmed" if approve else "Booking declined", label)
        ),
        "/app/booking/mine",
    )
    log_audit(member.id, f"booking.{b.status}", "Booking", b.id, label)
    db.session.commit()
    return jsonify(_bookings([b], member, True)[0])


@booking_bp.post("/bookings/<int:booking_id>/cancel")
@require_member
def cancel(booking_id: int):
    member = get_current_member()
    manager = _can(member, BOOKINGS)
    b, err = _get(Booking, booking_id)
    if err:
        return err
    if not manager and b.member_id != member.id:
        return api_error("FORBIDDEN", "not your booking", 403)
    rows = [b]
    if b.series_id and _bool(_body(), "series"):
        rows = list(
            db.session.scalars(
                select(Booking)
                .where(Booking.series_id == b.series_id)
                .where(Booking.starts_at >= b.starts_at)
            )
        )
    now = _local_now()
    rows = [x for x in rows if x.status in LIVE]
    if not rows:
        return api_error("NOT_LIVE", "this booking is no longer active", 409)
    for x in rows:
        if not manager:
            if x.starts_at <= now:
                return api_error("BOOKING_STARTED", "it has already started", 409)
            invoice = db.session.get(Invoice, x.invoice_id) if x.invoice_id else None
            if invoice is not None and invoice.status == "Paid":
                return api_error(
                    "BOOKING_PAID", "it is paid; ask the board to cancel it", 409
                )
        _unbill(x, member.id)
        x.status = "cancelled"
    r = db.session.get(BookingResource, b.resource_id)
    if b.member_id and b.member_id != member.id:
        label = f"{r.name}, {_day_label(b.starts_at)}"
        notify(
            [b.member_id],
            lambda de: (
                ("Buchung storniert", label) if de else ("Booking cancelled", label)
            ),
            "/app/booking/mine",
        )
    log_audit(member.id, "booking.cancel", "Booking", b.id, f"{r.name} x{len(rows)}")
    db.session.commit()
    return jsonify({"cancelled": [x.id for x in rows]})
