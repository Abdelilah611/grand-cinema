"""Routes de réservation et de billets.

Point central du projet : la réservation est atomique et la contrainte
unique (séance, place) en base interdit toute double réservation, même
lorsque deux requêtes arrivent simultanément (voir docs/BUGFIX.md).
"""
from xml.sax.saxutils import escape

from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as PDFImage,
)
import io
import re
import time

import segno
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_current_admin,
    get_current_customer,
    get_current_user,
    get_optional_user,
)
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
def get_seats(
    screening_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Plan de salle d'une séance : dimensions, places prises, prix."""
    if user is not None and user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les places sont réservées aux comptes clients.",
        )
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
    user: User = Depends(get_current_customer),
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
    # PostgreSQL may return timezone-aware datetimes (for example when the
    # existing column is TIMESTAMP WITH TIME ZONE), while SQLite and older
    # schemas return naive values. Compare like with like to avoid a TypeError
    # when a customer confirms a booking.
    now = (
        datetime.now(screening.start_time.tzinfo)
        if screening.start_time.tzinfo is not None
        else datetime.now()
    )
    if screening.start_time <= now:
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
    db: Session = Depends(get_db), user: User = Depends(get_current_customer)
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
    user: User = Depends(get_current_customer),
) -> dict:
    """Annule une réservation appartenant à l'utilisateur client connecté."""
    reservation = (
        db.query(Reservation).filter(Reservation.id == reservation_id).first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Réservation introuvable.")
    if reservation.user_id != user.id:
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


def _ticket_display_status(ticket: Ticket) -> str:
    """Treat any ticket on a non-confirmed reservation as cancelled."""
    if ticket.reservation.status != "confirmed" or ticket.status == "cancelled":
        return "cancelled"
    return ticket.status


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
    payload["ticket_status"] = _ticket_display_status(ticket)
    return payload


@router.get("/tickets/{code}/qr.png")
def ticket_qr(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_customer),
) -> Response:
    """Image QR du billet (PNG, générée avec segno)."""
    ticket = _accessible_ticket(code, db, user)
    qr = segno.make(f"GRAND-CINEMA:{ticket.code}")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=6, border=2)
    return Response(content=buffer.getvalue(), media_type="image/png")

@router.get("/tickets/{code}/pdf")
def download_ticket_pdf(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_customer),
) -> Response:
    """Génère et télécharge le billet électronique en PDF."""

    # Vérifier les droits d'accès au billet
    ticket = _accessible_ticket(code, db, user)

    reservation = ticket.reservation
    screening = reservation.screening
    film = screening.film
    room = screening.room

    # Générer le QR code avec le même contenu que le QR PNG existant
    qr = segno.make(f"GRAND-CINEMA:{ticket.code}")
    qr_buffer = io.BytesIO()
    qr.save(qr_buffer, kind="png", scale=6, border=2)
    qr_buffer.seek(0)

    # Créer le PDF en mémoire
    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Billet - {film.title}",
        author="Le Grand Cinéma",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CinemaTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#DDAF16"),
            spaceAfter=8 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="MovieTitle",
            parent=styles["Heading1"],
            fontSize=19,
            leading=24,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#202333"),
            spaceAfter=5 * mm,
        )
    )

    story = [
        Paragraph("LE GRAND CINÉMA", styles["CinemaTitle"]),
        Paragraph("BILLET ÉLECTRONIQUE", styles["Heading2"]),
        Spacer(1, 4 * mm),
        Paragraph(escape(film.title), styles["MovieTitle"]),
        Paragraph(
            f"{escape(room.name)} — {escape(room.room_type)}",
            styles["Normal"],
        ),
        Spacer(1, 8 * mm),
    ]

    date_text = screening.start_time.strftime("%d/%m/%Y à %H:%M")
    seats = sorted(seat.seat_label for seat in reservation.seats)
    total = len(seats) * screening.price

    ticket_status_label = {
        "valid": "VALIDE",
        "used": "DÉJÀ UTILISÉ",
        "cancelled": "ANNULÉ",
    }.get(_ticket_display_status(ticket), "NON VALIDE")
    reservation_status_label = (
        "CONFIRMÉE" if reservation.status == "confirmed" else "ANNULÉE"
    )
    rows = [
        ["INFORMATION", "DÉTAIL"],
        ["Film", Paragraph(escape(film.title), styles["Normal"])],
        ["Séance", date_text],
        ["Salle", escape(room.name)],
        ["Type de salle", escape(room.room_type)],
        ["Places", ", ".join(escape(s) for s in seats)],
        ["Prix total", f"{total:.2f} EUR"],
        ["Code du billet", ticket.code],
        ["Statut du billet", ticket_status_label],
        ["Statut de réservation", reservation_status_label],
    ]

    table = Table(rows, colWidths=[48 * mm, 100 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#202333")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F4F5F8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DCE5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )

    story.extend(
        [
            table,
            Spacer(1, 10 * mm),
            Paragraph("QR CODE DU BILLET", styles["Heading2"]),
            Spacer(1, 3 * mm),
            PDFImage(qr_buffer, width=42 * mm, height=42 * mm),
            Spacer(1, 4 * mm),
            Paragraph(
                "Présentez ce QR code à l'entrée. "
                "La validation doit être effectuée par un administrateur.",
                styles["Normal"],
            ),
        ]
    )

    document.build(story)
    pdf_buffer.seek(0)

    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="billet-{ticket.code}.pdf"'
            ),
            "Cache-Control": "no-store",
        },
    )
@router.post("/tickets/{code}/use")
def use_ticket(
    code: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    """Atomically mark a confirmed reservation's valid ticket as used."""
    updated = (
        db.query(Ticket)
        .filter(
            Ticket.code == code.upper(),
            Ticket.status == "valid",
            Ticket.reservation.has(Reservation.status == "confirmed"),
        )
        .update({Ticket.status: "used"}, synchronize_session=False)
    )
    if updated == 1:
        db.commit()
        return {"detail": "Billet validé.", "code": code.upper()}

    # A failed conditional update is either an unknown, used, or cancelled ticket.
    # Roll back before reading its current state, including after a concurrent winner.
    db.rollback()
    ticket = db.query(Ticket).filter(Ticket.code == code.upper()).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Billet introuvable.")
    if ticket.status == "used":
        raise HTTPException(status_code=400, detail="Billet déjà utilisé.")
    if ticket.status == "cancelled" or ticket.reservation.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Billet annulé : réservation non confirmée, entrée refusée.",
        )
    if ticket.status != "valid":
        raise HTTPException(
            status_code=400, detail=f"Billet non valide (statut : {ticket.status})."
        )
    # The reservation was confirmed but the conditional update did not transition
    # the ticket, so refuse entry rather than assuming a valid state.
    raise HTTPException(status_code=409, detail="Le billet n'a pas pu être validé.")
