"""Booking: rooms and equipment on a calendar.

- Resources are rooms (the clubhouse, a workshop) or equipment (a trailer,
  a laser cutter). With the Inventory plugin running, equipment is picked
  from its items (name and place come from the item); a room may be one too.
  A deleted item's resource is switched off.
- Members book a slot. Overlapping bookings are refused.
- A resource can need approval: the booking waits until someone with
  ``booking.bookings.update`` approves it.
- A resource can cost a fee (flat and/or per hour). It goes on the member's
  invoice once the booking is confirmed.

Permissions:
    booking.resources.update   add and change resources
    booking.bookings.update    approve, reject and cancel anyone's bookings,
                               book for others and repeat weekly
"""

from hubra.core.modules import Blueprint, Module, NavItem

module = Module(
    code="booking",
    name="Booking",
    description="Rooms and equipment on a calendar",
    default_enabled=False,
    depends_on=("members", "finance"),
    blueprints=(
        Blueprint("hubra_booking.routes", "booking_bp", "/api/v1/app/booking"),
    ),
    nav=(
        NavItem(
            "/app/booking",
            "shell.nav.booking",
            "calendar-time",
            section="more",
            order=27,
        ),
    ),
    tables=("booking_resources", "booking_bookings"),
    # Inventory is optional: without it resources are typed in by hand.
    # Fees go on invoices through Finance's contracts, not its services.
    consumes={
        "inventory.items.get": ">=1,<2",
        "inventory.items.list": ">=1,<2",
        "inventory.item.deleted": ">=1,<2",
        "finance.invoice.create": ">=1,<2",
        "finance.invoice.delete": ">=1,<2",
    },
    events={"inventory.item.deleted": "hubra_booking.hooks:on_item_deleted"},
)
