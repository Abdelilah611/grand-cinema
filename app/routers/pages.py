"""Pages HTML publiques (rendues avec Jinja2)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.dependencies import get_optional_user
from app.main_helpers import templates_dir
from app.models import Film, Reservation, ReservationSeat, Screening, Ticket, User
from app.routers.auth import (
    authenticate_credentials,
    register_user,
    set_auth_cookie,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(templates_dir()))


def _context(user: User | None, **extra) -> dict:
    context = {"user": user}
    context.update(extra)
    return context


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Page d'accueil : liste des films et leurs affiches."""
    films = db.query(Film).filter(Film.is_published.is_(True)).order_by(Film.title).all()
    return templates.TemplateResponse(
        request, "index.html", _context(user, films=films)
    )


@router.get("/films/{film_id}", response_class=HTMLResponse)
def film_detail(
    request: Request,
    film_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Page de détail d'un film et calendrier de ses séances."""
    film = db.query(Film).filter(Film.id == film_id, Film.is_published.is_(True)).first()
    if film is None:
        return templates.TemplateResponse(
            request, "404.html", _context(user), status_code=404
        )
    screenings = (
        db.query(Screening)
        .filter(
            Screening.film_id == film_id,
            Screening.start_time >= datetime.now(),
        )
        .order_by(Screening.start_time)
        .all()
    )
    by_day: dict[str, list[Screening]] = {}
    for screening in screenings:
        by_day.setdefault(screening.start_time.strftime("%Y-%m-%d"), []).append(
            screening
        )
    return templates.TemplateResponse(
        request,
        "film_detail.html",
        _context(user, film=film, by_day=by_day),
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    """Page de connexion."""
    return templates.TemplateResponse(request, "login.html", _context(user))


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Progressive-enhancement fallback for browsers where the JS handler fails."""
    try:
        user = authenticate_credentials(db, email, password)
    except SQLAlchemyError:
        return templates.TemplateResponse(
            request,
            "login.html",
            _context(None, login_error="Connexion temporairement indisponible. Réessayez."),
            status_code=503,
        )
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            _context(
                None,
                login_error="E-mail ou mot de passe incorrect.",
                login_email=email,
            ),
            status_code=401,
        )
    destination = "/admin" if user.role == "admin" else "/"
    response = RedirectResponse(url=destination, status_code=303)
    set_auth_cookie(response, user)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(get_optional_user)):
    """Page d'inscription."""
    return templates.TemplateResponse(request, "register.html", _context(user))


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Progressive-enhancement fallback for the JSON registration form."""
    try:
        register_user(db, email, password, full_name)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            _context(None, register_error=exc.detail, register_email=email),
            status_code=exc.status_code,
        )
    except SQLAlchemyError:
        return templates.TemplateResponse(
            request,
            "register.html",
            _context(
                None,
                register_error="Inscription temporairement indisponible. Réessayez.",
                register_email=email,
            ),
            status_code=503,
        )
    return RedirectResponse(url="/login?registered=1", status_code=303)


@router.get("/seances/{screening_id}", response_class=HTMLResponse)
def screening_page(
    request: Request,
    screening_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Page de choix des places pour une séance."""
    if user is not None and user.role == "admin":
        return RedirectResponse(url="/admin", status_code=303)
    screening = (
        db.query(Screening).join(Film).filter(
            Screening.id == screening_id, Film.is_published.is_(True)
        ).first()
    )
    if screening is None:
        return templates.TemplateResponse(
            request, "404.html", _context(user), status_code=404
        )
    taken = [
        row[0]
        for row in db.query(ReservationSeat.seat_label)
        .filter(ReservationSeat.screening_id == screening_id)
        .all()
    ]
    return templates.TemplateResponse(
        request,
        "screening.html",
        _context(
            user,
            screening=screening,
            taken=taken,
            rows=screening.room.rows,
            cols=screening.room.cols,
        ),
    )


@router.get("/mes-billets", response_class=HTMLResponse)
def my_tickets_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Page des billets de l'utilisateur connecté."""
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.role == "admin":
        return RedirectResponse(url="/admin", status_code=303)
    reservations = (
        db.query(Reservation)
        .filter(Reservation.user_id == user.id)
        .order_by(Reservation.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request, "my_tickets.html", _context(user, reservations=reservations)
    )


@router.get("/billets/{code}", response_class=HTMLResponse)
def ticket_page(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Page d'un billet électronique (QR code)."""
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.role == "admin":
        return RedirectResponse(url="/admin", status_code=303)
    ticket = db.query(Ticket).filter(Ticket.code == code.upper()).first()
    if ticket is None or (
        ticket.reservation.user_id != user.id and user.role != "admin"
    ):
        return templates.TemplateResponse(
            request, "404.html", _context(user), status_code=404
        )
    return templates.TemplateResponse(
        request, "ticket_detail.html", _context(user, ticket=ticket)
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request, user: User | None = Depends(get_optional_user)
):
    """Page d'administration (réservée aux administrateurs)."""
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "admin.html", _context(user))


@router.get("/admin/check-ticket", response_class=HTMLResponse)
def admin_check_ticket_page(
    request: Request, user: User | None = Depends(get_optional_user)
):
    """Page de contrôle à l'entrée, accessible uniquement aux administrateurs."""
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "admin_check_ticket.html", _context(user)
    )
