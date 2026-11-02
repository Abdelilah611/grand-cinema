"""Tests de l'administration : statistiques, CRUD, accès réservé."""

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
    client.post(
        "/api/bookings",
        json={"screening_id": screening_id, "seats": ["A1"]},
    )
    screening_delete = client.delete(f"/api/admin/screenings/{screening_id}")
    assert screening_delete.status_code == 409
    assert client.get("/api/admin/bookings").json()


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
