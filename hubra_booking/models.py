"""The Booking tables (one copy per club schema).

Times are the club's wall-clock time (Europe/Zurich by default), stored
without a zone: a room is booked from 18:00 to 20:00, whatever the season.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hubra.core.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _member_fk() -> ForeignKey:
    return ForeignKey("members.id", ondelete="SET NULL")


class BookingResource(db.Model):
    """A room or a piece of equipment that members can book."""

    __tablename__ = "booking_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="room")
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(20))
    # An item of the Inventory plugin, if the club runs it. No foreign key:
    # the inventory table may not exist.
    inventory_item_id: Mapped[int | None] = mapped_column(Integer)
    needs_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fee_flat: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fee_per_hour: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("transaction_categories.id", ondelete="SET NULL")
    )
    max_hours: Mapped[int | None] = mapped_column(Integer)
    advance_days: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class Booking(db.Model):
    """One slot on a resource. Status: pending, approved, rejected, cancelled."""

    __tablename__ = "booking_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("booking_resources.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int | None] = mapped_column(_member_fk())
    title: Mapped[str | None] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    # Bookings made together with "repeat weekly" share a series id.
    series_id: Mapped[str | None] = mapped_column(String(36))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL")
    )
    decided_by: Mapped[int | None] = mapped_column(_member_fk())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(_member_fk())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
