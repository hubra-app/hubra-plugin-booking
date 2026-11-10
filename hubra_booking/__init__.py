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
- Vor Ort: members say on which days they'll be in a room (Komme,
  Vielleicht, Bin da, with an optional time, a comment and "I bring the
  key"), so others can go on the same days. The evening before they get a
  reminder; in the morning the day's list goes out as
  ``booking.onsite.today`` (onsite.py).

Permissions:
    booking.resources.update   add and change resources
    booking.bookings.update    approve, reject and cancel anyone's bookings,
                               book for others and repeat weekly
"""

from hubra.core.contracts import WidgetField, event_contract, widget_contract
from hubra.core.modules import Blueprint, Module, NavItem, Schedule, SettingField

module = Module(
    code="booking",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    role_defaults={"member": "view", "board": "edit"},
    name="Booking",
    description="Rooms and equipment on a calendar",
    default_enabled=False,
    depends_on=("inventory", "members", "finance"),
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
    tables=(
        "booking_resources",
        "booking_bookings",
        "booking_onsite",
        "booking_onsite_watches",
        "booking_onsite_days",
    ),
    settings=(
        SettingField(
            "onsite_keep_days",
            "int",
            365,
            label="Vor Ort: Einträge aufbewahren (Tage)",
            description="Wie lange vergangene Vor-Ort-Einträge bleiben, mindestens 365 Tage.",
        ),
        SettingField(
            "onsite_reminder_hour",
            "int",
            18,
            label="Vor Ort: Erinnerung am Vorabend um (Uhr)",
            description="Wer für morgen «Komme» oder «Vielleicht» sagt, wird zu dieser Stunde erinnert.",
        ),
        SettingField(
            "onsite_today_hour",
            "int",
            7,
            label="Vor Ort: Tagesliste um (Uhr)",
            description="Ab dieser Stunde geht die Liste «heute vor Ort» an Discord.",
        ),
    ),
    tasks=("hubra_booking.tasks",),
    schedule=(
        Schedule("booking-onsite-hourly", "hubra_booking.tasks.onsite_hourly", 3600.0),
    ),
    provides=(
        event_contract(
            "booking.onsite.today",
            "hubra_booking.contracts:OnsiteToday",
            description="Who said they'll be in which room today (Vor Ort), once each morning.",
        ),
        # Dashboard widgets (widgets.py); every member may add them.
        widget_contract(
            "booking.onsite_today",
            "hubra_booking.widgets:today",
            label="booking.widget.today",
            description="booking.widget.todayHint",
            size="m",
            view="list",
        ),
        widget_contract(
            "booking.onsite_mine",
            "hubra_booking.widgets:mine",
            label="booking.widget.mine",
            description="booking.widget.mineHint",
            size="m",
            view="list",
            fields=(WidgetField("count", "booking.widget.count", "number", 5),),
        ),
        widget_contract(
            "booking.onsite_count",
            "hubra_booking.widgets:count",
            label="booking.widget.countToday",
            description="booking.widget.countHint",
            size="s",
            view="stat",
        ),
    ),
    # Equipment is an Inventory item, read through Inventory's contracts.
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
