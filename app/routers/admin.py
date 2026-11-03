"""Routes d'administration : statistiques, CRUD et réservations."""

from datetime import date, datetime
from pathlib import Path
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import get_db
from app.dependencies import get_current_admin
from app.models import Film, Reservation, ReservationSeat, Room, Screening, Ticket, User
from app.main_helpers import static_dir
from app.routers.bookings import _reservation_payload, cancel_reservation

router = APIRouter(prefix="/api/admin", tags=["admin"])
Admin = get_current_admin


def _fill_rate(reserved: int, capacity: int) -> float:
    if capacity <= 0:
        return 0.0
    return round(100.0 * reserved / capacity, 1)


@router.get("/stats")
def stats(db: Session = Depends(get_db), admin: User = Depends(Admin)) -> dict:
    """Statistiques de fréquentation et taux de remplissage."""
    confirmed = db.query(Reservation).filter(Reservation.status == "confirmed").all()
    cancelled_count = db.query(Reservation).filter(Reservation.status == "cancelled").count()
    total_seats = sum(len(r.seats) for r in confirmed)
    total_revenue = round(
        sum(len(r.seats) * r.screening.price for r in confirmed), 2
    )
    screenings = db.query(Screening).all()
    total_capacity = sum(s.room.capacity for s in screenings)
    total_reserved = (
        db.query(ReservationSeat).join(Reservation).filter(
            Reservation.status == "confirmed"
        ).count()
    )

    per_film = []
    for film in db.query(Film).order_by(Film.title).all():
        film_screenings = [s for s in screenings if s.film_id == film.id]
        capacity = sum(s.room.capacity for s in film_screenings)
        reserved = sum(
            len(r.seats) for r in confirmed if r.screening.film_id == film.id
        )
        revenue = round(
            sum(
                len(r.seats) * r.screening.price
                for r in confirmed
                if r.screening.film_id == film.id
            ),
            2,
        )
        per_film.append(
            {
                "film_id": film.id,
                "title": film.title,
                "reservations": sum(
                    1 for r in confirmed if r.screening.film_id == film.id
                ),
                "seats": reserved,
                "revenue": revenue,
                "fill_rate": _fill_rate(reserved, capacity),
            }
        )

    per_room = []
    for room in db.query(Room).order_by(Room.id).all():
        room_screenings = [s for s in screenings if s.room_id == room.id]
        capacity = sum(s.room.capacity for s in room_screenings)
        reserved = sum(
            len(r.seats) for r in confirmed if r.screening.room_id == room.id
        )
        per_room.append(
            {
                "room_id": room.id,
                "name": room.name,
                "seats": reserved,
                "fill_rate": _fill_rate(reserved, capacity),
            }
        )

    per_screening = []
    for screening in sorted(screenings, key=lambda s: s.start_time):
        reserved = sum(
            len(r.seats)
            for r in confirmed
            if r.screening_id == screening.id
        )
        per_screening.append(
            {
                "screening_id": screening.id,
                "film_title": screening.film.title,
                "room_name": screening.room.name,
                "start_time": screening.start_time.isoformat(),
                "capacity": screening.room.capacity,
                "reserved": reserved,
                "fill_rate": _fill_rate(reserved, screening.room.capacity),
                "revenue": round(reserved * screening.price, 2),
            }
        )

    return {
        "total_reservations": len(confirmed),
        "cancelled_reservations": cancelled_count,
        "tickets_sold": db.query(Ticket).filter(Ticket.status.in_(("valid", "used"))).count(),
        "total_seats": total_seats,
        "total_revenue": total_revenue,
        "global_fill_rate": _fill_rate(total_reserved, total_capacity),
        "per_film": per_film,
        "per_room": per_room,
        "per_screening": per_screening,
    }


class FilmBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    genre: str = Field(default="", max_length=100)
    duration_min: int = Field(default=0, ge=0, le=1000)
    synopsis: str = Field(default="", max_length=10000)
    director: str = Field(default="", max_length=255)
    release_year: int = Field(default=0, ge=0, le=2200)
    poster: str = Field(default="film1.svg", max_length=255)
    release_date: date | None = None
    age_rating: str = Field(default="Tous publics", max_length=30)
    language: str = Field(default="Français", max_length=100)
    cast_names: str = Field(default="", max_length=2000)
    trailer_url: str = Field(default="", max_length=500)
    is_published: bool = False

def _film_payload(film: Film) -> dict:
    return {
        "id": film.id, "title": film.title, "genre": film.genre,
        "duration_min": film.duration_min, "synopsis": film.synopsis,
        "director": film.director, "release_year": film.release_year,
        "poster": film.poster,
        "release_date": (
            film.release_date.isoformat() if film.release_date else None
        ),
        "age_rating": film.age_rating, "language": film.language,
        "cast": film.cast_names, "trailer_url": film.trailer_url,
        "is_published": film.is_published,
    }


async def _film_request_data(request: Request) -> tuple[dict, UploadFile | None]:
    if "application/json" in request.headers.get("content-type", ""):
        return await request.json(), None
    form = await request.form()
    data, poster_file = {}, None
    for key, value in form.multi_items():
        if key == "poster_file" and isinstance(value, UploadFile) and value.filename:
            poster_file = value
        elif isinstance(value, str):
            data[key] = value
    return data, poster_file


def _validate_trailer_url(value: str) -> None:
    if value:
        parsed = urlparse(value)
        youtube_hosts = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
        if parsed.scheme != "https" or parsed.hostname not in youtube_hosts:
            raise HTTPException(
                status_code=422,
                detail="L'URL de la bande-annonce doit être un lien YouTube HTTPS valide.",
            )


async def _save_poster(upload: UploadFile) -> str:
    allowed = {
        "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
        "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
        "image/gif": (b"GIF8", ".gif"),
        "image/webp": (b"RIFF", ".webp"),
    }
    spec = allowed.get(upload.content_type or "")
    content = await upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="L'affiche ne doit pas dépasser 5 Mo.")
    valid_magic = spec and content.startswith(spec[0])
    if upload.content_type == "image/webp":
        valid_magic = valid_magic and content[8:12] == b"WEBP"
    if not valid_magic:
        raise HTTPException(
            status_code=400,
            detail="Format d'affiche invalide. Utilisez JPEG, PNG, GIF ou WebP.",
        )
    directory = static_dir() / "uploads" / "films"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(16)}{spec[1]}"
    (directory / filename).write_bytes(content)
    return f"uploads/films/{filename}"


class RoomBody(BaseModel):
    name: str
    room_type: str = "Standard"
    capacity: int
    rows: int
    cols: int


class ScreeningBody(BaseModel):
    film_id: int
    room_id: int
    start_time: datetime
    price: float = 11.0


@router.get("/films")
def admin_list_films(db: Session = Depends(get_db), admin: User = Depends(Admin)):
    return [_film_payload(f) for f in db.query(Film).order_by(Film.id).all()]


@router.post("/films", status_code=201)
async def admin_create_film(
    request: Request, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    data, poster_file = await _film_request_data(request)
    try:
        body = FilmBody.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    _validate_trailer_url(body.trailer_url)
    fields = body.model_dump()
    if poster_file:
        fields["poster"] = await _save_poster(poster_file)
    elif fields["poster"].startswith(("/", "\\")) or ".." in Path(fields["poster"]).parts:
        raise HTTPException(status_code=422, detail="Chemin d'affiche invalide.")
    film = Film(**fields)
    db.add(film)
    db.commit()
    db.refresh(film)
    return _film_payload(film)


@router.put("/films/{film_id}")
async def admin_update_film(
    film_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(Admin),
):
    film = db.query(Film).filter(Film.id == film_id).first()
    if film is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    data, poster_file = await _film_request_data(request)
    try:
        body = FilmBody.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    _validate_trailer_url(body.trailer_url)
    fields = body.model_dump()
    if poster_file:
        fields["poster"] = await _save_poster(poster_file)
    elif fields["poster"].startswith(("/", "\\")) or ".." in Path(fields["poster"]).parts:
        raise HTTPException(status_code=422, detail="Chemin d'affiche invalide.")
    for key, value in fields.items():
        setattr(film, key, value)
    db.commit()
    db.refresh(film)
    return _film_payload(film)


@router.post("/films/{film_id}/publish")
def admin_publish_film(film_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)):
    film = db.query(Film).filter(Film.id == film_id).first()
    if film is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    film.is_published = True
    db.commit()
    return {"id": film.id, "is_published": True}


@router.post("/films/{film_id}/unpublish")
def admin_unpublish_film(film_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)):
    film = db.query(Film).filter(Film.id == film_id).first()
    if film is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    film.is_published = False
    db.commit()
    return {"id": film.id, "is_published": False}


@router.delete("/films/{film_id}")
def admin_delete_film(
    film_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    film = db.query(Film).filter(Film.id == film_id).first()
    if film is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    if film.screenings:
        raise HTTPException(
            status_code=409,
            detail="Ce film possède des séances. Supprimez-les avant de supprimer le film.",
        )
    db.delete(film)
    db.commit()
    return {"detail": "Film supprimé."}


@router.get("/rooms")
def admin_list_rooms(db: Session = Depends(get_db), admin: User = Depends(Admin)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "room_type": r.room_type,
            "capacity": r.capacity,
            "rows": r.rows,
            "cols": r.cols,
        }
        for r in db.query(Room).order_by(Room.id).all()
    ]


@router.post("/rooms", status_code=201)
def admin_create_room(
    body: RoomBody, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    if body.rows * body.cols != body.capacity:
        raise HTTPException(
            status_code=400,
            detail="La capacité doit être égale à rangées x sièges par rangée.",
        )
    room = Room(**body.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "name": room.name}


@router.put("/rooms/{room_id}")
def admin_update_room(
    room_id: int,
    body: RoomBody,
    db: Session = Depends(get_db),
    admin: User = Depends(Admin),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Salle introuvable.")
    if body.rows * body.cols != body.capacity:
        raise HTTPException(
            status_code=400,
            detail="La capacité doit être égale à rangées x sièges par rangée.",
        )
    if room.screenings and (room.rows, room.cols) != (body.rows, body.cols):
        raise HTTPException(
            status_code=409,
            detail="Le plan de la salle ne peut pas changer tant que des séances y sont liées.",
        )
    for key, value in body.model_dump().items():
        setattr(room, key, value)
    db.commit()
    return {"id": room.id, "name": room.name}


@router.delete("/rooms/{room_id}")
def admin_delete_room(
    room_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Salle introuvable.")
    if room.screenings:
        raise HTTPException(
            status_code=409,
            detail="Cette salle possède des séances. Supprimez-les avant la salle.",
        )
    db.delete(room)
    db.commit()
    return {"detail": "Salle supprimée."}


@router.get("/screenings")
def admin_list_screenings(db: Session = Depends(get_db), admin: User = Depends(Admin)):
    return [
        {
            "id": s.id,
            "film_id": s.film_id,
            "film_title": s.film.title,
            "room_id": s.room_id,
            "room_name": s.room.name,
            "start_time": s.start_time.isoformat(),
            "price": s.price,
        }
        for s in db.query(Screening).order_by(Screening.start_time).all()
    ]


@router.post("/screenings", status_code=201)
def admin_create_screening(
    body: ScreeningBody, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    if db.query(Film).filter(Film.id == body.film_id).first() is None:
        raise HTTPException(status_code=404, detail="Film introuvable.")
    if db.query(Room).filter(Room.id == body.room_id).first() is None:
        raise HTTPException(status_code=404, detail="Salle introuvable.")
    screening = Screening(**body.model_dump())
    db.add(screening)
    db.commit()
    db.refresh(screening)
    return {"id": screening.id}


@router.delete("/screenings/{screening_id}")
def admin_delete_screening(
    screening_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if screening is None:
        raise HTTPException(status_code=404, detail="Séance introuvable.")
    if screening.reservations:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cette séance possède un historique de réservations et ne peut pas "
                "être supprimée."
            ),
        )
    db.delete(screening)
    db.commit()
    return {"detail": "Séance supprimée."}


@router.get("/bookings")
def admin_list_bookings(db: Session = Depends(get_db), admin: User = Depends(Admin)):
    reservations = (
        db.query(Reservation).order_by(Reservation.created_at.desc()).all()
    )
    return [_reservation_payload(r) for r in reservations]


@router.post("/bookings/{reservation_id}/cancel")
def admin_cancel_booking(
    reservation_id: int, db: Session = Depends(get_db), admin: User = Depends(Admin)
):
    reservation = (
        db.query(Reservation).filter(Reservation.id == reservation_id).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Réservation introuvable.")
    if reservation.status == "cancelled":
        raise HTTPException(status_code=400, detail="Réservation déjà annulée.")
    cancel_reservation(db, reservation)
    return {"detail": "Réservation annulée.", "id": reservation.id}
