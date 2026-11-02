"""Configuration pytest : base SQLite temporaire isolée par test.

La variable DATABASE_URL est fixée AVANT l'import de l'application, de
sorte que le moteur SQLAlchemy des tests pointe vers un fichier
temporaire, jamais vers la base de développement.
"""

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["COOKIE_SECURE"] = "false"

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import Film, Room, Screening, User
from app.security import hash_password


def _seed_minimal(db):
    """Jeu de données minimal et déterministe pour les tests."""
    admin = User(
        email="admin@grandcinema.fr",
        hashed_password=hash_password("Admin123!"),
        full_name="Administrateur Démo",
        role="admin",
    )
    user = User(
        email="user@grandcinema.fr",
        hashed_password=hash_password("User123!"),
        full_name="Utilisateur Démo",
        role="user",
    )
    user2 = User(
        email="user2@grandcinema.fr",
        hashed_password=hash_password("User123!"),
        full_name="Deuxième Utilisateur",
        role="user",
    )
    db.add_all([admin, user, user2])
    film = Film(
        title="Film Test",
        genre="Drame",
        duration_min=100,
        synopsis="Film de test.",
        director="Test",
        release_year=2025,
        poster="film1.svg",
        is_published=True,
    )
    room = Room(name="Salle Test", room_type="Standard", capacity=6, rows=2, cols=3)
    db.add_all([film, room])
    db.commit()
    future = Screening(
        film_id=film.id,
        room_id=room.id,
        start_time=datetime.now() + timedelta(days=1),
        price=10.0,
    )
    past = Screening(
        film_id=film.id,
        room_id=room.id,
        start_time=datetime.now() - timedelta(days=1),
        price=10.0,
    )
    db.add_all([future, past])
    db.commit()
    return {"film": film, "room": room, "future": future, "past": past}


@pytest.fixture()
def db():
    """Recrée les tables et le jeu minimal avant chaque test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        data = _seed_minimal(session)
        yield session, data
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """Client de test avec la dépendance get_db branchée sur la base test."""

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client, email, password):
    """Connecte un utilisateur et retourne la réponse (le cookie est gardé)."""
    return client.post("/api/auth/login", json={"email": email, "password": password})
