"""Vor Ort: members say on which days they'll be in a room."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/booking"
STAFF = ["booking.resources.update", "booking.bookings.update"]


@pytest.fixture
def club(client, app, db, seeded_db):
    from hubra_booking.models import BookingResource

    set_modules(True, "booking")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    kim = _make_role_and_member(db, tier, name="Kim", permission_keys=STAFF)
    max_ = _make_role_and_member(db, tier, name="Max")
    lea = _make_role_and_member(db, tier, name="Lea")
    room = BookingResource(
        name="Werkstatt",
        kind="room",
        location="Keller",
        needs_approval=False,
        active=True,
        position=0,
    )
    gear = BookingResource(
        name="Anhänger", kind="equipment", needs_approval=False, active=True, position=1
    )
    db.session.add_all([room, gear])
    db.session.commit()
    return {
        "kim": kim.id,
        "max": max_.id,
        "lea": lea.id,
        "room": room.id,
        "gear": gear.id,
    }


def _day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_members_plan_and_see_each_other(client, db, club):
    _login(client, "max@test.ch")
    r = client.put(
        f"{BASE}/onsite",
        json={
            "resourceId": club["room"],
            "day": _day(2),
            "status": "going",
            "from": "18:00",
            "keyHolder": True,
            "comment": "Fräse",
        },
    )
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["keyHolder"] is True and r.get_json()["from"] == "18:00"
    # Changing it keeps one entry.
    r = client.put(
        f"{BASE}/onsite",
        json={"resourceId": club["room"], "day": _day(2), "status": "maybe"},
    )
    assert r.status_code == 200 and r.get_json()["status"] == "maybe"

    _login(client, "lea@test.ch")
    client.put(f"{BASE}/onsite", json={"resourceId": club["room"], "day": _day(2)})
    data = client.get(f"{BASE}/onsite?from={_day(0)}&to={_day(7)}").get_json()
    assert [r["name"] for r in data["rooms"]] == ["Werkstatt"]  # rooms only
    names = sorted(e["memberName"] for e in data["entries"])
    assert names == ["Test Lea", "Test Max"]
    assert [e["mine"] for e in data["entries"] if e["memberName"] == "Test Lea"] == [
        True
    ]

    # Refused: the past, "here" on another day, equipment, the wrong order.
    for body in (
        {"resourceId": club["room"], "day": _day(-1)},
        {"resourceId": club["room"], "day": _day(1), "status": "here"},
        {"resourceId": club["gear"], "day": _day(1)},
        {"resourceId": club["room"], "day": _day(1), "from": "20:00", "to": "18:00"},
    ):
        assert client.put(f"{BASE}/onsite", json=body).status_code == 400, body
    assert (
        client.put(
            f"{BASE}/onsite",
            json={"resourceId": club["room"], "day": _day(0), "status": "here"},
        ).status_code
        == 201
    )

    # Only own entries go, unless the member manages bookings.
    max_entry = next(e for e in data["entries"] if e["memberName"] == "Test Max")
    assert client.delete(f"{BASE}/onsite/{max_entry['id']}").status_code == 403
    _login(client, "kim@test.ch")
    assert client.delete(f"{BASE}/onsite/{max_entry['id']}").status_code == 204


def test_watchers_hear_about_new_plans(client, db, club):
    from hubra.core.models.notification import Notification

    _login(client, "lea@test.ch")
    assert (
        client.put(
            f"{BASE}/onsite/watch", json={"resourceId": club["room"], "watching": True}
        ).status_code
        == 200
    )
    assert client.get(f"{BASE}/onsite").get_json()["watching"] == [club["room"]]

    _login(client, "max@test.ch")
    client.put(
        f"{BASE}/onsite",
        json={"resourceId": club["room"], "day": _day(3), "from": "19:00"},
    )
    notes = db.session.query(Notification).filter_by(member_id=club["lea"]).all()
    assert len(notes) == 1 and "Max" in notes[0].msg and "19:00" in notes[0].msg
    # Max isn't told about himself.
    assert not db.session.query(Notification).filter_by(member_id=club["max"]).count()


def test_reminder_the_evening_before_and_morning_list(app, db, club, monkeypatch):
    from hubra_booking import onsite
    from hubra_booking.models import OnsiteDay, OnsiteEntry

    from hubra.core.models.notification import Notification

    today = date.today()
    tomorrow = today + timedelta(days=1)
    early = datetime.now(timezone.utc) - timedelta(days=2)
    db.session.add_all(
        [
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["max"],
                day=tomorrow,
                status="going",
                key_holder=True,
                created_at=early,
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["lea"],
                day=tomorrow,
                status="maybe",
                starts=time(18),
                created_at=early,
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["kim"],
                day=today,
                status="here",
                created_at=early,
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["kim"],
                day=today - timedelta(days=400),
                status="going",
                created_at=early,
            ),
        ]
    )
    db.session.commit()

    # Before the reminder hour: nothing.
    assert onsite.remind(datetime.combine(today, time(17)))["reminded"] == 0
    done = onsite.remind(datetime.combine(today, time(18, 5)))
    db.session.commit()
    assert done["reminded"] == 2
    lea = db.session.query(Notification).filter_by(member_id=club["lea"]).one()
    assert "Max" in lea.msg and "Schlüssel: Test Max" in lea.msg
    # Once.
    assert onsite.remind(datetime.combine(today, time(19)))["reminded"] == 0

    sent = []
    monkeypatch.setattr(
        "hubra.core.modules.emit", lambda name, **kw: sent.append((name, kw))
    )
    assert onsite.announce(datetime.combine(today, time(6)))["announced"] is False
    assert onsite.announce(datetime.combine(today, time(7)))["announced"] is True
    assert sent[0][0] == "booking.onsite.today"
    assert sent[0][1]["rooms"][0]["people"][0]["name"] == "Test Kim"
    assert db.session.get(OnsiteDay, today) is not None
    assert onsite.announce(datetime.combine(today, time(8)))["announced"] is False

    # Kept a year, then deleted.
    assert onsite.purge(datetime.combine(today, time(3))) == 1
    db.session.commit()
    assert db.session.query(OnsiteEntry).count() == 3


def test_today_event_matches_its_contract(db, club):
    from hubra_booking import onsite
    from hubra_booking.contracts import OnsiteToday
    from hubra_booking.models import OnsiteEntry

    db.session.add(
        OnsiteEntry(
            resource_id=club["room"],
            member_id=club["max"],
            day=date.today(),
            status="going",
            key_holder=True,
        )
    )
    db.session.commit()
    OnsiteToday(
        day=date.today().isoformat(), rooms=onsite.today_list(date.today()), link="x"
    )


def test_dashboard_widgets(client, db, club):
    from hubra_booking.models import OnsiteEntry

    today = date.today()
    db.session.add_all(
        [
            OnsiteEntry(resource_id=club["room"], member_id=club["max"], day=today, status="here", key_holder=True),
            OnsiteEntry(resource_id=club["room"], member_id=club["lea"], day=today, status="maybe"),
            OnsiteEntry(resource_id=club["room"], member_id=club["lea"], day=today + timedelta(days=1), status="going"),
            OnsiteEntry(resource_id=club["room"], member_id=club["kim"], day=today + timedelta(days=1), status="going"),
        ]
    )
    db.session.commit()
    _login(client, "lea@test.ch")
    names = {w["name"] for w in client.get("/api/v1/app/dashboards/widgets").get_json()["items"]}
    assert {"booking.onsite_today", "booking.onsite_mine", "booking.onsite_count"} <= names

    def data(name, **config):
        r = client.post(f"/api/v1/app/dashboards/widgets/{name}/data", json={"config": config})
        assert r.status_code == 200, r.get_json()
        return r.get_json()["data"]

    rows = data("booking.onsite_today")["items"]
    assert rows[0]["label"] == "Werkstatt · 2" and "Test Max🔑 ✓" in rows[0]["sub"]
    mine = data("booking.onsite_mine", count=5)
    assert mine["total"] == 2
    assert "Test Max" in mine["items"][0]["sub"] and "Test Kim" in mine["items"][1]["sub"]
    stat = data("booking.onsite_count")
    assert stat["value"] == 2 and stat["sub"].endswith(": 2")


def test_check_in_by_room_qr_code(client, db, club):
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/onsite/qr/{club['room']}").status_code == 403
    _login(client, "kim@test.ch")
    qr = client.get(f"{BASE}/onsite/qr/{club['room']}").get_json()
    assert qr["svg"].startswith("<?xml") or "<svg" in qr["svg"]
    token = qr["url"].rsplit("/", 1)[1]
    # The same code until it is renewed.
    assert client.get(f"{BASE}/onsite/qr/{club['room']}").get_json()["url"] == qr["url"]

    _login(client, "lea@test.ch")
    client.put(f"{BASE}/onsite", json={"resourceId": club["room"], "day": _day(0), "status": "going", "keyHolder": True})
    _login(client, "max@test.ch")
    r = client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()
    assert r["room"]["name"] == "Werkstatt" and r["entry"]["status"] == "here" and r["already"] is False
    assert [o["memberName"] for o in r["others"]] == ["Test Lea"]
    assert client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()["already"] is True
    # Lea had said "Komme": scanning turns it into "Bin da", keeping the key.
    _login(client, "lea@test.ch")
    r = client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()
    assert r["entry"]["status"] == "here" and r["entry"]["keyHolder"] is True

    _login(client, "kim@test.ch")
    new = client.post(f"{BASE}/onsite/qr/{club['room']}/renew").get_json()
    assert new["url"] != qr["url"]
    assert client.post(f"{BASE}/onsite/checkin", json={"token": token}).status_code == 404
