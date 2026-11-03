"""Petits utilitaires partagés (chemins du projet)."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def templates_dir() -> Path:
    return BASE_DIR / "templates"


def static_dir() -> Path:
    return BASE_DIR / "static"
