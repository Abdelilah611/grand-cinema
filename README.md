# 🎬 Le Grand Cinéma

Application web de réservation de places de cinéma : consultation des
films et des séances, plan de salle avec sélection des sièges,
réservation sécurisée contre la double réservation, billet électronique
avec QR code, et espace d'administration avec statistiques de
fréquentation.

Projet inspiré de l'énoncé d'examen « Le Grand Cinéma » : 10 salles,
1 700 places (2 salles Premium/IMAX de 300 places, 4 Standard de 180,
2 VIP de 120, 2 Événementielles modulables de 70).

## Fonctionnalités

- **Accueil** : liste des films avec affiches générées localement (SVG).
- **Détail d'un film** : synopsis, durée, réalisateur, séances à venir
  par jour et par salle.
- **Inscription / connexion** : comptes utilisateurs avec rôles
  `user` et `admin` (JWT en cookie HttpOnly).
- **Plan de salle** : places générées depuis la capacité de la salle
  (ex. 300 = 15 rangées × 20 sièges), places prises grisées, sélection
  au clic.
- **Réservation sécurisée** : contrainte unique en base sur
  (séance, place) + transaction atomique — deux réservations
  simultanées de la même place ne créent qu'une seule réservation
  (voir `docs/BUGFIX.md`).
- **Billet électronique** : page billet avec QR code (PNG téléchargeable).
- **Administration** : CRUD films, salles, séances ; gestion des
  réservations ; tableau de bord (fréquentation et taux de remplissage
  global, par film, par salle et par séance).
- **Documentation API** : Swagger automatique sur `/docs`
  (+ résumé dans `docs/API.md`).

## Stack technique

- **Backend** : Python 3.12, FastAPI, SQLAlchemy, JWT (PyJWT).
- **Frontend** : HTML / CSS / JavaScript (templates Jinja2 servis par
  FastAPI), aucune dépendance externe.
- **Base de données** : SQLite par défaut (`grand_cinema.db`),
  PostgreSQL possible via `DATABASE_URL`.
- La base SQLite par défaut est résolue depuis le dossier du projet,
  même si Uvicorn est lancé depuis un autre répertoire. `COOKIE_SECURE`
  vaut `true` par défaut pour protéger le cookie de session en HTTPS ;
  mettez `COOKIE_SECURE=false` uniquement pour un serveur local en HTTP.
- **QR codes** : segno (pur Python).
- **Mots de passe** : PBKDF2-HMAC-SHA256 (stdlib), jamais en clair.
- **Tests** : pytest + pytest-cov. **Qualité** : ruff.

## Arborescence

```
grand-cinema/
├── app/                  # Code de l'application
│   ├── main.py           # Point d'entrée FastAPI
│   ├── config.py         # Configuration (DATABASE_URL, SECRET_KEY)
│   ├── database.py       # Moteur SQLAlchemy, session
│   ├── models.py         # Modèles : User, Film, Room, Screening,
│   │                     #   Reservation, ReservationSeat, Ticket
│   ├── security.py       # Hachage PBKDF2, JWT, codes de billet
│   ├── dependencies.py   # Authentification (user / admin)
│   ├── seed.py           # Données de démonstration
│   └── routers/          # auth, films, bookings, admin, pages
├── templates/            # Pages Jinja2 (accueil, film, séance, billets, admin)
├── static/               # CSS, JavaScript, affiches SVG
├── tests/                # Tests pytest (auth, réservation, concurrence,
│                         #   billets, admin)
├── docs/                 # API.md, BUGFIX.md
├── scripts/              # Génération des affiches SVG
├── requirements.txt      # Dépendances de production
├── requirements-dev.txt  # pytest, pytest-cov, httpx, ruff
├── pyproject.toml        # Configuration ruff et couverture
├── Dockerfile            # Image Docker de production
├── render.yaml           # Déploiement Render (web + PostgreSQL)
└── MERGE_REQUEST.md      # Merge request feature/reservation → develop
```

## Installation

```bash
cd grand-cinema
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pour le développement (tests, lint) :

```bash
pip install -r requirements-dev.txt
```

## Lancement

```bash
uvicorn app.main:app --reload
```

Puis ouvrir :

- Application : <http://127.0.0.1:8000>
- Documentation API (Swagger) : <http://127.0.0.1:8000/docs>

Au premier démarrage, la base SQLite `grand_cinema.db` est créée et
remplie avec les données de démonstration (10 salles, 6 films, séances
sur 7 jours).

## Comptes de démonstration

| Rôle | E-mail | Mot de passe |
|------|--------|--------------|
| Administrateur | admin@grandcinema.fr | Admin123! |
| Utilisateur | user@grandcinema.fr | User123! |

Ces comptes sont créés automatiquement par le seed et rappelés sur la
page de connexion.

## Gestion des films

Connectez-vous avec un compte administrateur puis ouvrez `/admin` et
l'onglet **Films**. Le formulaire permet de créer une fiche avec son titre,
sa description, son genre, son réalisateur, sa distribution, sa durée, sa
date de sortie, sa classification, sa langue et une URL de bande-annonce
YouTube. Les affiches acceptées sont JPEG, PNG, GIF et WebP, jusqu'à 5 Mo;
elles sont stockées dans `static/uploads/films/`.

Les nouveaux films sont enregistrés en brouillon par défaut. Utilisez
**Publier** ou choisissez **Publié** dans le formulaire pour les afficher
sur l'accueil, `/api/films` et leur page de détail. Les brouillons restent
visibles dans l'administration uniquement. Les anciens films présents dans
une base existante sont conservés et restent publiés lors de la mise à jour
du schéma.

## Configuration de la base de données

Par défaut, SQLite est utilisé (`sqlite:///./grand_cinema.db`).
Pour PostgreSQL, définir la variable d'environnement `DATABASE_URL` :

```bash
export DATABASE_URL="postgresql://utilisateur:motdepasse@hote:5432/grand_cinema"
uvicorn app.main:app
```

Les URL commençant par `postgres://` (format Render/Heroku) sont
converties automatiquement en `postgresql://`.

Autres variables :

- `SECRET_KEY` : clé de signature des JWT (une clé de développement
  est utilisée par défaut — **à définir en production**).

## Tests et couverture

```bash
pytest --cov=app --cov-report=term --cov-report=html
```

Le rapport HTML est généré dans `htmlcov/`. La suite couvre
l'authentification, la réservation, la prévention de la double
réservation (y compris un test de concurrence avec threads),
les billets et les statistiques admin.

## Qualité du code

```bash
ruff check app tests scripts
```

La configuration ruff est dans `pyproject.toml` (longueur de ligne
100, règles E et F, deux exceptions justifiées en commentaire :
gabarit SVG insécable et import après fixation de `DATABASE_URL`
dans `tests/conftest.py`).

## Déploiement

Le projet est prêt pour un déploiement en une étape sur Render
(`render.yaml` : service web + base PostgreSQL) ou via Docker :

```bash
docker build -t grand-cinema .
docker run -p 8000:8000 -e SECRET_KEY="une-cle-longue-et-secrete" grand-cinema
```

Penser à définir `SECRET_KEY` et `DATABASE_URL` en production.

## Git et publication sur GitHub

Branches : `main` (socle stable), `develop` (intégration),
`feature/reservation` (fonctionnalité complète, fusionnée dans
`develop` avec `git merge --no-ff`). Pour publier (nécessite un
compte GitHub connecté) :

```bash
git remote add origin https://github.com/<utilisateur>/grand-cinema.git
git push -u origin main develop feature/reservation
```

Puis ouvrir la merge request `feature/reservation` → `develop` en
reprenant le contenu de `MERGE_REQUEST.md`.

## Bug de concurrence corrigé

Voir `docs/BUGFIX.md` : sans protection, deux requêtes simultanées
peuvent vendre deux fois la même place. Correction : contrainte
unique `(screening_id, seat_label)` + transaction atomique + reprise
en cas de verrou SQLite. Le test `tests/test_concurrency.py` prouve
que deux réservations simultanées de la même place n'en créent
qu'une seule (201 + 409).
