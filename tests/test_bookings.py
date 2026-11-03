"""Tests de réservation : création, double réservation, annulation."""

from tests.conftest import login


def test_draft_screening_is_not_visible_or_bookable(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    db[1]["film"].is_published = False
    db[0].commit()
    screening_id = db[1]["future"].id
    assert client.get(f"/api/screenings/{screening_id}/seats").status_code == 404
    response = client.post(
        "/api/bookings", json={"screening_id": screening_id, "seats": ["A1"]}
    )
    assert response.status_code == 404


def _future_id(db):
    return db[1]["future"].id


def _past_id(db):
    return db[1]["past"].id


def test_seats_endpoint_lists_taken_seats(client, db):
    response = client.get(f"/api/screenings/{_future_id(db)}/seats")
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == 2
    assert body["cols"] == 3
    assert body["taken"] == []


def test_booking_creates_reservation_and_ticket(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    response = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1", "A2"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["seats"] == ["A1", "A2"]
    assert body["total"] == 20.0
    assert body["ticket_code"]
    seats = client.get(f"/api/screenings/{_future_id(db)}/seats").json()
    assert sorted(seats["taken"]) == ["A1", "A2"]


def test_double_booking_same_seat_rejected(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    first = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1"]},
    )
    assert first.status_code == 201
    login(client, "user2@grandcinema.fr", "User123!")
    second = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1"]},
    )
    assert second.status_code == 409


def test_booking_invalid_seat_rejected(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    response = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["Z99"]},
    )
    assert response.status_code == 400


def test_booking_past_screening_rejected(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    response = client.post(
        "/api/bookings",
        json={"screening_id": _past_id(db), "seats": ["A1"]},
    )
    assert response.status_code == 400


def test_booking_requires_auth(client, db):
    response = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1"]},
    )
    assert response.status_code == 401


def test_cancel_frees_seat_for_rebooking(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    created = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1"]},
    ).json()
    cancel = client.post(f"/api/bookings/{created['reservation_id']}/cancel")
    assert cancel.status_code == 200
    seats = client.get(f"/api/screenings/{_future_id(db)}/seats").json()
    assert seats["taken"] == []
    rebook = client.post(
        "/api/bookings",
        json={"screening_id": _future_id(db), "seats": ["A1"]},
    )
    assert rebook.status_code == 201
