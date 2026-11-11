"""Rows left behind by deleted members and resources.

A club's schema is cloned from public without foreign keys
(core/tenant/schema_manager.py), so in clubs made after Booking was
installed the ``ON DELETE CASCADE`` / ``SET NULL`` of models.py never runs.
A member deleted on request (or by the retention job) would leave their Vor
Ort days, comments, watches and feed token behind, and their id on
bookings. The hourly job (tasks.py) clears them; in clubs that do have the
foreign keys there is nothing to do.

Bookings stay (they are the resource's history and may sit on an invoice),
without the member and without their note, like core keeps invoices.
"""

from __future__ import annotations

from sqlalchemy import delete, or_, select, update

from hubra.core.extensions import db
from hubra.core.models.member import Member

from .models import (
    Booking,
    BookingResource,
    OnsiteEntry,
    OnsiteFeed,
    OnsitePing,
    OnsiteWatch,
)


def _gone(column):
    """*column* names a member that no longer exists."""
    return column.is_not(None) & column.not_in(select(Member.id))


def purge_orphans() -> dict:
    members = select(Member.id)
    resources = select(BookingResource.id)
    done = {}
    for name, model in (
        ("onsite", OnsiteEntry),
        ("watches", OnsiteWatch),
    ):
        done[name] = (
            db.session.execute(
                delete(model).where(
                    or_(
                        model.member_id.not_in(members),
                        model.resource_id.not_in(resources),
                    )
                )
            ).rowcount
            or 0
        )
    done["feeds"] = (
        db.session.execute(
            delete(OnsiteFeed).where(OnsiteFeed.member_id.not_in(members))
        ).rowcount
        or 0
    )
    db.session.execute(
        delete(OnsitePing).where(OnsitePing.resource_id.not_in(resources))
    )
    # "Mitmachen" pointing at an entry that is gone.
    db.session.execute(
        update(OnsiteEntry)
        .where(OnsiteEntry.joins_id.is_not(None))
        .where(OnsiteEntry.joins_id.not_in(select(OnsiteEntry.id)))
        .values(joins_id=None)
    )
    cleared = 0
    cleared += (
        db.session.execute(
            update(Booking)
            .where(_gone(Booking.member_id))
            .values(member_id=None, note=None)
        ).rowcount
        or 0
    )
    for col in ("decided_by", "created_by"):
        column = getattr(Booking, col)
        db.session.execute(update(Booking).where(_gone(column)).values({col: None}))
    done["bookings"] = cleared
    return done
