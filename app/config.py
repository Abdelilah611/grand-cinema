"""Configuration de l'application Le Grand Cinéma.

Les paramètres sont lus depuis les variables d'environnement, avec des
valeurs par défaut adaptées au développement local (SQLite).
"""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_DIR / "grand_cinema.db"


class Settings:
    """Paramètres de l'application."""

    database_url: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
    )
    secret_key: str = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-me-in-production-32-chars"
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 heures
    cookie_secure: bool = os.environ.get("COOKIE_SECURE", "true").lower() not in {
        "0", "false", "no", "off"
    }

    @property
    def sqlalchemy_url(self) -> str:
        """URL SQLAlchemy (Render fournit postgres://, SQLAlchemy veut postgresql://)."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


settings = Settings()
