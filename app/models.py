"""Modèles de données (SQLAlchemy).

Socle : utilisateurs, films, salles, séances.
Branche ``feature/reservation`` : réservations, places réservées, billets.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    DateTime,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow_naive() -> datetime:
    """UTC timestamp kept naive for compatibility with existing SQLite rows."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """Utilisateur de la plateforme (rôle ``user`` ou ``admin``)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)

    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="user", cascade="all, delete-orphan"
    )


class Film(Base):
    """Film à l'affiche."""

    __tablename__ = "films"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    genre: Mapped[str] = mapped_column(String(100), default="")
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    synopsis: Mapped[str] = mapped_column(Text, default="")
    director: Mapped[str] = mapped_column(String(255), default="")
    release_year: Mapped[int] = mapped_column(Integer, default=0)
    poster: Mapped[str] = mapped_column(String(255), default="")
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    age_rating: Mapped[str] = mapped_column(String(30), default="Tous publics")
    language: Mapped[str] = mapped_column(String(100), default="Français")
    cast_names: Mapped[str] = mapped_column(Text, default="")
    trailer_url: Mapped[str] = mapped_column(String(500), default="")
    is_published: Mapped[bool] = mapped_column(default=False, nullable=False)

    screenings: Mapped[list["Screening"]] = relationship(
        "Screening", back_populates="film", cascade="all, delete-orphan"
    )


class Room(Base):
    """Salle du cinéma (capacité découpée en rangées x sièges)."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    room_type: Mapped[str] = mapped_column(String(50), default="Standard")
    capacity: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)

    screenings: Mapped[list["Screening"]] = relationship(
        "Screening", back_populates="room", cascade="all, delete-orphan"
    )


class Screening(Base):
    """Séance : un film, dans une salle, à une date et un prix."""

    __tablename__ = "screenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[float] = mapped_column(Float, default=11.0)

    film: Mapped[Film] = relationship("Film", back_populates="screenings")
    room: Mapped[Room] = relationship("Room", back_populates="screenings")
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="screening", cascade="all, delete-orphan"
    )


class Reservation(Base):
    """Réservation d'un utilisateur pour une séance."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    screening_id: Mapped[int] = mapped_column(ForeignKey("screenings.id"))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)

    user: Mapped[User] = relationship("User", back_populates="reservations")
    screening: Mapped[Screening] = relationship(
        "Screening", back_populates="reservations"
    )
    seats: Mapped[list["ReservationSeat"]] = relationship(
        "ReservationSeat", back_populates="reservation", cascade="all, delete-orphan"
    )
    ticket: Mapped["Ticket | None"] = relationship(
        "Ticket",
        back_populates="reservation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ReservationSeat(Base):
    """Une place réservée dans une séance.

    La contrainte unique (séance, place) est la protection centrale
    contre la double réservation : la base refuse toute seconde
    insertion de la même place pour la même séance, même en concurrence.
    """

    __tablename__ = "reservation_seats"
    __table_args__ = (
        UniqueConstraint("screening_id", "seat_label", name="uq_screening_seat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"))
    screening_id: Mapped[int] = mapped_column(ForeignKey("screenings.id"))
    seat_label: Mapped[str] = mapped_column(String(10))

    reservation: Mapped[Reservation] = relationship(
        "Reservation", back_populates="seats"
    )


class Ticket(Base):
    """Billet électronique d'une réservation (QR code)."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id"), unique=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)

    reservation: Mapped[Reservation] = relationship(
        "Reservation", back_populates="ticket"
    )
