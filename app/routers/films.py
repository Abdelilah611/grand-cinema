"""Routes publiques : films et séances."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Film, Room, Screening

router = APIRouter(prefix="/api", tags=["films"])


def _film_payload(film: Film) -> dict:
    return {
        "id": film.id,
        "title": film.title,
        "genre": film.genre,
        "duration_min": film.duration_min,
        "synopsis": film.synopsis,
        "director": film.director,
        "release_year": film.release_year,
        "poster": film.poster,
        "release_date": film.release_date.isoformat() if film.release_date else None,
        "age_rating": film.age_rating,
        "language": film.language,
        "cast": film.cast_names,
        "trailer_url": film.trailer_url,
    }


def _screening_payload(screening: Screening) -> dict:
    return {
        "id": screening.id,
        "film_id": screening.film_id,
        "film_title": screening.film.title,
        "room_id": screening.room_id,
        "room_name": screening.room.name,
        "room_type": screening.room.room_type,
        "start_time": screening.start_time.isoformat(),
        "price": screening.price,
    }


@router.get("/films")
def list_films(db: Session = Depends(get_db)) -> list[dict]:
    """Liste tous les films à l'affiche."""
    films = db.query(Film).filter(Film.is_published.is_(True)).order_by(Film.title).all()
    return [_film_payload(film) for film in films]


@router.get("/films/{film_id}")
def get_film(film_id: int, db: Session = Depends(get_db)) -> dict:
    """Détail d'un film avec ses séances à venir."""
    film = db.query(Film).filter(Film.id == film_id, Film.is_published.is_(True)).first()
    if film is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    screenings = (
        db.query(Screening)
        .filter(
            Screening.film_id == film_id,
            Screening.start_time >= datetime.now(),
        )
        .order_by(Screening.start_time)
        .all()
    )
    payload = _film_payload(film)
    payload["screenings"] = [_screening_payload(s) for s in screenings]
    return payload


@router.get("/screenings")
def list_screenings(
    film_id: int | None = None,
    date: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Liste les séances à venir, filtrables par film et par jour (AAAA-MM-JJ)."""
    query = db.query(Screening).join(Film).filter(
        Screening.start_time >= datetime.now(), Film.is_published.is_(True)
    )
    if film_id is not None:
        query = query.filter(Screening.film_id == film_id)
    if date is not None:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Format de date invalide.")
        query = query.filter(
            Screening.start_time >= datetime.combine(day, datetime.min.time()),
            Screening.start_time < datetime.combine(day, datetime.max.time()),
        )
    screenings = query.order_by(Screening.start_time).all()
    return [_screening_payload(s) for s in screenings]


@router.get("/screenings/{screening_id}")
def get_screening(screening_id: int, db: Session = Depends(get_db)) -> dict:
    """Détail d'une séance."""
    screening = (
        db.query(Screening).join(Film).filter(
            Screening.id == screening_id, Film.is_published.is_(True)
        ).first()
    )
    if screening is None:
        raise HTTPException(status_code=404, detail="Séance introuvable.")
    return _screening_payload(screening)


@router.get("/rooms")
def list_rooms(db: Session = Depends(get_db)) -> list[dict]:
    """Liste les salles du cinéma."""
    rooms = db.query(Room).order_by(Room.id).all()
    return [
        {
            "id": room.id,
            "name": room.name,
            "room_type": room.room_type,
            "capacity": room.capacity,
            "rows": room.rows,
            "cols": room.cols,
        }
        for room in rooms
    ]
