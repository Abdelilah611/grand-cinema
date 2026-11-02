"""Données de démonstration : les 10 salles de l'énoncé, 6 films fictifs,
des séances sur les 7 prochains jours et les comptes de démonstration.

Le peuplement est idempotent : il ne crée rien si les tables contiennent
déjà des données.
"""

from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import Film, Room, Screening, User
from app.security import hash_password

ROOMS = [
    # (nom, type, capacité, rangées, sièges par rangée)
    ("IMAX 1", "Premium", 300, 15, 20),
    ("IMAX 2", "Premium", 300, 15, 20),
    ("Standard 1", "Standard", 180, 12, 15),
    ("Standard 2", "Standard", 180, 12, 15),
    ("Standard 3", "Standard", 180, 12, 15),
    ("Standard 4", "Standard", 180, 12, 15),
    ("VIP 1", "VIP", 120, 10, 12),
    ("VIP 2", "VIP", 120, 10, 12),
    ("Modulable A", "Événementielle", 70, 7, 10),
    ("Modulable B", "Événementielle", 70, 7, 10),
]

PRICE_BY_TYPE = {"Premium": 15.0, "Standard": 11.0, "VIP": 18.0, "Événementielle": 10.0}

FILMS = [
    {
        "title": "Le Dernier Métro de Minuit",
        "genre": "Drame",
        "duration_min": 118,
        "director": "Claire Vasseur",
        "release_year": 2025,
        "poster": "uploads/films/Le Dernier Métro de Minuit.png",
        "is_published": True,
        "synopsis": (
            "Dans une ville qui ne dort jamais, une conductrice de métro "
            "découvre, lors de sa dernière ronde, un passager qui semble "
            "connaître son passé mieux qu'elle-même. Un drame nocturne sur "
            "la mémoire et les secondes chances."
        ),
    },
    {
        "title": "Jazz sous les Étoiles",
        "genre": "Musical",
        "duration_min": 104,
        "director": "Mehdi Larbi",
        "release_year": 2026,
        "poster": "uploads/films/Jazz sous les étoiles _ affiche du festival.png",
        "is_published": True,
        "synopsis": (
            "En pleine semaine du festival de Jazz, une jeune trompettiste "
            "venue d'ailleurs croise un pianiste de bar. Entre scènes "
            "improvisées et nuits blanches, la ville entière se met à swinguer."
        ),
    },
    {
        "title": "L'Île aux Murmures",
        "genre": "Aventure",
        "duration_min": 132,
        "director": "Anaïs Roche",
        "release_year": 2024,
        "poster": "uploads/films/ile-aux-murmures.png",
        "is_published": True,
        "synopsis": (
            "Une cartographe hérite d'une carte incomplète menant à une île "
            "que personne n'a jamais retrouvée deux fois. Elle embarque avec "
            "un équipage improbable pour percer le secret des murmures."
        ),
    },
    {
        "title": "Comédie de la Gare",
        "genre": "Comédie",
        "duration_min": 96,
        "director": "Théo Marchand",
        "release_year": 2025,
        "poster": "uploads/films/comedie-de-la-gare.png",
        "is_published": True,
        "synopsis": (
            "Un chef de gare maniaque, une valise échangée et un train qui "
            "n'arrive jamais à l'heure : une journée ordinaire qui déraille "
            "avec tendresse dans la plus joyeuse des gares."
        ),
    },
    {
        "title": "Les Ombres de la Ville",
        "genre": "Policier",
        "duration_min": 121,
        "director": "Sarah Benali",
        "release_year": 2026,
        "poster": "uploads/films/Les Ombres de la Ville.png",
        "is_published": True,
        "synopsis": (
            "Une enquêtrice obstinée suit la piste d'un voleur qui ne dérobe "
            "que des objets sans valeur, sauf aux yeux de leurs propriétaires. "
            "Un polar élégant dans les ruelles d'une ville de festival."
        ),
    },
    {
        "title": "Voyage au Bout du Rêve",
        "genre": "Science-fiction",
        "duration_min": 141,
        "director": "Lucas Perrin",
        "release_year": 2025,
        "poster": "uploads/films/Voyage au Bout du Rêve.png",
        "is_published": True,
        "synopsis": (
            "En 2087, une ingénieure met au point une machine capable de "
            "projeter les rêves sur grand écran. Quand les rêves d'un inconnu "
            "commencent à prédire l'avenir, tout bascule."
        ),
    },
]

DEMO_USERS = [
    ("admin@grandcinema.fr", "Admin123!", "Administrateur Démo", "admin"),
    ("user@grandcinema.fr", "User123!", "Utilisateur Démo", "user"),
]

SHOW_HOURS = [14, 17, 20]


def seed(db: Session) -> None:
    """Peuple la base si elle est vide (idempotent)."""
    if db.query(User).count() == 0:
        for email, password, full_name, role in DEMO_USERS:
            db.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    full_name=full_name,
                    role=role,
                )
            )
    if db.query(Room).count() == 0:
        for name, room_type, capacity, rows, cols in ROOMS:
            db.add(
                Room(
                    name=name,
                    room_type=room_type,
                    capacity=capacity,
                    rows=rows,
                    cols=cols,
                )
            )
    if db.query(Film).count() == 0:
        for data in FILMS:
            db.add(Film(**data))
    db.commit()

    if db.query(Screening).count() > 0:
        return
    rooms = db.query(Room).order_by(Room.id).all()
    films = db.query(Film).order_by(Film.id).all()
    now = datetime.now()
    for day_offset in range(7):
        day = (now + timedelta(days=day_offset)).date()
        for film_index, film in enumerate(films):
            room = rooms[(day_offset + film_index) % len(rooms)]
            hour = SHOW_HOURS[(day_offset + film_index) % len(SHOW_HOURS)]
            start = datetime.combine(day, time(hour=hour))
            if start <= now:
                continue
            db.add(
                Screening(
                    film_id=film.id,
                    room_id=room.id,
                    start_time=start,
                    price=PRICE_BY_TYPE[room.room_type],
                )
            )
    db.commit()
