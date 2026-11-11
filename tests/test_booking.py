"""The Booking plugin: resources on a calendar, overlaps refused, approval
and a fee on the member's invoice.

Runs with Hubra's fixtures once the plugin is in plugins/booking of a Hubra
checkout (see README.md).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/booking"
STAFF = ["booking.resources.update", "booking.bookings.update"]


@pytest.fixture
def club(client, app, db, seeded_db):
    """Kim runs the clubhouse; Max and Lea are ordinary members."""
    from hubra.core.models.finance import TransactionCategory

    set_modules(True, "booking")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    kim = _make_role_and_member(db, tier, name="Kim", permission_keys=STAFF)
    max_ = _make_role_and_member(db, tier, name="Max")
    lea = _make_role_and_member(db, tier, name="Lea")
    cat = TransactionCategory(name="Vermietung")
    db.session.add(cat)
    db.session.commit()
    return {"kim": kim.id, "max": max_.id, "lea": lea.id, "cat": cat.id}


def _slot(days: int, start: int, end: int) -> dict:
    day = date.today() + timedelta(days=days)
    return {
        "startsAt": f"{day.isoformat()}T{start:02d}:00",
        "endsAt": f"{day.isoformat()}T{end:02d}:00",
    }


def test_overlaps_are_refused_and_a_fee_is_invoiced(client, db, club):
    from hubra.core.models.finance import Invoice

    _login(client, "kim@test.ch")
    room = client.post(
        f"{BASE}/resources",
        json={
            "name": "Clubhaus",
            "kind": "room",
            "feeFlat": "20",
            "feePerHour": "10",
            "categoryId": club["cat"],
            "maxHours": 6,
        },
    ).get_json()
    assert room["feePerHour"] == 10.0 and room["needsApproval"] is False

    _login(client, "max@test.ch")
    assert client.post(f"{BASE}/resources", json={"name": "x"}).status_code == 403
    b = client.post(
        f"{BASE}/bookings", json={"resourceId": room["id"], **_slot(3, 18, 21)}
    )
    assert b.status_code == 201
    booking = b.get_json()
    assert booking["status"] == "approved" and booking["fee"] == 50.0
    invoice = db.session.get(Invoice, booking["invoiceId"])
    assert invoice.member_id == club["max"] and float(invoice.amount) == 50.0

    # Too long, in the past, or on top of Max: refused.
    assert (
        client.post(
            f"{BASE}/bookings", json={"resourceId": room["id"], **_slot(4, 8, 20)}
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{BASE}/bookings", json={"resourceId": room["id"], **_slot(-1, 8, 9)}
        ).status_code
        == 400
    )
    _login(client, "lea@test.ch")
    clash = client.post(
        f"{BASE}/bookings", json={"resourceId": room["id"], **_slot(3, 20, 22)}
    )
    assert clash.status_code == 409
    assert clash.get_json()["error"] == "BOOKING_CONFLICT"
    # Right after is fine.
    assert (
        client.post(
            f"{BASE}/bookings", json={"resourceId": room["id"], **_slot(3, 21, 22)}
        ).status_code
        == 201
    )
    # Lea sees Max's slot in the calendar, but not his fee.
    day = date.today() + timedelta(days=3)
    cal = client.get(
        f"{BASE}/bookings?from={day.isoformat()}&to={(day + timedelta(days=1)).isoformat()}"
    ).get_json()
    theirs = next(c for c in cal if c["id"] == booking["id"])
    assert theirs["memberName"] == "Test Max" and "fee" not in theirs
    assert client.post(f"{BASE}/bookings/{booking['id']}/cancel").status_code == 403

    # Max cancels: the unpaid invoice goes with it.
    _login(client, "max@test.ch")
    assert client.post(f"{BASE}/bookings/{booking['id']}/cancel").status_code == 200
    assert db.session.get(Invoice, booking["invoiceId"]) is None
    # A resource with bookings is switched off, not deleted.
    _login(client, "kim@test.ch")
    assert client.delete(f"{BASE}/resources/{room['id']}").status_code == 409


def test_approval_and_weekly_series(client, db, club):
    _login(client, "kim@test.ch")
    meeting_room = client.post(
        f"{BASE}/resources",
        json={"name": "Sitzungszimmer", "kind": "room", "needsApproval": True},
    ).get_json()

    _login(client, "max@test.ch")
    asked = client.post(
        f"{BASE}/bookings",
        json={"resourceId": meeting_room["id"], "title": "Umzug", **_slot(5, 9, 12)},
    ).get_json()
    assert asked["status"] == "pending" and asked["invoiceId"] is None
    # A pending request already blocks the slot.
    _login(client, "lea@test.ch")
    assert (
        client.post(
            f"{BASE}/bookings",
            json={"resourceId": meeting_room["id"], **_slot(5, 10, 11)},
        ).status_code
        == 409
    )
    assert client.get(f"{BASE}/bookings/pending").status_code == 403

    _login(client, "kim@test.ch")
    assert client.get(f"{BASE}/options").get_json()["pending"] == 1
    pending = client.get(f"{BASE}/bookings/pending").get_json()
    assert [p["id"] for p in pending] == [asked["id"]]
    done = client.post(
        f"{BASE}/bookings/{asked['id']}/decide",
        json={"approve": False, "note": "Defekt"},
    ).get_json()
    assert done["status"] == "rejected"
    assert (
        client.post(
            f"{BASE}/bookings/{asked['id']}/decide", json={"approve": True}
        ).status_code
        == 409
    )

    # Kim books the training slot for Lea every week for a month.
    series = client.post(
        f"{BASE}/bookings",
        json={
            "resourceId": meeting_room["id"],
            "memberId": club["lea"],
            "repeatWeeks": 3,
            **_slot(1, 17, 19),
        },
    ).get_json()
    assert len(series) == 4 and all(s["status"] == "approved" for s in series)
    starts = [datetime.fromisoformat(s["startsAt"]) for s in series]
    assert starts[1] - starts[0] == timedelta(weeks=1)
    # Max can't book for others or repeat.
    _login(client, "max@test.ch")
    assert (
        client.post(
            f"{BASE}/bookings",
            json={
                "resourceId": meeting_room["id"],
                "memberId": club["lea"],
                **_slot(2, 8, 9),
            },
        ).status_code
        == 403
    )
    # Lea cancels the rest of the series from the second one on.
    _login(client, "lea@test.ch")
    mine = client.get(f"{BASE}/bookings/mine").get_json()
    assert len(mine) == 4
    gone = client.post(
        f"{BASE}/bookings/{series[1]['id']}/cancel", json={"series": True}
    ).get_json()
    assert sorted(gone["cancelled"]) == sorted(s["id"] for s in series[1:])


# ── Inventory, through its contracts ────────────────────────────────────────

ITEMS = {
    7: {"name": "Anhänger", "location": "Hof", "status": "available"},
    9: {"name": "Laser", "location": "Werkstatt", "status": "available"},
    11: {"name": "Bohrmaschine", "location": None, "status": "broken"},
}


def _item(i):
    return {"id": i, "category": "Tool", **ITEMS[i]}


def _inv_get(ctx, data):
    return [_item(i) for i in data["ids"] if i in ITEMS]


def _inv_list(ctx, data):
    return [_item(i) for i in sorted(ITEMS)]


@pytest.fixture
def inventory(app, monkeypatch):
    """A stand-in Inventory that offers the two queries Booking uses."""
    from hubra.core.contracts import query_contract
    from hubra.core.modules import Module, registry

    registry.load()
    fake = Module(
        code="inventory",
        name="Inventory",
        provides=(
            query_contract("inventory.items.get", f"{__name__}:_inv_get"),
            query_contract("inventory.items.list", f"{__name__}:_inv_list"),
        ),
    )
    monkeypatch.setitem(registry._modules, "inventory", fake)
    monkeypatch.setitem(ITEMS, 7, dict(ITEMS[7]))
    set_modules(True, "inventory")
    return fake


def test_equipment_is_picked_from_the_inventory(client, club, inventory):
    _login(client, "kim@test.ch")
    assert client.get(f"{BASE}/options").get_json()["inventory"] is True
    items = client.get(f"{BASE}/inventory-items").get_json()
    assert [i["name"] for i in items] == ["Anhänger", "Laser", "Bohrmaschine"]
    assert all(i["resourceId"] is None for i in items)

    # Equipment typed in by hand is refused while Inventory runs.
    typed = client.post(
        f"{BASE}/resources", json={"name": "Anhänger", "kind": "equipment"}
    )
    assert typed.status_code == 400, typed.get_json()

    # Picked from the inventory: name and place come from the item.
    res = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 7}
    )
    assert res.status_code == 201, res.get_json()
    trailer = res.get_json()
    assert trailer["name"] == "Anhänger" and trailer["location"] == "Hof"
    assert trailer["inventoryItemName"] == "Anhänger"

    # One item is one resource.
    again = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 7}
    )
    assert again.status_code == 400
    items = client.get(f"{BASE}/inventory-items").get_json()
    assert {i["id"]: i["resourceId"] for i in items}[7] == trailer["id"]

    bad = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 99}
    )
    assert bad.status_code == 400

    # A renamed item shows its new name, in the list and on bookings.
    ITEMS[7]["name"] = "Veloanhänger"
    listed = client.get(f"{BASE}/resources").get_json()
    assert [r["name"] for r in listed] == ["Veloanhänger"]
    b = client.post(
        f"{BASE}/bookings", json={"resourceId": trailer["id"], **_slot(2, 9, 11)}
    )
    assert b.status_code == 201 and b.get_json()["resourceName"] == "Veloanhänger"

    # Rooms may still be typed in.
    room = client.post(f"{BASE}/resources", json={"name": "Clubhaus", "kind": "room"})
    assert room.status_code == 201


def test_items_out_of_use_cannot_be_booked(client, club, inventory):
    _login(client, "kim@test.ch")
    drill = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 11}
    ).get_json()
    assert drill["inventoryItemStatus"] == "broken"
    _login(client, "max@test.ch")
    b = client.post(
        f"{BASE}/bookings", json={"resourceId": drill["id"], **_slot(2, 9, 11)}
    )
    assert b.status_code == 409
    assert b.get_json()["error"] == "RESOURCE_OUT_OF_USE"


def test_a_deleted_item_switches_its_resource_off(client, db, club, inventory):
    from hubra_booking.hooks import on_item_deleted
    from hubra_booking.models import BookingResource

    _login(client, "kim@test.ch")
    laser = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 9}
    ).get_json()
    on_item_deleted(None, 9)
    db.session.commit()
    r = db.session.get(BookingResource, laser["id"])
    assert r.active is False and r.inventory_item_id is None and r.name == "Laser"


def test_resources_keep_their_name_when_inventory_cannot_answer(
    client, club, inventory, monkeypatch
):
    _login(client, "kim@test.ch")
    trailer = client.post(
        f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 7}
    ).get_json()
    # Inventory's queries fail: the copy kept in Booking is shown instead.
    monkeypatch.delitem(ITEMS, 7)
    listed = client.get(f"{BASE}/resources").get_json()
    assert [(r["id"], r["name"]) for r in listed] == [(trailer["id"], "Anhänger")]
    assert listed[0]["inventoryItemName"] is None


def test_the_item_page_panel_reads_its_resource(client, club, inventory):
    _login(client, "kim@test.ch")
    empty = client.get(f"{BASE}/resources/by-item/9").get_json()
    assert empty["resource"] is None and empty["canManage"] is True
    assert empty["item"]["name"] == "Laser"
    laser = client.post(
        f"{BASE}/resources",
        json={"kind": "equipment", "inventoryItemId": 9, "feePerHour": "12"},
    ).get_json()
    got = client.get(f"{BASE}/resources/by-item/9").get_json()
    assert got["resource"]["id"] == laser["id"]

    # Members see an active resource but may not change it; a switched-off
    # one isn't shown to them.
    _login(client, "max@test.ch")
    seen = client.get(f"{BASE}/resources/by-item/9").get_json()
    assert seen["resource"]["id"] == laser["id"] and seen["canManage"] is False
    _login(client, "kim@test.ch")
    client.patch(f"{BASE}/resources/{laser['id']}", json={"active": False})
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/resources/by-item/9").get_json()["resource"] is None


def test_the_item_panel_keeps_items_to_those_who_may_see_them(
    client, club, inventory, monkeypatch
):
    """Without a resource, an item's name and place come only with the
    caller's own Inventory rights (inventory.items.read)."""
    from hubra.core.contracts import query_contract
    from hubra.core.modules import Module, registry

    guarded = Module(
        code="inventory",
        name="Inventory",
        provides=(
            query_contract(
                "inventory.items.get",
                f"{__name__}:_inv_get",
                perm="inventory.items.read",
            ),
            query_contract(
                "inventory.items.list",
                f"{__name__}:_inv_list",
                perm="inventory.items.read",
            ),
        ),
    )
    monkeypatch.setitem(registry._modules, "inventory", guarded)
    _login(client, "max@test.ch")
    got = client.get(f"{BASE}/resources/by-item/9").get_json()
    assert got["resource"] is None and got["item"] is None

    # Once it is a bookable resource every member sees it in Booking anyway.
    _login(client, "kim@test.ch")
    assert (
        client.get(f"{BASE}/resources/by-item/9").get_json()["item"]["name"] == "Laser"
    )
    client.post(f"{BASE}/resources", json={"kind": "equipment", "inventoryItemId": 9})
    _login(client, "max@test.ch")
    got = client.get(f"{BASE}/resources/by-item/9").get_json()
    assert got["resource"]["name"] == "Laser" and got["item"]["name"] == "Laser"


def test_resource_colour_is_a_name_or_hex(client, club):
    _login(client, "kim@test.ch")
    ok = client.post(f"{BASE}/resources", json={"name": "A", "color": "teal"})
    assert ok.status_code == 201
    assert (
        client.post(
            f"{BASE}/resources", json={"name": "B", "color": "#7048e8"}
        ).status_code
        == 201
    )
    bad = client.post(f"{BASE}/resources", json={"name": "C", "color": "red);x:url(a"})
    assert bad.status_code == 400


def test_a_member_cannot_cancel_part_of_a_series(client, db, club):
    """A refusal on one booking of a series changes none of them."""
    from hubra_booking.models import Booking

    _login(client, "kim@test.ch")
    room = client.post(
        f"{BASE}/resources", json={"name": "Clubhaus", "kind": "room", "feeFlat": "10"}
    ).get_json()
    made = client.post(
        f"{BASE}/bookings",
        json={
            "resourceId": room["id"],
            "memberId": club["max"],
            "repeatWeeks": 2,
            **_slot(2, 9, 11),
        },
    ).get_json()
    # The last one is paid already: Max's series cancel is refused, and the
    # earlier ones keep their invoices.
    from hubra.core.models.finance import Invoice

    db.session.get(Invoice, made[-1]["invoiceId"]).status = "Paid"
    db.session.commit()
    _login(client, "max@test.ch")
    r = client.post(f"{BASE}/bookings/{made[1]['id']}/cancel", json={"series": True})
    assert r.status_code == 409 and r.get_json()["error"] == "BOOKING_PAID"
    db.session.expire_all()
    b = db.session.get(Booking, made[1]["id"])
    assert b.status == "approved" and b.invoice_id == made[1]["invoiceId"]
    assert db.session.get(Invoice, made[1]["invoiceId"]) is not None
