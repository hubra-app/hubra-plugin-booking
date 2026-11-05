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
    trailer = client.post(
        f"{BASE}/resources",
        json={"name": "Anhänger", "kind": "equipment", "needsApproval": True},
    ).get_json()

    _login(client, "max@test.ch")
    asked = client.post(
        f"{BASE}/bookings",
        json={"resourceId": trailer["id"], "title": "Umzug", **_slot(5, 9, 12)},
    ).get_json()
    assert asked["status"] == "pending" and asked["invoiceId"] is None
    # A pending request already blocks the slot.
    _login(client, "lea@test.ch")
    assert (
        client.post(
            f"{BASE}/bookings", json={"resourceId": trailer["id"], **_slot(5, 10, 11)}
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
            "resourceId": trailer["id"],
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
                "resourceId": trailer["id"],
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

ITEMS = {7: ("Anhänger", "Hof"), 9: ("Laser", "Werkstatt")}


def _inv_get(ctx, data):
    return [{"id": i, "name": ITEMS[i][0]} for i in data["ids"] if i in ITEMS]


def _inv_list(ctx, data):
    return [
        {"id": i, "name": name, "location": where}
        for i, (name, where) in sorted(ITEMS.items())
    ]


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
    set_modules(True, "inventory")
    return fake


def test_resources_link_inventory_items_through_its_queries(client, club, inventory):
    _login(client, "kim@test.ch")
    assert client.get(f"{BASE}/options").get_json()["inventory"] is True
    items = client.get(f"{BASE}/inventory-items").get_json()
    assert [i["name"] for i in items] == ["Anhänger", "Laser"]

    res = client.post(
        f"{BASE}/resources",
        json={"name": "Anhänger", "kind": "equipment", "inventoryItemId": 7},
    )
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["inventoryItemName"] == "Anhänger"
    bad = client.post(
        f"{BASE}/resources",
        json={"name": "Nichts", "kind": "equipment", "inventoryItemId": 99},
    )
    assert bad.status_code == 400


def test_without_inventory_resources_have_no_items(client, club, monkeypatch):
    from hubra.core.modules import registry

    registry.load()
    monkeypatch.delitem(registry._modules, "inventory", raising=False)
    _login(client, "kim@test.ch")
    assert client.get(f"{BASE}/options").get_json()["inventory"] is False
    assert client.get(f"{BASE}/inventory-items").get_json() == []
