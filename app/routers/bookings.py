"""Routes de réservation et de billets.

Point central du projet : la réservation est atomique et la contrainte
unique (séance, place) en base interdit toute double réservation, même
lorsque deux requêtes arrivent simultanément (voir docs/BUGFIX.md).
"""

import io
import re
import time

import segno
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_admin, get_current_user
from app.models import Film, Reservation, ReservationSeat, Screening, Ticket, User
from app.security import generate_ticket_code

router = APIRouter(prefix="/api", tags=["bookings"])

_SEAT_RE = re.compile(r"^([A-Z]+)(\d+)$")


def parse_seat(label: str, rows: int, cols: int) -> tuple[int, int] | None:
    """Valide une place (ex. ``C12``) dans un plan rangées x colonnes.

    Retourne (indice_rangée, indice_siège) ou None si hors plan.
    """
    match = _SEAT_RE.match(label.strip().upper())
    if not match:
        return None
    letters, number = match.group(1), int(match.group(2))
    row_index = 0
    for char in letters:
        row_index = row_index * 26 + (ord(char) - ord("A") + 1)
    row_index -= 1
    if row_index < 0 or row_index >= rows or number < 1 or number > cols:
        return None
    return row_index, number


def cancel_reservation(db: Session, reservation: Reservation) -> None:
    """Annule une réservation et libère ses places (lignes supprimées)."""
    for seat in list(reservation.seats):
        db.delete(seat)
    reservation.status = "cancelled"
    if reservation.ticket is not None:
        reservation.ticket.status = "cancelled"
    db.commit()


class BookingBody(BaseModel):
    screening_id: int
    seats: list[str]


@router.get("/screenings/{screening_id}/seats")
def get_seats(screening_id: int, db: Session = Depends(get_db)) -> dict:
    """Plan de salle d'une séance : dimensions, places prises, prix."""
    screening = (
        db.query(Screening)
        .join(Film)
        .filter(Screening.id == screening_id, Film.is_published.is_(True))
        .first()
    )
    if screening is None:
        raise HTTPException(status_code=404, detail="Séance introuvable.")
    taken = [
        row[0]
        for row in db.query(ReservationSeat.seat_label)
        .filter(ReservationSeat.screening_id == screening_id)
        .all()
    ]
    return {
        "screening_id": screening.id,
        "film_title": screening.film.title,
        "room_name": screening.room.name,
        "room_type": screening.room.room_type,
        "start_time": screening.start_time.isoformat(),
        "price": screening.price,
        "rows": screening.room.rows,
        "cols": screening.room.cols,
        "capacity": screening.room.capacity,
        "taken": taken,
    }


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Réserve des places pour une séance (transaction atomique)."""
    from datetime import datetime

    screening = (
        db.query(Screening)
        .join(Film)
        .filter(
            Screening.id == body.screening_id,
            Film.is_published.is_(True),
        )
        .first()
    )
    if screening is None:
        raise HTTPException(status_code=404, detail="Séance introuvable.")
    if screening.start_time <= datetime.now():
        raise HTTPException(status_code=400, detail="La séance est déjà passée.")
    labels: list[str] = []
    seen: set[str] = set()
    for raw in body.seats:
        label = raw.strip().upper()
        if label in seen:
            raise HTTPException(
                status_code=400, detail=f"Place en double dans la demande : {label}."
            )
        seen.add(label)
        if parse_seat(label, screening.room.rows, screening.room.cols) is None:
            raise HTTPException(
                status_code=400, detail=f"Place invalide pour cette salle : {label}."
            )
        labels.append(label)
    if not labels:
        raise HTTPException(status_code=400, detail="Aucune place sélectionnée.")

    reservation = None
    for attempt in range(5):
        try:
            reservation = Reservation(
                user_id=user.id, screening_id=screening.id, status="confirmed"
            )
            db.add(reservation)
            db.flush()
            for label in labels:
                db.add(
                    ReservationSeat(
                        reservation_id=reservation.id,
                        screening_id=screening.id,
                        seat_label=label,
                    )
                )
            code = generate_ticket_code()
            while db.query(Ticket).filter(Ticket.code == code).first():
                code = generate_ticket_code()
            db.add(Ticket(reservation_id=reservation.id, code=code, status="valid"))
            db.commit()
            break
        except IntegrityError:
            # La contrainte unique (séance, place) a refusé la réservation :
            # une des places a été prise entre-temps.
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Une ou plusieurs places sont déjà réservées.",
            )
        except OperationalError as exc:
            # SQLite : verrou transitoire en cas d'écritures concurrentes.
            db.rollback()
            if "locked" in str(exc).lower() and attempt < 4:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise HTTPException(
                status_code=503,
                detail="La base est momentanément indisponible, réessayez.",
            )
    assert reservation is not None
    db.refresh(reservation)
    return {
        "reservation_id": reservation.id,
        "ticket_code": reservation.ticket.code if reservation.ticket else None,
        "screening_id": screening.id,
        "seats": labels,
        "total": round(len(labels) * screening.price, 2),
        "status": reservation.status,
    }


@router.get("/bookings/me")
def my_bookings(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    """Réservations de l'utilisateur connecté."""
    reservations = (
        db.query(Reservation)
        .filter(Reservation.user_id == user.id)
        .order_by(Reservation.created_at.desc())
        .all()
    )
    return [_reservation_payload(r) for r in reservations]


def _reservation_payload(reservation: Reservation) -> dict:
    screening = reservation.screening
    return {
        "id": reservation.id,
        "status": reservation.status,
        "user_email": reservation.user.email,
        "screening_id": screening.id,
        "film_title": screening.film.title,
        "room_name": screening.room.name,
        "start_time": screening.start_time.isoformat(),
        "price": screening.price,
        "seats": [seat.seat_label for seat in reservation.seats],
        "total": round(len(reservation.seats) * screening.price, 2),
        "ticket_code": reservation.ticket.code if reservation.ticket else None,
        "ticket_status": reservation.ticket.status if reservation.ticket else None,
        "created_at": reservation.created_at.isoformat(),
    }


@router.post("/bookings/{reservation_id}/cancel")
def cancel_my_booking(
    reservation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Annule une réservation (propriétaire ou administrateur)."""
    reservation = (
        db.query(Reservation).filter(Reservation.id == reservation_id).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Réservation introuvable.")
    if reservation.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé.")
    if reservation.status == "cancelled":
        raise HTTPException(status_code=400, detail="Réservation déjà annulée.")
    cancel_reservation(db, reservation)
    return {"detail": "Réservation annulée.", "id": reservation.id}


def _accessible_ticket(code: str, db: Session, user: User) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.code == code.upper()).first()
    if ticket is None or (
        ticket.reservation.user_id != user.id and user.role != "admin"
    ):
        raise HTTPException(status_code=404, detail="Billet introuvable.")
    return ticket


@router.get("/tickets/{code}")
def get_ticket(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Détail d'un billet à partir de son code (le code fait office de secret)."""
    ticket = _accessible_ticket(code, db, user)
    payload = _reservation_payload(ticket.reservation)
    payload.pop("user_email", None)
    payload["ticket_code"] = ticket.code
    payload["ticket_status"] = ticket.status
    return payload


@router.get("/tickets/{code}/qr.png")
def ticket_qr(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Image QR du billet (PNG, générée avec segno)."""
    ticket = _accessible_ticket(code, db, user)
    qr = segno.make(f"GRAND-CINEMA:{ticket.code}")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=6, border=2)
    return Response(content=buffer.getvalue(), media_type="image/png")


@router.post("/tickets/{code}/use")
def use_ticket(
    code: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    """Marque un billet comme utilisé (contrôle à l'entrée, admin)."""
    ticket = db.query(Ticket).filter(Ticket.code == code.upper()).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Billet introuvable.")
    if ticket.status != "valid":
        raise HTTPException(
            status_code=400, detail=f"Billet non valide (statut : {ticket.status})."
        )
    ticket.status = "used"
    db.commit()
    return {"detail": "Billet validé.", "code": ticket.code}
