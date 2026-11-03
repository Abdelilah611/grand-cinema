"""Sécurité : hachage des mots de passe et jetons JWT.

Le hachage utilise PBKDF2-HMAC-SHA256 de la bibliothèque standard
(200 000 itérations, sel aléatoire) : aucun mot de passe n'est stocké
en clair. Les jetons sont signés avec PyJWT (HS256).
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

_HASH_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Retourne ``sel_hex$empreinte_hex`` pour un mot de passe."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _HASH_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son empreinte stockée."""
    try:
        salt_hex, digest_hex = hashed.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), _HASH_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(user_id: int, role: str) -> str:
    """Crée un JWT portant l'identifiant et le rôle de l'utilisateur."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """Décode un JWT, ou retourne None si invalide ou expiré."""
    try:
        return jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except jwt.PyJWTError:
        return None


def generate_ticket_code() -> str:
    """Génère un code de billet unique (12 caractères hexadécimaux)."""
    return secrets.token_hex(16).upper()
