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
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["max"],
                day=today,
                status="here",
                key_holder=True,
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["lea"],
                day=today,
                status="maybe",
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["lea"],
                day=today + timedelta(days=1),
                status="going",
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["kim"],
                day=today + timedelta(days=1),
                status="going",
            ),
        ]
    )
    db.session.commit()
    _login(client, "lea@test.ch")
    names = {
        w["name"]
        for w in client.get("/api/v1/app/dashboards/widgets").get_json()["items"]
    }
    assert {
        "booking.onsite_today",
        "booking.onsite_mine",
        "booking.onsite_count",
    } <= names

    def data(name, **config):
        r = client.post(
            f"/api/v1/app/dashboards/widgets/{name}/data", json={"config": config}
        )
        assert r.status_code == 200, r.get_json()
        return r.get_json()["data"]

    rows = data("booking.onsite_today")["items"]
    assert rows[0]["label"] == "Werkstatt · 2" and "Test Max🔑 ✓" in rows[0]["sub"]
    mine = data("booking.onsite_mine", count=5)
    assert mine["total"] == 2
    assert (
        "Test Max" in mine["items"][0]["sub"] and "Test Kim" in mine["items"][1]["sub"]
    )
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
    client.put(
        f"{BASE}/onsite",
        json={
            "resourceId": club["room"],
            "day": _day(0),
            "status": "going",
            "keyHolder": True,
        },
    )
    _login(client, "max@test.ch")
    r = client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()
    assert (
        r["room"]["name"] == "Werkstatt"
        and r["entry"]["status"] == "here"
        and r["already"] is False
    )
    assert [o["memberName"] for o in r["others"]] == ["Test Lea"]
    assert (
        client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()[
            "already"
        ]
        is True
    )
    # Lea had said "Komme": scanning turns it into "Bin da", keeping the key.
    _login(client, "lea@test.ch")
    r = client.post(f"{BASE}/onsite/checkin", json={"token": token}).get_json()
    assert r["entry"]["status"] == "here" and r["entry"]["keyHolder"] is True

    _login(client, "kim@test.ch")
    new = client.post(f"{BASE}/onsite/qr/{club['room']}/renew").get_json()
    assert new["url"] != qr["url"]
    assert (
        client.post(f"{BASE}/onsite/checkin", json={"token": token}).status_code == 404
    )


def test_repeat_weekly_and_remove_the_following(client, db, club):
    _login(client, "max@test.ch")
    r = client.put(
        f"{BASE}/onsite",
        json={
            "resourceId": club["room"],
            "day": _day(1),
            "from": "18:00",
            "repeatUntil": _day(29),
        },
    )
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["made"] == 5 and r.get_json()["series"]
    data = client.get(f"{BASE}/onsite?from={_day(0)}&to={_day(30)}").get_json()
    days = [e["day"] for e in data["entries"]]
    assert days == [_day(1), _day(8), _day(15), _day(22), _day(29)]
    assert all(e["from"] == "18:00" for e in data["entries"])
    # "Bin da" can't repeat; nor further than a year.
    for body in (
        {
            "resourceId": club["room"],
            "day": _day(0),
            "status": "here",
            "repeatUntil": _day(14),
        },
        {"resourceId": club["room"], "day": _day(1), "repeatUntil": _day(400)},
    ):
        assert client.put(f"{BASE}/onsite", json=body).status_code == 400, body
    # Removing the third one and the following leaves the first two.
    third = data["entries"][2]["id"]
    assert client.delete(f"{BASE}/onsite/{third}?following=1").status_code == 204
    left = client.get(f"{BASE}/onsite?from={_day(0)}&to={_day(30)}").get_json()[
        "entries"
    ]
    assert [e["day"] for e in left] == [_day(1), _day(8)]


def test_check_out(client, db, club):
    _login(client, "max@test.ch")
    entry = client.put(
        f"{BASE}/onsite",
        json={"resourceId": club["room"], "day": _day(0), "status": "here"},
    ).get_json()
    r = client.post(f"{BASE}/onsite/{entry['id']}/leave")
    assert r.status_code == 200 and r.get_json()["leftAt"]
    # Not someone else's, not another day.
    later = client.put(
        f"{BASE}/onsite", json={"resourceId": club["room"], "day": _day(2)}
    ).get_json()
    assert client.post(f"{BASE}/onsite/{later['id']}/leave").status_code == 400
    _login(client, "lea@test.ch")
    assert client.post(f"{BASE}/onsite/{entry['id']}/leave").status_code == 404


def test_join_someone_s_plan(client, db, club):
    from hubra.core.models.notification import Notification

    _login(client, "max@test.ch")
    host = client.put(
        f"{BASE}/onsite",
        json={
            "resourceId": club["room"],
            "day": _day(2),
            "comment": "Boot schleifen",
            "joinable": True,
        },
    ).get_json()
    assert host["joinable"] is True
    # Can't join oneself.
    assert (
        client.put(
            f"{BASE}/onsite",
            json={"resourceId": club["room"], "day": _day(2), "joinsId": host["id"]},
        ).status_code
        == 400
    )
    _login(client, "lea@test.ch")
    r = client.put(
        f"{BASE}/onsite",
        json={"resourceId": club["room"], "day": _day(2), "joinsId": host["id"]},
    )
    assert r.status_code == 201 and r.get_json()["joinsId"] == host["id"]
    note = db.session.query(Notification).filter_by(member_id=club["max"]).one()
    assert "Lea" in note.msg and "Boot schleifen" in note.msg
    # Another day: nothing to join.
    assert (
        client.put(
            f"{BASE}/onsite",
            json={"resourceId": club["room"], "day": _day(3), "joinsId": host["id"]},
        ).status_code
        == 400
    )


def test_calendar_feed(client, db, club):
    _login(client, "lea@test.ch")
    client.put(
        f"{BASE}/onsite/watch", json={"resourceId": club["room"], "watching": True}
    )
    client.put(
        f"{BASE}/onsite",
        json={
            "resourceId": club["room"],
            "day": _day(1),
            "from": "18:00",
            "comment": "Fräse; neu",
        },
    )
    url = client.get(f"{BASE}/onsite/feed").get_json()["url"]
    assert client.get(f"{BASE}/onsite/feed").get_json()["url"] == url
    _login(client, "max@test.ch")
    client.put(f"{BASE}/onsite", json={"resourceId": club["room"], "day": _day(1)})
    client.put(f"{BASE}/onsite", json={"resourceId": club["room"], "day": _day(4)})

    path = url[url.index("/api/") :]
    client.environ_base.pop("HTTP_AUTHORIZATION", None)
    client.delete_cookie("access_token_cookie")
    resp = client.get(path, headers={"Authorization": ""})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.mimetype == "text/calendar"
    body = resp.get_data(as_text=True)
    assert body.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:Vor Ort: Werkstatt" in body and "T180000" in body
    assert r"Fräse\; neu" in body and "Auch dabei: Test Max" in body
    # Max's other day comes from the watched room.
    assert "SUMMARY:Werkstatt: Test Max" in body
    assert client.get(path.replace(".ics", "x.ics")).status_code == 404

    _login(client, "lea@test.ch")
    new = client.post(f"{BASE}/onsite/feed/renew").get_json()["url"]
    assert new != url
    assert client.get(path).status_code == 404


def test_key_ping_the_evening_before(db, club):
    from hubra_booking import onsite
    from hubra_booking.models import OnsiteEntry

    from hubra.core.models.notification import Notification

    today = date.today()
    tomorrow = today + timedelta(days=1)
    db.session.add_all(
        [
            # Kim brought the key a month ago.
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["kim"],
                day=today - timedelta(days=30),
                status="here",
                key_holder=True,
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["max"],
                day=tomorrow,
                status="going",
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["lea"],
                day=tomorrow,
                status="maybe",
            ),
        ]
    )
    db.session.commit()
    assert onsite.key_pings(datetime.combine(today, time(17)))["keyPings"] == 0
    assert onsite.key_pings(datetime.combine(today, time(18)))["keyPings"] == 1
    db.session.commit()
    note = db.session.query(Notification).filter_by(member_id=club["kim"]).one()
    assert "2" in note.msg and "Schlüssel" in note.msg
    # Once per room and day.
    assert onsite.key_pings(datetime.combine(today, time(19)))["keyPings"] == 0


def test_stats_for_the_board(client, db, club):
    from hubra_booking.models import OnsiteEntry

    today = date.today()
    db.session.add_all(
        [
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["max"],
                day=today,
                status="here",
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["lea"],
                day=today,
                status="going",
            ),
            OnsiteEntry(
                resource_id=club["room"],
                member_id=club["kim"],
                day=today,
                status="maybe",
            ),
        ]
    )
    db.session.commit()
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/onsite/stats").status_code == 403
    _login(client, "kim@test.ch")
    r = client.get(f"{BASE}/onsite/stats?months=3").get_json()
    assert len(r["months"]) == 3 and r["months"][-1]["month"] == f"{today:%Y-%m}"
    cell = r["months"][-1]["rooms"][0]
    assert cell == {"resourceId": club["room"], "days": 1, "visits": 2, "people": 2}
    assert r["weekdays"][today.weekday()] == 2 and r["total"]["visits"] == 2


def test_feed_text_cannot_break_the_ics_lines():
    from hubra_booking.onsite import _ics_text

    out = _ics_text("Fräse\r\nBEGIN:VEVENT\rX\x00Y")
    assert "\r" not in out and "\n" not in out and "\x00" not in out
    assert out == r"Fräse\nBEGIN:VEVENT\nXY"


def test_a_deleted_member_leaves_nothing_behind(client, db, club):
    """Club schemas may lack the foreign keys that cascade: the hourly job
    removes a deleted member's Vor Ort rows and their name from bookings."""
    from sqlalchemy import text

    from hubra_booking.cleanup import purge_orphans
    from hubra_booking.models import Booking, OnsiteEntry, OnsiteFeed, OnsiteWatch

    _login(client, "max@test.ch")
    client.put(
        f"{BASE}/onsite/watch", json={"resourceId": club["room"], "watching": True}
    )
    client.put(
        f"{BASE}/onsite",
        json={"resourceId": club["room"], "day": _day(1), "comment": "privat"},
    )
    client.get(f"{BASE}/onsite/feed")
    day = date.today() + timedelta(days=2)
    b = client.post(
        f"{BASE}/bookings",
        json={
            "resourceId": club["room"],
            "startsAt": f"{day}T10:00",
            "endsAt": f"{day}T11:00",
            "note": "privat",
        },
    ).get_json()
    # Gone as a club schema without foreign keys would leave it.
    db.session.execute(text("PRAGMA foreign_keys=OFF"))
    db.session.execute(text("DELETE FROM members WHERE id = :id"), {"id": club["max"]})
    db.session.commit()

    done = purge_orphans()
    db.session.commit()
    assert done["onsite"] == 1 and done["watches"] == 1 and done["feeds"] == 1
    assert db.session.query(OnsiteEntry).count() == 0
    assert db.session.query(OnsiteWatch).count() == 0
    assert db.session.query(OnsiteFeed).count() == 0
    kept = db.session.get(Booking, b["id"])
    assert kept.member_id is None and kept.note is None and kept.created_by is None
    assert purge_orphans()["bookings"] == 0


def test_bookings_in_the_club_calendar(client, db, club):
    from hubra_booking.models import Booking, OnsiteEntry

    day = date.today() + timedelta(days=2)
    at = datetime.combine(day, time(9))
    db.session.add_all(
        [
            Booking(resource_id=club["room"], member_id=club["max"], title="Löten", starts_at=at, ends_at=at + timedelta(hours=2), status="approved"),
            Booking(resource_id=club["gear"], member_id=club["lea"], starts_at=at, ends_at=at + timedelta(hours=1), status="pending"),
            Booking(resource_id=club["room"], member_id=club["lea"], starts_at=at, ends_at=at + timedelta(hours=1), status="declined"),
            # Vor Ort: two coming, one maybe (not counted).
            OnsiteEntry(resource_id=club["room"], member_id=club["max"], day=day, status="going"),
            OnsiteEntry(resource_id=club["room"], member_id=club["lea"], day=day, status="going"),
            OnsiteEntry(resource_id=club["gear"], member_id=club["lea"], day=day, status="maybe"),
        ]
    )
    db.session.commit()
    _login(client, "lea@test.ch")
    resp = client.get(
        "/api/v1/app/calendar/",
        query_string={"start": day.isoformat(), "end": day.isoformat()},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "booking" in body["sources"]
    titles = sorted(i["title"] for i in body["items"] if i["kind"] == "booking")
    assert titles == ["Anhänger (?)", "Werkstatt: Löten"]
    bookings = [i for i in body["items"] if i["kind"] == "booking"]
    assert {i["path"] for i in bookings} == {"/app/calendar/bookings"}
    onsite = [i for i in body["items"] if i["kind"] == "onsite"]
    assert [(i["title"], i["all_day"], i["path"]) for i in onsite] == [
        ("Werkstatt: 2 vor Ort", True, f"/app/calendar/onsite?day={day.isoformat()}")
    ]
