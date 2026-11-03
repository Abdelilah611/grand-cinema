# Documentation de l'API — Le Grand Cinéma

La documentation interactive (Swagger UI) est générée automatiquement
par FastAPI et disponible sur **`/docs`** (et `/redoc`). Ce document
résume les endpoints principaux.

Base : `http://127.0.0.1:8000`

L'authentification utilise un JWT posé dans un cookie HttpOnly
(`access_token`) lors de la connexion. Les appels API peuvent aussi
envoyer l'en-tête `Authorization: Bearer <token>`.

## Authentification

| Méthode | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | — | Crée un compte (`email`, `password`, `full_name`). Rôle `user`. |
| POST | `/api/auth/login` | — | Connecte l'utilisateur, pose le cookie JWT. |
| POST | `/api/auth/logout` | — | Supprime le cookie. |
| GET | `/api/auth/me` | Connecté | Profil de l'utilisateur connecté. |

## Films et séances (public)

| Méthode | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/films` | Liste des films à l'affiche. |
| GET | `/api/films/{id}` | Détail d'un film avec ses séances à venir. |
| GET | `/api/screenings?film_id=&date=AAAA-MM-JJ` | Séances à venir, filtrables par film et par jour. |
| GET | `/api/screenings/{id}` | Détail d'une séance. |
| GET | `/api/screenings/{id}/seats` | Plan de salle : rangées, colonnes, places prises, prix. |
| GET | `/api/rooms` | Liste des salles. |

## Réservations et billets (connecté)

| Méthode | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/bookings` | Crée une réservation. Corps : `{"screening_id": 1, "seats": ["A1", "A2"]}`. Une place déjà prise retourne **409**. |
| GET | `/api/bookings/me` | Réservations de l'utilisateur connecté. |
| POST | `/api/bookings/{id}/cancel` | Annule une réservation (propriétaire ou admin), libère les places. |
| GET | `/api/tickets/{code}` | Détail d'un billet par son code. |
| GET | `/api/tickets/{code}/qr.png` | Image QR du billet (PNG). |
| POST | `/api/tickets/{code}/use` | Marque un billet comme utilisé (admin). |

## Administration (rôle `admin` requis)

| Méthode | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/admin/stats` | Statistiques : réservations, revenus, taux de remplissage global, par film, par salle et par séance. |
| GET/POST | `/api/admin/films` | Liste / création de films. |
| PUT/DELETE | `/api/admin/films/{id}` | Modification / suppression d'un film. |
| GET/POST | `/api/admin/rooms` | Liste / création de salles. |
| PUT/DELETE | `/api/admin/rooms/{id}` | Modification / suppression d'une salle. |
| GET/POST | `/api/admin/screenings` | Liste / création de séances. |
| DELETE | `/api/admin/screenings/{id}` | Suppression d'une séance. |
| GET | `/api/admin/bookings` | Liste des réservations. |
| POST | `/api/admin/bookings/{id}/cancel` | Annulation d'une réservation par l'admin. |

## Codes de statut

- `200` : succès. `201` : ressource créée.
- `400` : requête invalide (place hors plan, séance passée...).
- `401` : authentification requise. `403` : administrateur requis.
- `404` : ressource introuvable.
- `409` : conflit, la place est déjà réservée pour cette séance.
- `503` : base temporairement verrouillée (SQLite en forte concurrence).
