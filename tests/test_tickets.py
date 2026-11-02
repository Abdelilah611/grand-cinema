"""Tests des billets : consultation, téléchargements, validation et accès."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Ticket
from app.routers.bookings import router as bookings_router, use_ticket
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
    assert response.headers["content-type"].startswith("application/json")


def test_ticket_routes_are_registered_once_with_expected_handlers():
    expected = {
        "/api/tickets/{code}": ("get_ticket", "GET"),
        "/api/tickets/{code}/qr.png": ("ticket_qr", "GET"),
        "/api/tickets/{code}/pdf": ("download_ticket_pdf", "GET"),
        "/api/tickets/{code}/use": ("use_ticket", "POST"),
    }
    matches = {
        path: [
            route
            for route in bookings_router.routes
                if hasattr(route, "path") and route.path == path
        ]
        for path in expected
    }
    assert all(len(routes) == 1 for routes in matches.values())
    for path, (endpoint_name, method) in expected.items():
        route = matches[path][0]
        assert route.endpoint.__name__ == endpoint_name
        assert route.methods == {method}


def test_ticket_qr_png(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.get(f"/api/tickets/{booking['ticket_code']}/qr.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 100
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_ticket_pdf_download_has_pdf_content_type_and_signature(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.get(f"/api/tickets/{booking['ticket_code']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content.startswith(b"%PDF-")


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
    assert used.headers["content-type"].startswith("application/json")
    assert used.json() == {
        "detail": "Billet validé.",
        "code": booking["ticket_code"],
    }
    again = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert again.status_code == 400
    assert again.json()["detail"] == "Billet déjà utilisé."
    db[0].expire_all()
    ticket = db[0].query(Ticket).filter_by(code=booking["ticket_code"]).one()
    assert ticket.status == "used"
    assert ticket.reservation.status == "confirmed"
    assert [seat.seat_label for seat in ticket.reservation.seats] == ["A1"]
    login(client, "user@grandcinema.fr", "User123!")
    page = client.get(f"/billets/{booking['ticket_code']}")
    assert page.status_code == 200
    assert "Déjà utilisé" in page.text
    assert "/api/tickets/" + booking["ticket_code"] + "/use" not in page.text


def test_ticket_use_by_simple_user_forbidden(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    response = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert response.status_code == 403


def test_ticket_use_requires_authentication(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    client.post("/api/auth/logout")
    response = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert response.status_code == 401


def test_ticket_use_unknown_code_does_not_create_ticket(client, db):
    login(client, "admin@grandcinema.fr", "Admin123!")
    before = db[0].query(Ticket).count()
    response = client.post("/api/tickets/UNKNOWN-TICKET/use")
    assert response.status_code == 404
    assert db[0].query(Ticket).count() == before


def test_cancelled_reservation_cannot_be_validated(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    cancelled = client.post(
        f"/api/bookings/{booking['reservation_id']}/cancel"
    )
    assert cancelled.status_code == 200
    login(client, "admin@grandcinema.fr", "Admin123!")
    rejected = client.post(f"/api/tickets/{booking['ticket_code']}/use")
    assert rejected.status_code == 400
    assert "annulé" in rejected.json()["detail"].lower()
    details = client.get(f"/api/tickets/{booking['ticket_code']}")
    assert details.json()["ticket_status"] == "cancelled"
    page = client.get(f"/billets/{booking['ticket_code']}")
    assert "Annulé" in page.text
    db[0].expire_all()
    ticket = db[0].query(Ticket).filter_by(code=booking["ticket_code"]).one()
    assert ticket.status == "cancelled"


def test_simultaneous_ticket_validation_has_only_one_winner(client, db):
    login(client, "user@grandcinema.fr", "User123!")
    booking = _book(client, db)
    login(client, "admin@grandcinema.fr", "Admin123!")
    barrier = Barrier(2)
    admin = SimpleNamespace(role="admin")

    def validate():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            try:
                return use_ticket(booking["ticket_code"], session, admin)
            except HTTPException as exc:
                return exc
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: validate(), range(2)))

    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, HTTPException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 400
    assert failures[0].detail == "Billet déjà utilisé."
    db[0].expire_all()
    ticket = db[0].query(Ticket).filter_by(code=booking["ticket_code"]).one()
    assert ticket.status == "used"
