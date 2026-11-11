"""Vor Ort: members say on which days they'll be in a room.

Not a booking: nothing is held and any number of members can be there. It
lets members plan around each other ("who's in the workshop on Thursday?")
and go on the same days.

GET    /onsite?from=&to=     the rooms, everyone's entries, the room's bookings
                             (busy) and the rooms the caller watches
PUT    /onsite               {resourceId, day, status: going|maybe|here,
                              from?, to?, keyHolder?, comment?, joinable?,
                              joinsId?, repeatUntil?}: the caller's entry for
                             that room and day (made or changed). repeatUntil:
                             the same every week up to that day (a series).
                             joinsId: join another member's entry that day
                             ("Mitmachen"); they hear it.
DELETE /onsite/<id>?following=1
                             own entry (following: and the series' later
                             ones); booking.bookings.update: anyone's
POST   /onsite/<id>/leave    own entry today: checked out ("Ich gehe")
GET    /onsite/feed          the caller's calendar feed URL (own days and
                             days in watched rooms), made on first use
POST   /onsite/feed/renew    a new feed URL; the old one stops working
GET    /onsite/feed/<club>/<token>.ics
                             the feed itself, without signing in
GET    /onsite/stats?months= booking.resources.update or .bookings.update:
                             per room and month the days with someone, the
                             visits and the people; visits per weekday
PUT    /onsite/watch         {resourceId, watching}: hear when someone plans
                             to be in that room
POST   /onsite/checkin       {token}: the room's QR code was scanned: the
                             caller is there today ("Bin da")
GET    /onsite/qr/<id>       booking.resources.update: the room's QR code
                             ({url, svg}), made on first use
POST   /onsite/qr/<id>/renew booking.resources.update: a new code; printed
                             old ones stop working

The jobs (``tasks.onsite_hourly``): the evening before, everyone who said
Komme or Vielleicht gets a reminder (bell, Discord DM, mail) with who else
comes and who brings the key; on a room's day with people coming but no
key, the members who brought its key lately are asked; in the morning the day's list goes out as the
event ``booking.onsite.today`` (the Discord plugin posts it); entries older
than the club keeps them (at least a year) are deleted.
"""

from __future__ import annotations

import re
import secrets
from datetime import date, datetime, time, timedelta, timezone

from flask import jsonify, request
from sqlalchemy import delete, select

from hubra.core.auth.helpers import get_current_member
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.member import Member
from hubra.core.permissions import require_member

from .body import Invalid, _body, _can, _date, _int, _names, _text
from .models import (
    Booking,
    BookingResource,
    OnsiteDay,
    OnsiteEntry,
    OnsiteFeed,
    OnsitePing,
    OnsiteWatch,
)

RESOURCES = "booking.resources.update"
STATUSES = ("going", "maybe", "here")
REMINDED = ("going", "maybe")
# How far ahead a member can plan, and the longest range one request reads.
AHEAD = timedelta(days=366)
MAX_RANGE = timedelta(days=62)
# Settings (Einstellungen › Module › Booking) and their defaults.
KEEP_MIN = 365
DEFAULTS = {
    "onsite_keep_days": KEEP_MIN,
    "onsite_reminder_hour": 18,
    "onsite_today_hour": 7,
}
TODAY_EVENT = "booking.onsite.today"
# A series runs at most a year (weekly).
SERIES_MAX = 53
# Who "brought the key lately": key holder in the room within these days.
KEY_LOOKBACK = timedelta(days=180)
STATS = "booking.bookings.update"
LINK = "/app/booking/onsite"


def setting(key: str) -> int:
    from hubra.core.modules import get_config

    value = get_config("booking").get(key)
    if value is None or value == "":
        return DEFAULTS[key]
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULTS[key]
    if key == "onsite_keep_days":
        return max(value, KEEP_MIN)
    return min(max(value, 0), 23)


def _local_now() -> datetime:
    from .routes import _local_now as now

    return now()


def _rooms(ids=None) -> list[BookingResource]:
    query = (
        select(BookingResource)
        .where(BookingResource.kind == "room")
        .where(BookingResource.active.is_(True))
        .order_by(BookingResource.position, BookingResource.id)
    )
    if ids is not None:
        query = query.where(BookingResource.id.in_(ids or {0}))
    return list(db.session.scalars(query))


def _hhmm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _clock(data: dict, key: str) -> time | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise Invalid(f"{key} must be a time (HH:MM)")
    try:
        return time.fromisoformat(value.strip()[:5]).replace(second=0)
    except ValueError:
        raise Invalid(f"{key} must be a time (HH:MM)") from None


def _entry(e: OnsiteEntry, names: dict[int, str], viewer_id: int) -> dict:
    return {
        "id": e.id,
        "resourceId": e.resource_id,
        "day": e.day.isoformat(),
        "from": _hhmm(e.starts),
        "to": _hhmm(e.ends),
        "status": e.status,
        "keyHolder": e.key_holder,
        "comment": e.comment,
        "memberId": e.member_id,
        "memberName": names.get(e.member_id),
        "mine": e.member_id == viewer_id,
        "series": e.series,
        "leftAt": e.left_at.isoformat(timespec="minutes") if e.left_at else None,
        "joinable": e.joinable,
        "joinsId": e.joins_id,
    }


def _range() -> tuple[date, date]:
    today = _local_now().date()
    start = _date(request.args, "from") or today - timedelta(days=today.weekday())
    end = _date(request.args, "to") or start + timedelta(days=7)
    if end <= start:
        raise Invalid("to must be after from")
    if end - start > MAX_RANGE:
        raise Invalid("at most 62 days at once")
    return start, end


def _upsert(
    member_id: int, resource_id: int, day: date, fields: dict
) -> tuple[OnsiteEntry, bool]:
    """The member's entry for a room and day, made or changed to *fields*."""
    entry = db.session.scalar(
        select(OnsiteEntry)
        .where(OnsiteEntry.resource_id == resource_id)
        .where(OnsiteEntry.member_id == member_id)
        .where(OnsiteEntry.day == day)
    )
    created = entry is None
    if created:
        entry = OnsiteEntry(resource_id=resource_id, member_id=member_id, day=day)
        db.session.add(entry)
    elif entry.starts != fields["starts"]:
        entry.reminded_at = None
    for key, value in fields.items():
        setattr(entry, key, value)
    if entry.status != "here":
        entry.left_at = None
    return entry, created


def register(bp) -> None:
    """Add the Vor Ort routes to the Booking blueprint."""

    @bp.get("/onsite")
    @require_member
    def onsite_list():
        member = get_current_member()
        start, end = _range()
        rooms = _rooms()
        room_ids = [r.id for r in rooms]
        entries = list(
            db.session.scalars(
                select(OnsiteEntry)
                .where(OnsiteEntry.resource_id.in_(room_ids or [0]))
                .where(OnsiteEntry.day >= start, OnsiteEntry.day < end)
                .order_by(OnsiteEntry.day, OnsiteEntry.starts, OnsiteEntry.id)
            )
        )
        names = _names(e.member_id for e in entries)
        # Exclusive bookings of the rooms: the room is taken then.
        busy = db.session.scalars(
            select(Booking)
            .where(Booking.resource_id.in_(room_ids or [0]))
            .where(Booking.status.in_(("pending", "approved")))
            .where(Booking.starts_at < datetime.combine(end, time()))
            .where(Booking.ends_at > datetime.combine(start, time()))
            .order_by(Booking.starts_at)
        )
        watching = db.session.scalars(
            select(OnsiteWatch.resource_id).where(OnsiteWatch.member_id == member.id)
        ).all()
        return jsonify(
            {
                "today": _local_now().date().isoformat(),
                "rooms": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "location": r.location,
                        "color": r.color,
                    }
                    for r in rooms
                ],
                "entries": [_entry(e, names, member.id) for e in entries],
                "busy": [
                    {
                        "resourceId": b.resource_id,
                        "startsAt": b.starts_at.isoformat(timespec="minutes"),
                        "endsAt": b.ends_at.isoformat(timespec="minutes"),
                        "title": b.title,
                        "pending": b.status == "pending",
                    }
                    for b in busy
                ],
                "watching": sorted(watching),
            }
        )

    @bp.put("/onsite")
    @require_member
    def onsite_set():
        member = get_current_member()
        data = _body()
        resource_id = _int(data, "resourceId", 1, 2**31 - 1)
        if resource_id is None or not _rooms([resource_id]):
            raise Invalid("resourceId: no such room")
        day = _date(data, "day", required=True)
        today = _local_now().date()
        if day < today:
            raise Invalid("day is in the past")
        if day > today + AHEAD:
            raise Invalid("day is more than a year ahead")
        status = data.get("status") or "going"
        if status not in STATUSES:
            raise Invalid("status must be going, maybe or here")
        if status == "here" and day != today:
            raise Invalid("here is only for today")
        starts, ends = _clock(data, "from"), _clock(data, "to")
        if starts and ends and ends <= starts:
            raise Invalid("to must be after from")
        until = _date(data, "repeatUntil")
        days = [day]
        if until is not None:
            if status == "here":
                raise Invalid("here can't repeat")
            if until > today + AHEAD:
                raise Invalid("repeatUntil is more than a year ahead")
            while days[-1] + timedelta(days=7) <= until and len(days) < SERIES_MAX:
                days.append(days[-1] + timedelta(days=7))
        host = None
        joins_id = _int(data, "joinsId", 1, 2**31 - 1)
        if joins_id is not None:
            host = db.session.get(OnsiteEntry, joins_id)
            if (
                host is None
                or host.resource_id != resource_id
                or host.day != day
                or host.member_id == member.id
                or not host.joinable
            ):
                raise Invalid("joinsId: nothing to join that day")
            if until is not None:
                raise Invalid("joining can't repeat")
        series = secrets.token_urlsafe(16)[:22] if len(days) > 1 else None
        fields = {
            "status": status,
            "starts": starts,
            "ends": ends,
            "key_holder": bool(data.get("keyHolder")),
            "comment": _text(data, "comment", 300),
            "joinable": bool(data.get("joinable")) and host is None,
        }
        first, created_first = None, False
        for d in days:
            entry, created = _upsert(member.id, resource_id, d, fields)
            if series:
                entry.series = series
            elif d == day and "joinsId" in data:
                entry.joins_id = host.id if host else None
            if first is None:
                first, created_first = entry, created
        db.session.flush()
        if created_first:
            tell_watchers(first, member, until=days[-1] if series else None)
        if host is not None:
            tell_host(host, first, member)
        db.session.commit()
        out = _entry(first, {member.id: member.name}, member.id)
        out["made"] = len(days)
        return jsonify(out), 201 if created_first else 200

    @bp.delete("/onsite/<int:entry_id>")
    @require_member
    def onsite_delete(entry_id: int):
        member = get_current_member()
        entry = db.session.get(OnsiteEntry, entry_id)
        if entry is None:
            return api_error("NOT_FOUND", "not found", 404)
        if entry.member_id != member.id and not _can(member, "booking.bookings.update"):
            return api_error("FORBIDDEN", "only your own entries", 403)
        if entry.series and request.args.get("following") in ("1", "true"):
            db.session.execute(
                delete(OnsiteEntry)
                .where(OnsiteEntry.series == entry.series)
                .where(OnsiteEntry.member_id == entry.member_id)
                .where(OnsiteEntry.day >= entry.day)
            )
        else:
            db.session.delete(entry)
        db.session.commit()
        return "", 204

    @bp.post("/onsite/<int:entry_id>/leave")
    @require_member
    def onsite_leave(entry_id: int):
        member = get_current_member()
        entry = db.session.get(OnsiteEntry, entry_id)
        if entry is None or entry.member_id != member.id:
            return api_error("NOT_FOUND", "not found", 404)
        if entry.day != _local_now().date():
            raise Invalid("only today's entry")
        entry.status = "here"
        entry.left_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify(_entry(entry, {member.id: member.name}, member.id))

    @bp.get("/onsite/feed")
    @require_member
    def onsite_feed():
        return jsonify({"url": _feed_url(get_current_member(), renew=False)})

    @bp.post("/onsite/feed/renew")
    @require_member
    def onsite_feed_renew():
        return jsonify({"url": _feed_url(get_current_member(), renew=True)})

    @bp.get("/onsite/feed/<string:club>/<string:token>.ics")
    def onsite_feed_ics(club: str, token: str):
        return feed_ics(club, token)

    @bp.get("/onsite/stats")
    @require_member
    def onsite_stats():
        member = get_current_member()
        if not (_can(member, RESOURCES) or _can(member, STATS)):
            return api_error("FORBIDDEN", "only for those who manage bookings", 403)
        months = _int(request.args, "months", 1, 12, default=6)
        return jsonify(stats(months))

    @bp.put("/onsite/watch")
    @require_member
    def onsite_watch():
        member = get_current_member()
        data = _body()
        resource_id = _int(data, "resourceId", 1, 2**31 - 1)
        if resource_id is None or not _rooms([resource_id]):
            raise Invalid("resourceId: no such room")
        row = db.session.scalar(
            select(OnsiteWatch)
            .where(OnsiteWatch.resource_id == resource_id)
            .where(OnsiteWatch.member_id == member.id)
        )
        if data.get("watching") and row is None:
            db.session.add(OnsiteWatch(resource_id=resource_id, member_id=member.id))
        elif not data.get("watching") and row is not None:
            db.session.delete(row)
        db.session.commit()
        return jsonify(
            {"resourceId": resource_id, "watching": bool(data.get("watching"))}
        )


def _qr(room: BookingResource) -> dict:
    import io

    import qrcode
    import qrcode.image.svg

    from hubra.core.services.email import club_app_url

    if not room.onsite_token:
        room.onsite_token = secrets.token_urlsafe(24)
        db.session.commit()
    path = f"/app/booking/checkin/{room.onsite_token}"
    url = club_app_url(path) or path
    image = qrcode.make(
        url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2
    )
    buf = io.BytesIO()
    image.save(buf)
    return {
        "resourceId": room.id,
        "name": room.name,
        "url": url,
        "svg": buf.getvalue().decode(),
    }


def register_checkin(bp) -> None:
    @bp.post("/onsite/checkin")
    @require_member
    def onsite_checkin():
        member = get_current_member()
        token = _text(_body(), "token", 64, required=True)
        room = db.session.scalar(
            select(BookingResource)
            .where(BookingResource.onsite_token == token)
            .where(BookingResource.kind == "room")
            .where(BookingResource.active.is_(True))
        )
        if room is None:
            return api_error("NOT_FOUND", "This QR code is no longer valid", 404)
        today = _local_now().date()
        entry = db.session.scalar(
            select(OnsiteEntry)
            .where(OnsiteEntry.resource_id == room.id)
            .where(OnsiteEntry.member_id == member.id)
            .where(OnsiteEntry.day == today)
        )
        created = entry is None
        if created:
            entry = OnsiteEntry(
                resource_id=room.id,
                member_id=member.id,
                day=today,
                status="here",
                key_holder=False,
            )
            db.session.add(entry)
        was_here = not created and entry.status == "here" and entry.left_at is None
        entry.status = "here"
        entry.left_at = None
        db.session.flush()
        if created:
            tell_watchers(entry, member)
        db.session.commit()
        others = list(
            db.session.scalars(
                select(OnsiteEntry)
                .where(OnsiteEntry.resource_id == room.id)
                .where(OnsiteEntry.day == today)
                .where(OnsiteEntry.member_id != member.id)
                .order_by(OnsiteEntry.starts, OnsiteEntry.id)
            )
        )
        names = _names([e.member_id for e in others] + [member.id])
        return jsonify(
            {
                "room": {"id": room.id, "name": room.name, "location": room.location},
                "entry": _entry(entry, names, member.id),
                "already": was_here,
                "others": [_entry(e, names, member.id) for e in others],
            }
        )

    @bp.get("/onsite/qr/<int:resource_id>")
    @require_member
    def onsite_qr(resource_id: int):
        if not _can(get_current_member(), RESOURCES):
            return api_error("FORBIDDEN", "only for those who manage resources", 403)
        rooms = _rooms([resource_id])
        if not rooms:
            return api_error("NOT_FOUND", "not found", 404)
        return jsonify(_qr(rooms[0]))

    @bp.post("/onsite/qr/<int:resource_id>/renew")
    @require_member
    def onsite_qr_renew(resource_id: int):
        if not _can(get_current_member(), RESOURCES):
            return api_error("FORBIDDEN", "only for those who manage resources", 403)
        rooms = _rooms([resource_id])
        if not rooms:
            return api_error("NOT_FOUND", "not found", 404)
        rooms[0].onsite_token = None
        return jsonify(_qr(rooms[0]))


# ── Texts ────────────────────────────────────────────────────────────────────


_DAYS = {
    True: ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    False: ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}


def _german(member) -> bool:
    return (getattr(member, "language", None) or "de").lower().startswith("de")


def day_label(day: date, german: bool) -> str:
    sep = "." if german else "/"
    return f"{_DAYS[german][day.weekday()]} {day.day:02d}{sep}{day.month:02d}{sep}{day.year}"


def time_label(e: OnsiteEntry, german: bool) -> str:
    if e.starts and e.ends:
        return f"{_hhmm(e.starts)}–{_hhmm(e.ends)}"
    if e.starts:
        return f"{'ab' if german else 'from'} {_hhmm(e.starts)}"
    if e.ends:
        return f"{'bis' if german else 'until'} {_hhmm(e.ends)}"
    return ""


def tell_watchers(entry: OnsiteEntry, member, until: date | None = None) -> int:
    """Members watching the room hear that *member* plans to come (*until*:
    every week up to that day)."""
    from hubra.core.notifications.services import notify_member

    room = db.session.get(BookingResource, entry.resource_id)
    watchers = db.session.scalars(
        select(Member)
        .join(OnsiteWatch, OnsiteWatch.member_id == Member.id)
        .where(OnsiteWatch.resource_id == entry.resource_id)
        .where(Member.id != member.id)
        .where(Member.status == "active")
        .where(Member.archived_at.is_(None))
    ).all()
    for w in watchers:
        de = _german(w)
        when = " ".join(
            x for x in (day_label(entry.day, de), time_label(entry, de)) if x
        )
        if until is not None:
            when += (
                f", jede Woche bis {day_label(until, de)}"
                if de
                else f", every week until {day_label(until, de)}"
            )
        if de:
            verb = "kommt vielleicht" if entry.status == "maybe" else "kommt"
            title = f"Vor Ort: {room.name}"
            msg = (
                f"{member.name} ist jetzt da."
                if entry.status == "here"
                else f"{member.name} {verb} am {when}."
            )
        else:
            verb = "might come" if entry.status == "maybe" else "is coming"
            title = f"Onsite: {room.name}"
            msg = (
                f"{member.name} is there now."
                if entry.status == "here"
                else f"{member.name} {verb} on {when}."
            )
        notify_member(w.id, "info", title, msg, link=f"{LINK}?day={entry.day}")
    return len(watchers)


# ── Jobs ─────────────────────────────────────────────────────────────────────


def _others(
    entries: list[OnsiteEntry], me: int, names: dict, de: bool
) -> tuple[str, str]:
    """Who else comes, and who brings the key."""
    others = [
        names.get(e.member_id, "?") + (" (?)" if e.status == "maybe" else "")
        for e in entries
        if e.member_id != me
    ]
    keys = [names.get(e.member_id, "?") for e in entries if e.key_holder]
    none = "niemand" if de else "nobody"
    return ", ".join(others) or none, ", ".join(keys) or none


def remind(now: datetime | None = None) -> dict:
    """The evening before: everyone who said Komme or Vielleicht for
    tomorrow gets a reminder with who else comes and who brings the key.
    Bell and Discord DM go by the member's "Erinnerung vor Anlässen"
    choices; the mail by their reminder mail switch."""
    from hubra.core.notifications.services import notify_member

    now = now or _local_now()
    done = {"reminded": 0, "mailed": 0}
    if now.hour < setting("onsite_reminder_hour"):
        return done
    tomorrow = now.date() + timedelta(days=1)
    due = datetime.combine(now.date(), time(setting("onsite_reminder_hour")))
    entries = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day == tomorrow)
            .order_by(OnsiteEntry.starts, OnsiteEntry.id)
        )
    )
    todo = [e for e in entries if e.reminded_at is None and e.status in REMINDED]
    if not todo:
        return done
    rooms = {r.id: r for r in _rooms({e.resource_id for e in entries})}
    members = {
        m.id: m
        for m in db.session.scalars(
            select(Member)
            .where(Member.id.in_({e.member_id for e in entries}))
            .where(Member.status == "active")
            .where(Member.archived_at.is_(None))
        )
    }
    names = {i: m.name for i, m in members.items()}
    stamp = datetime.now(timezone.utc)
    for e in todo:
        e.reminded_at = stamp
        member, room = members.get(e.member_id), rooms.get(e.resource_id)
        # Planned after the reminder went out for the day: they know.
        made = e.created_at.astimezone(_zone()).replace(tzinfo=None)
        if member is None or room is None or made >= due:
            continue
        de = _german(member)
        same_room = [x for x in entries if x.resource_id == e.resource_id]
        others, keys = _others(same_room, member.id, names, de)
        when = " ".join(x for x in (day_label(e.day, de), time_label(e, de)) if x)
        if de:
            title = f"Morgen vor Ort: {room.name}"
            msg = f"{when}. Auch dabei: {others}. Schlüssel: {keys}."
        else:
            title = f"Onsite tomorrow: {room.name}"
            msg = f"{when}. Also coming: {others}. Key: {keys}."
        notify_member(
            member.id,
            "info",
            title,
            msg,
            link=f"{LINK}?day={e.day}",
            topic="event_reminders",
        )
        done["reminded"] += 1
        if member.event_reminder_mail and _mail(member, room, e, others, keys, de):
            done["mailed"] += 1
    return done


def _zone():
    from .routes import _zone as zone

    return zone()


def _mail(member, room, entry, others: str, keys: str, de: bool) -> bool:
    """The reminder by mail, with the reminder mail of events (who else comes
    and the key go where the place is)."""
    from hubra.core.services.email import DEFAULT_LANG, club_app_url, club_display_name
    from hubra.core.services.mail_i18n import render_mail_template
    from hubra.core.tasks.after_commit import delay_after_commit
    from hubra.core.tasks.email_tasks import send_email_task

    if not member.email or not member.private_email_verified:
        return False
    lang = member.language or DEFAULT_LANG
    where = [room.location] if room.location else []
    where.append(f"{'Auch dabei' if de else 'Also coming'}: {others}")
    where.append(f"{'Schlüssel' if de else 'Key'}: {keys}")
    when = " ".join(x for x in (day_label(entry.day, de), time_label(entry, de)) if x)
    body_html, body_text, subject = render_mail_template(
        "event_reminder",
        locale=lang,
        name=member.name,
        club_name=club_display_name(),
        event_title=f"{'Vor Ort' if de else 'Onsite'}: {room.name}",
        when=when,
        location=" · ".join(where),
        portal_url=club_app_url(f"{LINK}?day={entry.day}"),
    )
    delay_after_commit(
        send_email_task,
        to_email=member.email,
        to_name=member.name,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
    )
    return True


def today_list(day: date) -> list[dict]:
    """Per room, who's there on *day* (the event's payload)."""
    entries = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day == day)
            .order_by(OnsiteEntry.starts, OnsiteEntry.id)
        )
    )
    if not entries:
        return []
    names = _names(e.member_id for e in entries)
    out = []
    for room in _rooms({e.resource_id for e in entries}):
        people = [
            {
                "member_id": e.member_id,
                "name": names.get(e.member_id, "?"),
                "status": e.status,
                "starts": _hhmm(e.starts),
                "ends": _hhmm(e.ends),
                "key_holder": e.key_holder,
                "comment": e.comment,
            }
            for e in entries
            if e.resource_id == room.id
        ]
        out.append(
            {
                "resource_id": room.id,
                "name": room.name,
                "location": room.location,
                "people": people,
            }
        )
    return out


def announce(now: datetime | None = None) -> dict:
    """In the morning, once a day: the day's list as ``booking.onsite.today``
    (the Discord plugin posts it in the channel the club picked)."""
    from hubra.core.modules import emit
    from hubra.core.services.email import club_app_url

    now = now or _local_now()
    if now.hour < setting("onsite_today_hour"):
        return {"announced": False}
    day = now.date()
    if db.session.get(OnsiteDay, day) is not None:
        return {"announced": False}
    rooms = today_list(day)
    db.session.add(OnsiteDay(day=day))
    if not rooms:
        return {"announced": False}
    emit(TODAY_EVENT, day=day.isoformat(), rooms=rooms, link=club_app_url(LINK))
    return {"announced": True, "rooms": len(rooms)}


def purge(now: datetime | None = None) -> int:
    """Entries older than the club keeps them (at least a year)."""
    now = now or _local_now()
    cutoff = now.date() - timedelta(days=setting("onsite_keep_days"))
    gone = db.session.execute(delete(OnsiteEntry).where(OnsiteEntry.day < cutoff))
    db.session.execute(delete(OnsiteDay).where(OnsiteDay.day < cutoff))
    return gone.rowcount or 0


# ── Mitmachen ────────────────────────────────────────────────────────────────


def tell_host(host: OnsiteEntry, entry: OnsiteEntry, member) -> None:
    """The member whose plan *member* joins hears it."""
    from hubra.core.notifications.services import notify_member

    owner = db.session.get(Member, host.member_id)
    room = db.session.get(BookingResource, host.resource_id)
    if owner is None or room is None:
        return
    de = _german(owner)
    what = f" ({host.comment})" if host.comment else ""
    when = day_label(host.day, de)
    if de:
        title = f"Vor Ort: {room.name}"
        msg = f"{member.name} macht am {when} mit{what}."
    else:
        title = f"Onsite: {room.name}"
        msg = f"{member.name} joins you on {when}{what}."
    notify_member(owner.id, "info", title, msg, link=f"{LINK}?day={host.day}")


# ── Calendar feed ────────────────────────────────────────────────────────────


def _feed_url(member, renew: bool) -> str:
    from flask import url_for

    from hubra.core.tenant.context import current_tenant

    row = db.session.get(OnsiteFeed, member.id)
    if row is None:
        row = OnsiteFeed(member_id=member.id, token=secrets.token_urlsafe(32)[:43])
        db.session.add(row)
    elif renew:
        row.token = secrets.token_urlsafe(32)[:43]
    db.session.commit()
    tenant = current_tenant()
    return url_for(
        "booking_bp.onsite_feed_ics",
        club=tenant.slug if tenant else "-",
        token=row.token,
        _external=True,
    )


def _ics_text(value: str) -> str:
    # CR and other control characters (from a name or a comment) would end
    # the line in some calendar apps and let text add its own properties.
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines of at most 75 octets (RFC 5545 3.1)."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def _vevent(uid: str, day: date, starts, ends, summary: str, desc: str, where):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
    if starts:
        end = ends or (datetime.combine(day, starts) + timedelta(hours=2)).time()
        if end <= starts:
            end = time(23, 59)
        lines.append(f"DTSTART:{day:%Y%m%d}T{starts:%H%M}00")
        lines.append(f"DTEND:{day:%Y%m%d}T{end:%H%M}00")
    else:
        lines.append(f"DTSTART;VALUE=DATE:{day:%Y%m%d}")
        lines.append(f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}")
    lines.append(f"SUMMARY:{_ics_text(summary)}")
    if desc:
        lines.append(f"DESCRIPTION:{_ics_text(desc)}")
    if where:
        lines.append(f"LOCATION:{_ics_text(where)}")
    lines.append("END:VEVENT")
    return [_fold(x) for x in lines]


def feed_ics(club: str, token: str):
    """A member's Vor Ort as iCalendar: their own days, and the days others
    come to a room they watch. Times are the club's local time."""
    from flask import Response, g

    from hubra.core.models.tenant import Tenant
    from hubra.core.module_access import may_use
    from hubra.core.modules import is_enabled
    from hubra.core.tenant.context import set_search_path

    missing = api_error("NOT_FOUND", "Unknown calendar", 404)
    tenant = None
    if club != "-":
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == club))
        if tenant is None or tenant.status != "active":
            return missing
        g.tenant = tenant
        set_search_path(tenant.id)
    if not is_enabled("booking"):
        return missing
    row = db.session.scalar(select(OnsiteFeed).where(OnsiteFeed.token == token))
    member = db.session.get(Member, row.member_id) if row else None
    if member is None or member.archived_at is not None or member.status != "active":
        return missing
    # A member whose roles no longer include Booking loses the feed too.
    if not may_use(member, "booking"):
        return missing
    de = _german(member)
    since = _local_now().date() - timedelta(days=30)
    rooms = {r.id: r for r in _rooms()}
    watched = set(
        db.session.scalars(
            select(OnsiteWatch.resource_id).where(OnsiteWatch.member_id == member.id)
        )
    )
    entries = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day >= since)
            .where(OnsiteEntry.day <= since + AHEAD)
            .where(
                (OnsiteEntry.member_id == member.id)
                | OnsiteEntry.resource_id.in_(watched or {0})
            )
            .order_by(OnsiteEntry.day, OnsiteEntry.starts, OnsiteEntry.id)
        )
    )
    names = _names(e.member_id for e in entries)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Hubra//Vor Ort//DE",
        "CALSCALE:GREGORIAN",
        _fold(
            f"X-WR-CALNAME:{_ics_text(('Vor Ort' if de else 'Onsite') + (f' · {tenant.name}' if tenant else ''))}"
        ),
    ]
    mine = {(e.resource_id, e.day) for e in entries if e.member_id == member.id}
    others: dict[tuple[int, date], list[OnsiteEntry]] = {}
    for e in entries:
        room = rooms.get(e.resource_id)
        if room is None:
            continue
        if e.member_id == member.id:
            same = [
                x
                for x in entries
                if x.resource_id == e.resource_id
                and x.day == e.day
                and x.member_id != member.id
            ]
            also = ", ".join(names.get(x.member_id, "?") for x in same)
            desc = "\n".join(
                x
                for x in (
                    e.comment or "",
                    (f"Auch dabei: {also}" if de else f"Also coming: {also}")
                    if also
                    else "",
                )
                if x
            )
            maybe = (
                (" (vielleicht)" if de else " (maybe)") if e.status == "maybe" else ""
            )
            lines += _vevent(
                f"onsite-{e.id}@hubra",
                e.day,
                e.starts,
                e.ends,
                f"{'Vor Ort' if de else 'Onsite'}: {room.name}{maybe}",
                desc,
                room.location,
            )
        elif (e.resource_id, e.day) not in mine:
            others.setdefault((e.resource_id, e.day), []).append(e)
    for (room_id, day), people in others.items():
        room = rooms[room_id]
        who = ", ".join(names.get(x.member_id, "?") for x in people)
        lines += _vevent(
            f"onsite-room-{room_id}-{day:%Y%m%d}@hubra",
            day,
            None,
            None,
            f"{room.name}: {who}",
            "",
            room.location,
        )
    lines.append("END:VCALENDAR")
    return Response(
        "\r\n".join(lines) + "\r\n",
        mimetype="text/calendar",
        headers={"Cache-Control": "private, max-age=900"},
    )


# ── Who brings the key? ──────────────────────────────────────────────────────


def key_pings(now: datetime | None = None) -> dict:
    """The evening before (at the reminder hour): for each room where people
    come tomorrow but nobody said they bring the key, the members who brought
    its key in the last half year are asked, once per room and day."""
    from hubra.core.notifications.services import notify_member

    now = now or _local_now()
    done = {"keyPings": 0}
    if now.hour < setting("onsite_reminder_hour"):
        return done
    tomorrow = now.date() + timedelta(days=1)
    entries = list(
        db.session.scalars(select(OnsiteEntry).where(OnsiteEntry.day == tomorrow))
    )
    by_room: dict[int, list[OnsiteEntry]] = {}
    for e in entries:
        by_room.setdefault(e.resource_id, []).append(e)
    for room in _rooms(set(by_room)):
        people = by_room[room.id]
        if any(e.key_holder for e in people):
            continue
        if db.session.get(OnsitePing, (room.id, tomorrow)) is not None:
            continue
        db.session.add(OnsitePing(resource_id=room.id, day=tomorrow))
        holders = db.session.scalars(
            select(Member)
            .where(
                Member.id.in_(
                    select(OnsiteEntry.member_id)
                    .where(OnsiteEntry.resource_id == room.id)
                    .where(OnsiteEntry.key_holder.is_(True))
                    .where(OnsiteEntry.day >= tomorrow - KEY_LOOKBACK)
                    .where(OnsiteEntry.day < tomorrow)
                )
            )
            .where(Member.status == "active")
            .where(Member.archived_at.is_(None))
        ).all()
        count = len(people)
        for m in holders:
            de = _german(m)
            if de:
                title = f"Schlüssel für {room.name}?"
                msg = (
                    f"Morgen kommen {count} in {room.name}, aber noch niemand "
                    "bringt den Schlüssel. Kannst du?"
                )
            else:
                title = f"Key for {room.name}?"
                msg = (
                    f"{count} are coming to {room.name} tomorrow, but nobody "
                    "brings the key yet. Can you?"
                )
            notify_member(m.id, "info", title, msg, link=f"{LINK}?day={tomorrow}")
            done["keyPings"] += 1
    return done


# ── Stats ────────────────────────────────────────────────────────────────────


def stats(months: int) -> dict:
    """Per room and month: days with someone, visits (Komme and Bin da, not
    Vielleicht) and different people; visits per weekday."""
    today = _local_now().date()
    first = date(today.year, today.month, 1)
    for _ in range(months - 1):
        first = date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1)
    rooms = _rooms()
    rows = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day >= first)
            .where(OnsiteEntry.day <= today)
            .where(OnsiteEntry.status != "maybe")
        )
    )
    keys = []
    m = first
    while m <= today:
        keys.append(f"{m:%Y-%m}")
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    per: dict = {
        k: {r.id: {"days": set(), "visits": 0, "people": set()} for r in rooms}
        for k in keys
    }
    weekdays = [0] * 7
    for e in rows:
        cell = per.get(f"{e.day:%Y-%m}", {}).get(e.resource_id)
        if cell is None:
            continue
        cell["days"].add(e.day)
        cell["visits"] += 1
        cell["people"].add(e.member_id)
        weekdays[e.day.weekday()] += 1
    return {
        "rooms": [{"id": r.id, "name": r.name} for r in rooms],
        "months": [
            {
                "month": k,
                "rooms": [
                    {
                        "resourceId": rid,
                        "days": len(c["days"]),
                        "visits": c["visits"],
                        "people": len(c["people"]),
                    }
                    for rid, c in per[k].items()
                ],
            }
            for k in keys
        ],
        "weekdays": weekdays,
        "total": {
            "visits": sum(weekdays),
            "people": len({e.member_id for e in rows}),
        },
    }
