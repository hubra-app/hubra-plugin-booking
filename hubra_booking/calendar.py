"""Bookings and Vor Ort in the club calendar (``booking.calendar.items``).

Every member sees the bookings of the club in the booking calendar, so the
club calendar shows them too: the resource, the booking's title, from start
to end. Pending bookings are marked; declined and cancelled ones are left
out. Vor Ort adds one all-day entry per room and day that someone said
they'd be there (Komme or Bin da), with how many; "Vielleicht" doesn't count.
Both open their full calendar under Kalender (/app/calendar/<tab>).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select

from hubra.core.extensions import db

from .models import Booking, BookingResource, OnsiteEntry
from .routes import LIVE


def items(ctx, data) -> dict:
    start = datetime.combine(data.start, datetime.min.time())
    end = datetime.combine(data.end + timedelta(days=1), datetime.min.time())
    rows = db.session.execute(
        select(Booking, BookingResource)
        .join(BookingResource, BookingResource.id == Booking.resource_id)
        .where(Booking.status.in_(LIVE))
        .where(Booking.starts_at < end)
        .where(Booking.ends_at > start)
        .order_by(Booking.starts_at)
        .limit(1000)
    ).all()
    out = []
    for booking, resource in rows:
        title = resource.name + (f": {booking.title}" if booking.title else "")
        if booking.status == "pending":
            title += " (?)"
        out.append(
            {
                "id": f"booking:{booking.id}",
                "title": title,
                "kind": "booking",
                "start": booking.starts_at,
                "end": booking.ends_at,
                "location": resource.location,
                "path": "/app/calendar/bookings",
                "color": resource.color,
            }
        )
    lang = (getattr(ctx.actor, "language", None) or "de").lower()
    out.extend(_onsite(data.start, data.end, "vor Ort" if lang.startswith("de") else "on site"))
    return {"items": out}


def _onsite(first, last, label: str) -> list[dict]:
    rows = db.session.execute(
        select(OnsiteEntry.day, BookingResource.id, BookingResource.name, BookingResource.color)
        .join(BookingResource, BookingResource.id == OnsiteEntry.resource_id)
        .where(OnsiteEntry.day >= first)
        .where(OnsiteEntry.day <= last)
        .where(OnsiteEntry.status.in_(("going", "here")))
        .limit(5000)
    ).all()
    count = Counter((day, rid) for day, rid, _, _ in rows)
    rooms = {rid: (name, color) for _, rid, name, color in rows}
    return [
        {
            "id": f"onsite:{rid}:{day.isoformat()}",
            "title": f"{rooms[rid][0]}: {n} {label}",
            "kind": "onsite",
            "start": datetime.combine(day, datetime.min.time()),
            "all_day": True,
            "path": f"/app/calendar/onsite?day={day.isoformat()}",
            "color": rooms[rid][1],
        }
        for (day, rid), n in sorted(count.items())
    ]
