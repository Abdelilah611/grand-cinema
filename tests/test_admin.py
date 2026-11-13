"""Tests de l'administration : statistiques, CRUD, accès réservé."""

from datetime import datetime, timedelta

from tests.conftest import login


def test_stats_requires_admin(client):
    login(client, "user@grandcinema.fr", "User123!")
    assert client.get("/api/admin/stats").status_code == 403
    login(client, "admin@grandcinema.fr", "Admin123!")
    response = client.get("/api/admin/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_reservations"] == 0
    assert body["global_fill_rate"] == 0.0
    assert len(body["per_film"]) == 1
    assert len(body["per_room"]) == 1


def test_stats_reflect_bookings(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    client.post(
        "/api/bookings",
        json={"screening_id": db[1]["future"].id, "seats": ["A1", "A2"]},
    )
    login(client, "admin@grandcinema.fr", "Admin123!")
    stats = client.get("/api/admin/stats").json()
    assert stats["total_reservations"] == 1
    assert stats["total_seats"] == 2
    assert stats["total_revenue"] == 20.0
    assert stats["per_film"][0]["reservations"] == 1
    assert stats["per_film"][0]["seats"] == 2
    assert stats["per_film"][0]["revenue"] == 20.0
    assert stats["per_film"][0]["fill_rate"] == 16.7
    assert stats["per_room"][0]["seats"] == 2
    assert stats["per_room"][0]["fill_rate"] == 16.7
    future_stats = next(
        item for item in stats["per_screening"] if item["screening_id"] == db[1]["future"].id
    )
    assert future_stats["reserved"] == 2
    assert future_stats["revenue"] == 20.0
    assert future_stats["fill_rate"] == 33.3
    # 2 places vendues sur 2 séances de 6 places chacune (12 au total).
    assert stats["global_fill_rate"] == 16.7


def test_stats_explain_cancelled_reservations(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = client.post(
        "/api/bookings",
        json={"screening_id": db[1]["future"].id, "seats": ["A1"]},
    ).json()
    client.post(f"/api/bookings/{booking['reservation_id']}/cancel")
    login(client, "admin@grandcinema.fr", "Admin123!")
    stats = client.get("/api/admin/stats").json()
    assert stats["total_reservations"] == 0
    assert stats["cancelled_reservations"] == 1
    assert stats["tickets_sold"] == 0


def test_room_and_screening_history_cannot_be_cascaded(client, db):
    login(client, "admin@grandcinema.fr", "Admin123!")
    room_id = db[1]["room"].id
    screening_id = db[1]["future"].id
    room_delete = client.delete(f"/api/admin/rooms/{room_id}")
    assert room_delete.status_code == 409
    login(client, "user@grandcinema.fr", "User123!")
    reservation = client.post(
        "/api/bookings",
        json={"screening_id": screening_id, "seats": ["A1"]},
    )
    assert reservation.status_code == 201
    login(client, "admin@grandcinema.fr", "Admin123!")
    screening_delete = client.delete(f"/api/admin/screenings/{screening_id}")
    assert screening_delete.status_code == 409
    bookings = client.get("/api/admin/bookings").json()
    assert len(bookings) == 1
    assert bookings[0]["status"] == "confirmed"
    assert bookings[0]["ticket_status"] == "valid"


def test_admin_crud_film(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    created = client.post(
        "/api/admin/films",
        json={"title": "Nouveau Film", "genre": "Comédie", "duration_min": 90},
    )
    assert created.status_code == 201
    film_id = created.json()["id"]
    updated = client.put(
        f"/api/admin/films/{film_id}",
        json={"title": "Film Renommé", "genre": "Comédie", "duration_min": 95},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Film Renommé"
    deleted = client.delete(f"/api/admin/films/{film_id}")
    assert deleted.status_code == 200
    remaining_ids = [f["id"] for f in client.get("/api/films").json()]
    assert film_id not in remaining_ids


def test_admin_room_capacity_must_match_grid(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    response = client.post(
        "/api/admin/rooms",
        json={
            "name": "Salle Incohérente",
            "room_type": "Standard",
            "capacity": 100,
            "rows": 2,
            "cols": 3,
        },
    )
    assert response.status_code == 400


def test_admin_can_manage_rooms_and_screenings(client, db):
    login(client, "admin@grandcinema.fr", "Admin123!")
    room = client.post(
        "/api/admin/rooms",
        json={
            "name": "Salle créée",
            "room_type": "Standard",
            "capacity": 4,
            "rows": 2,
            "cols": 2,
        },
    )
    assert room.status_code == 201
    room_id = room.json()["id"]

    updated_room = client.put(
        f"/api/admin/rooms/{room_id}",
        json={
            "name": "Salle modifiée",
            "room_type": "VIP",
            "capacity": 4,
            "rows": 2,
            "cols": 2,
        },
    )
    assert updated_room.status_code == 200
    assert updated_room.json()["name"] == "Salle modifiée"

    screening = client.post(
        "/api/admin/screenings",
        json={
            "film_id": db[1]["film"].id,
            "room_id": room_id,
            "start_time": (datetime.now() + timedelta(days=2)).isoformat(),
            "price": 18.0,
        },
    )
    assert screening.status_code == 201
    screening_id = screening.json()["id"]
    listed = client.get("/api/admin/screenings").json()
    assert any(item["id"] == screening_id for item in listed)

    deleted_screening = client.delete(f"/api/admin/screenings/{screening_id}")
    assert deleted_screening.status_code == 200
    remaining = client.get("/api/admin/screenings").json()
    assert all(item["id"] != screening_id for item in remaining)
    deleted_room = client.delete(f"/api/admin/rooms/{room_id}")
    assert deleted_room.status_code == 200


def test_admin_lists_bookings(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    client.post(
        "/api/bookings",
        json={"screening_id": db[1]["future"].id, "seats": ["A1"]},
    )
    login(client, "admin@grandcinema.fr", "Admin123!")
    bookings = client.get("/api/admin/bookings").json()
    assert len(bookings) == 1
    assert bookings[0]["user_email"] == "user@grandcinema.fr"


def test_admin_can_cancel_booking_and_repeat_is_rejected(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    created = client.post(
        "/api/bookings",
        json={"screening_id": db[1]["future"].id, "seats": ["A1"]},
    )
    assert created.status_code == 201
    reservation_id = created.json()["reservation_id"]

    login(client, "admin@grandcinema.fr", "Admin123!")
    cancelled = client.post(f"/api/admin/bookings/{reservation_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["id"] == reservation_id

    repeated = client.post(f"/api/admin/bookings/{reservation_id}/cancel")
    assert repeated.status_code == 400
    booking = client.get("/api/admin/bookings").json()[0]
    assert booking["status"] == "cancelled"
    assert booking["ticket_status"] == "cancelled"
