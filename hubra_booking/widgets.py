"""Dashboard widgets of Vor Ort (docs/dashboards.md in hubra-app/hubra).

booking.onsite_today   list  who is in which room today
booking.onsite_mine    list  my next Vor Ort days, with who else comes
booking.onsite_count   stat  how many are coming today

Every member sees them (like the Vor Ort tab); they read as the viewer.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from hubra.core.extensions import db

from . import onsite
from .body import _names
from .models import OnsiteEntry

_MARK = {"maybe": " (?)", "here": " ✓"}


def _today():
    return onsite._local_now().date()


def _german(ctx) -> bool:
    return onsite._german(ctx.actor) if ctx.actor is not None else True


def _who(entries, names, skip=None) -> str:
    return ", ".join(
        names.get(e.member_id, "?")
        + ("🔑" if e.key_holder else "")
        + _MARK.get(e.status, "")
        for e in entries
        if e.member_id != skip
    )


def today(ctx, config: dict) -> dict:
    """Per room, who said they'll be there today."""
    day = _today()
    entries = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day == day)
            .order_by(OnsiteEntry.starts, OnsiteEntry.id)
        )
    )
    names = _names(e.member_id for e in entries)
    items = []
    for room in onsite._rooms({e.resource_id for e in entries}):
        here = [e for e in entries if e.resource_id == room.id]
        items.append(
            {
                "label": f"{room.name} · {len(here)}",
                "sub": _who(here, names),
                "path": f"{onsite.LINK}?day={day}",
            }
        )
    return {"items": items, "total": len(items)}


def mine(ctx, config: dict) -> dict:
    """The viewer's next Vor Ort days, with who else comes."""
    if ctx.actor is None:
        return {"items": [], "total": 0}
    count = max(1, min(int(config.get("count") or 5), 20))
    start = _today()
    base = (
        select(OnsiteEntry)
        .where(OnsiteEntry.member_id == ctx.actor.id)
        .where(OnsiteEntry.day >= start)
    )
    rows = list(
        db.session.scalars(base.order_by(OnsiteEntry.day, OnsiteEntry.id).limit(count))
    )
    total = db.session.scalar(select(func.count()).select_from(base.subquery()))
    if not rows:
        return {"items": [], "total": 0}
    others = list(
        db.session.scalars(
            select(OnsiteEntry)
            .where(OnsiteEntry.day.in_({r.day for r in rows}))
            .where(OnsiteEntry.resource_id.in_({r.resource_id for r in rows}))
            .where(OnsiteEntry.member_id != ctx.actor.id)
            .order_by(OnsiteEntry.starts, OnsiteEntry.id)
        )
    )
    names = _names(e.member_id for e in others)
    rooms = {r.id: r.name for r in onsite._rooms({r.resource_id for r in rows})}
    de = _german(ctx)
    items = []
    for r in rows:
        when = " ".join(
            x for x in (onsite.day_label(r.day, de), onsite.time_label(r, de)) if x
        )
        with_ = _who(
            [o for o in others if o.day == r.day and o.resource_id == r.resource_id],
            names,
        )
        alone = "noch allein" if de else "nobody else yet"
        items.append(
            {
                "label": f"{rooms.get(r.resource_id, '?')} · {when}",
                "sub": (("Mit: " if de else "With: ") + with_) if with_ else alone,
                "path": f"{onsite.LINK}?day={r.day}",
            }
        )
    return {"items": items, "total": total}


def count(ctx, config: dict) -> dict:
    """How many said they'll be in a room today; tomorrow below."""
    day = _today()

    def n(d):
        return (
            db.session.scalar(
                select(func.count())
                .select_from(OnsiteEntry)
                .where(OnsiteEntry.day == d)
            )
            or 0
        )

    tomorrow = n(day + timedelta(days=1))
    de = _german(ctx)
    return {
        "value": n(day),
        "sub": f"{'Morgen' if de else 'Tomorrow'}: {tomorrow}",
        "path": onsite.LINK,
    }
