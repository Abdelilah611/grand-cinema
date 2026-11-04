"""Importe dans PostgreSQL/Neon les anciennes affiches stockées sur le disque.

Pour chaque film dont ``poster_data`` est vide et dont ``poster`` pointe vers
``uploads/films/...``, lit le fichier dans ``static/`` et le copie dans la base.
Les fichiers introuvables sont listés (ils doivent être ré-uploadés via l'admin).

Usage (idempotent, peut être relancé) :
    DATABASE_URL="postgresql://...neon..." python scripts/import_posters_to_db.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, engine  # noqa: E402
from app.models import Film  # noqa: E402

SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
)


def detect_type(data: bytes) -> str | None:
    for magic, mime in SIGNATURES:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def main() -> None:
    print("Base utilisée :", engine.url.render_as_string(hide_password=True))
    imported, missing = 0, []
    with SessionLocal() as db:
        films = db.query(Film).filter(Film.has_poster_data.is_(False)).all()
        for film in films:
            if not film.poster or not film.poster.startswith("uploads/"):
                continue
            path = (ROOT / "static" / film.poster).resolve()
            if ROOT / "static" not in path.parents or not path.is_file():
                missing.append((film.id, film.title, film.poster))
                continue
            data = path.read_bytes()
            mime = detect_type(data)
            if mime is None or len(data) > 5 * 1024 * 1024:
                missing.append((film.id, film.title, f"{film.poster} (format/taille invalide)"))
                continue
            film.poster_data, film.poster_content_type, film.poster = data, mime, ""
            imported += 1
        db.commit()
    print(f"{imported} affiche(s) importée(s).")
    for film_id, title, poster in missing:
        print(f"  À ré-uploader : #{film_id} {title} ({poster})")


if __name__ == "__main__":
    main()
