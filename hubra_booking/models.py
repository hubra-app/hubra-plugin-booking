"""The Booking tables (one copy per club schema).

Times are the club's wall-clock time (Europe/Zurich by default), stored
without a zone: a room is booked from 18:00 to 20:00, whatever the season.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
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


# ── Vor Ort ──────────────────────────────────────────────────────────────────


class OnsiteEntry(db.Model):
    """A member says they'll be in a room on a day (Vor Ort).

    Not a booking: nothing is held, any number of members can be there.
    Status: ``going`` (Komme), ``maybe`` (Vielleicht), ``here`` (Bin da, only
    for today). One entry per member, room and day.
    """

    __tablename__ = "booking_onsite"
    __table_args__ = (
        UniqueConstraint("resource_id", "member_id", "day", name="uq_booking_onsite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("booking_resources.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    # Optional wall-clock times: "ab 18:00", "18:00 bis 21:00".
    starts: Mapped[time | None] = mapped_column(Time)
    ends: Mapped[time | None] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    # "Ich bringe den Schlüssel": the room will be open.
    key_holder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(300))
    # The reminder the evening before went out.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class OnsiteWatch(db.Model):
    """A member wants to hear when someone plans to be in a room."""

    __tablename__ = "booking_onsite_watches"
    __table_args__ = (
        UniqueConstraint("resource_id", "member_id", name="uq_booking_onsite_watch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("booking_resources.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class OnsiteDay(db.Model):
    """Days whose "heute vor Ort" announcement went out (once a day)."""

    __tablename__ = "booking_onsite_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    announced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
