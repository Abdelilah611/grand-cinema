"""Application FastAPI Le Grand Cinéma."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.main_helpers import static_dir
from app.routers import admin, auth, bookings, films, pages
from app.seed import seed


def initialize_database() -> None:
    """Create missing tables and add backward-compatible film columns."""
    Base.metadata.create_all(bind=engine)
    existing = {column["name"] for column in inspect(engine).get_columns("films")}
    additions = {
        "release_date": "DATE",
        "age_rating": "VARCHAR(30) NOT NULL DEFAULT 'Tous publics'",
        "language": "VARCHAR(100) NOT NULL DEFAULT 'Français'",
        "cast_names": "TEXT NOT NULL DEFAULT ''",
        "trailer_url": "VARCHAR(500) NOT NULL DEFAULT ''",
        # Existing films were public before the publication flag existed.
        "is_published": "BOOLEAN NOT NULL DEFAULT TRUE",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE films ADD COLUMN {name} {definition}")
                )
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Le Grand Cinéma",
    description=(
        "Application web de réservation de places : films, séances, "
        "réservations en ligne et billets dématérialisés."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")
app.include_router(auth.router)
app.include_router(films.router)
app.include_router(bookings.router)
app.include_router(admin.router)
app.include_router(pages.router)
