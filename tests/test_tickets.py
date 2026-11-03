"""Tests des billets : consultation, QR code, validation à l'entrée."""

from tests.conftest import login


def _book(client, db):
    response = client.post(
        "/api/bookings",
        json={"screening_id": db[1]["future"].id, "seats": ["A1"]},
    )
    assert response.status_code == 201
    return response.json()


def test_ticket_detail_by_code(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.get(f"/api/tickets/{booking['ticket_code']}")
    assert response.status_code == 200
    assert response.json()["seats"] == ["A1"]
    assert response.json()["ticket_status"] == "valid"


def test_ticket_qr_png(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.get(f"/api/tickets/{booking['ticket_code']}/qr.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 100
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_ticket_unknown_code_404(client):
    login(client, "user@grandcinema.fr", "User123!")
    response = client.get("/api/tickets/INCONNU123")
    assert response.status_code == 404


def test_ticket_requires_owner_or_admin(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    code = booking["ticket_code"]
    assert "user_email" not in client.get(f"/api/tickets/{code}").json()
    login(client, "user2@grandcinema.fr", "User123!")
    assert client.get(f"/api/tickets/{code}").status_code == 404
    assert client.get(f"/api/tickets/{code}/qr.png").status_code == 404
    assert client.get(f"/billets/{code}").status_code == 404


def test_ticket_use_by_admin_then_reuse_rejected(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    login(client, "admin@grandcinema.fr", "Admin123!")
    used = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert used.status_code == 200
    again = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert again.status_code == 400


def test_ticket_use_by_simple_user_forbidden(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert response.status_code == 403
