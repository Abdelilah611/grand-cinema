"""Connexion à la base de données (SQLAlchemy).

Par défaut : SQLite (fichier ``grand_cinema.db`` à la racine du projet).
En production : PostgreSQL via la variable d'environnement ``DATABASE_URL``.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.sqlalchemy_url.startswith("sqlite"):
    # SQLite : autoriser l'accès multi-thread et patienter en cas de verrou.
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.sqlalchemy_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dépendance FastAPI : fournit une session, puis la ferme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
