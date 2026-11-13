"""Test de concurrence : deux réservations simultanées de la même place.

Ce test prouve la correction du bug documenté dans docs/BUGFIX.md : sans
la contrainte unique (séance, place), deux requêtes simultanées
créeraient deux réservations pour la même place. Avec la contrainte,
une seule réussit (201) et l'autre est rejetée (409).
"""

import threading

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ReservationSeat
from tests.conftest import login


def test_concurrent_booking_same_seat_creates_only_one(client, db):
    screening_id = db[1]["future"].id
    results = []
    errors = []
    barrier = threading.Barrier(2)

    def attempt(email):
        try:
            with TestClient(app, raise_server_exceptions=False) as thread_client:
                login(thread_client, email, "User123!")
                barrier.wait(timeout=10)
                response = thread_client.post(
                    "/api/bookings",
                    json={"screening_id": screening_id, "seats": ["B2"]},
                )
                results.append(response.status_code)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=attempt, args=("user@grandcinema.fr",)),
        threading.Thread(target=attempt, args=("user2@grandcinema.fr",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [201, 409]
    session = SessionLocal()
    try:
        count = (
            session.query(ReservationSeat)
            .filter(
                ReservationSeat.screening_id == screening_id,
                ReservationSeat.seat_label == "B2",
            )
            .count()
        )
    finally:
        session.close()
    assert count == 1
