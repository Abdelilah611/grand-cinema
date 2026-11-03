"""Dépendances d'authentification FastAPI."""

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


def _read_token(request: Request, access_token: str | None) -> str | None:
    """Lit le jeton depuis le cookie, sinon depuis l'en-tête Authorization."""
    if access_token:
        return access_token
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def get_optional_user(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Retourne l'utilisateur connecté, ou None (pages publiques)."""
    token = _read_token(request, access_token)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


def get_current_user(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Exige un utilisateur connecté, sinon 401."""
    user = get_optional_user(request, access_token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Exige un administrateur, sinon 403."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )
    return user
