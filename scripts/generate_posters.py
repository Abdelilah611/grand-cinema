"""Génère les affiches des films (SVG locaux, aucune dépendance externe).

Chaque affiche est un dégradé de couleurs avec le titre du film, son genre
et son année. Usage : ``python scripts/generate_posters.py``.
"""

import os
import xml.sax.saxutils as sax

FILMS = [
    ("Le Dernier Métro de Minuit", "Drame", "2025", "#1f3864", "#5b7fa6"),
    ("Jazz sous les Étoiles", "Musical", "2026", "#7b2d26", "#c0392b"),
    ("L'Île aux Murmures", "Aventure", "2024", "#145a32", "#27ae60"),
    ("Comédie de la Gare", "Comédie", "2025", "#7d6608", "#f1c40f"),
    ("Les Ombres de la Ville", "Policier", "2026", "#1b2631", "#5d6d7e"),
    ("Voyage au Bout du Rêve", "Science-fiction", "2025", "#4a235a", "#8e44ad"),
]

TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="400" height="600" fill="url(#g)"/>
  <circle cx="200" cy="210" r="90" fill="white" opacity="0.15"/>
  <text x="200" y="225" font-family="sans-serif" font-size="64" fill="white" text-anchor="middle">🎬</text>
  <text x="200" y="400" font-family="sans-serif" font-size="30" font-weight="bold" fill="white" text-anchor="middle">{title1}</text>
  <text x="200" y="440" font-family="sans-serif" font-size="30" font-weight="bold" fill="white" text-anchor="middle">{title2}</text>
  <text x="200" y="490" font-family="sans-serif" font-size="20" fill="white" opacity="0.9" text-anchor="middle">{genre} - {year}</text>
  <text x="200" y="560" font-family="sans-serif" font-size="16" fill="white" opacity="0.8" text-anchor="middle">LE GRAND CINÉMA</text>
</svg>
"""


def split_title(title: str) -> tuple[str, str]:
    """Coupe un titre en deux lignes équilibrées."""
    words = title.split()
    if len(words) <= 2:
        return title, ""
    mid = len(words) // 2
    return " ".join(words[:mid]), " ".join(words[mid:])


def main() -> None:
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "posters",
    )
    os.makedirs(out_dir, exist_ok=True)
    for index, (title, genre, year, c1, c2) in enumerate(FILMS, start=1):
        line1, line2 = split_title(title)
        svg = TEMPLATE.format(
            c1=c1,
            c2=c2,
            title1=sax.escape(line1),
            title2=sax.escape(line2),
            genre=sax.escape(genre),
            year=year,
        )
        path = os.path.join(out_dir, f"film{index}.svg")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        print(f"Généré : {path}")


if __name__ == "__main__":
    main()
