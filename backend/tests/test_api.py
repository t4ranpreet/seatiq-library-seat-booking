from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    with TestClient(main.app) as test_client:
        yield test_client


def student(client, name="Demo Student"):
    response = client.post("/api/demo/session", json={"display_name": name})
    assert response.status_code == 200
    return {"X-Demo-Token": response.json()["token"]}


def reservation(client, headers, seat="A02"):
    response = client.post("/api/bookings", headers=headers, json={"seat_id": seat})
    assert response.status_code == 201
    return response.json()


def test_seed_floors_and_seat_map(client):
    floors = client.get("/api/floors").json()
    assert len(floors) == 3
    assert sum(floor["total"] for floor in floors) == 72
    assert sum(floor["available"] for floor in floors) == 70
    seats = client.get("/api/floors/1/seats").json()["seats"]
    assert len(seats) == 24
    assert next(seat for seat in seats if seat["id"] == "A01")["status"] == "occupied"


def test_reservation_is_single_and_conflict_safe(client):
    first = student(client)
    second = student(client, "Demo Guest")
    booking = reservation(client, first)
    assert booking["seat_id"] == "A02"
    assert client.post("/api/bookings", headers=second, json={"seat_id": "A02"}).status_code == 409
    assert client.post("/api/bookings", headers=first, json={"seat_id": "A03"}).status_code == 409
    seats = client.get("/api/floors/1/seats").json()["seats"]
    assert next(seat for seat in seats if seat["id"] == "A02")["status"] == "reserved"


def test_checkin_break_and_return_lifecycle(client):
    headers = student(client)
    booking = reservation(client, headers)
    path = f"/api/bookings/{booking['id']}"
    assert client.post(f"{path}/check-in", headers=headers, json={"qr_token": "WRONG"}).status_code == 400
    checked = client.post(f"{path}/check-in", headers=headers, json={"qr_token": booking["qr_token"]})
    assert checked.status_code == 200
    assert checked.json()["status"] == "occupied"
    paused = client.post(f"{path}/break", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "break"
    returned = client.post(f"{path}/return", headers=headers)
    assert returned.status_code == 200
    assert returned.json()["status"] == "occupied"


def test_expired_break_releases_seat(client, monkeypatch):
    monkeypatch.setattr(main, "BREAK_MINUTES", 1)
    headers = student(client)
    booking = reservation(client, headers)
    path = f"/api/bookings/{booking['id']}"
    client.post(f"{path}/check-in", headers=headers, json={"qr_token": booking["qr_token"]})
    client.post(f"{path}/break", headers=headers)
    with main.connect() as db:
        expired = (main.now() - timedelta(seconds=2)).isoformat()
        db.execute("UPDATE bookings SET break_until=? WHERE id=?", (expired, booking["id"]))
    seats = client.get("/api/floors/1/seats").json()["seats"]
    assert next(seat for seat in seats if seat["id"] == "A02")["status"] == "available"
    me = client.get("/api/me", headers=headers).json()
    assert me["booking"] is None


def test_admin_is_demo_only_and_can_reset(client):
    student_headers = student(client)
    reservation(client, student_headers)
    assert client.get("/api/admin/analytics", headers=student_headers).status_code == 403
    admin = client.post("/api/demo/admin-session").json()
    admin_headers = {"X-Demo-Token": admin["token"]}
    analytics = client.get("/api/admin/analytics", headers=admin_headers)
    assert analytics.status_code == 200
    assert analytics.json()["totals"]["reserved"] == 1
    assert client.post("/api/admin/reset", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/analytics", headers=admin_headers).json()["totals"]["reserved"] == 0


def test_signout_invalidates_demo_session(client):
    headers = student(client)
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.delete("/api/demo/session", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401

