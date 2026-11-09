"""What Booking does when Inventory tells it something (docs/contracts.md)."""

from __future__ import annotations

from sqlalchemy import select

from hubra.core.extensions import db

from .models import BookingResource


def on_item_deleted(tenant_id, item_id: int) -> None:
    """A deleted item can't be booked any more: its resource is switched off.

    The resource and its bookings stay, so past bookings and invoices keep
    their name; the board can delete it once nothing points to it.
    """
    for r in db.session.scalars(
        select(BookingResource).where(BookingResource.inventory_item_id == item_id)
    ):
        r.active = False
        r.inventory_item_id = None
