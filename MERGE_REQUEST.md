# Merge Request : feature/reservation → develop

## Titre

feat(reservation) : réservation sécurisée, billets QR et administration

## Description

Cette merge request ajoute la fonctionnalité complète de réservation
du Grand Cinéma, au-dessus du socle déjà présent sur `develop`
(authentification, catalogue de films et séances, documentation API).

### Contenu

- **Modèles** : `Reservation`, `ReservationSeat` et `Ticket`
  (contrainte unique sur `(screening_id, seat_label)`), relations
  restaurées sur `User` et `Screening`.
- **Réservation sécurisée** : création en transaction atomique ;
  place déjà prise → **409** ; verrou SQLite transitoire → reprise
  jusqu'à 5 fois puis **503**. Annulation libérant les places.
- **Plan de salle** : page séance avec sélection des sièges,
  places prises grisées, total calculé en direct.
- **Billets électroniques** : page billet + QR code PNG (segno),
  validation à l'entrée réservée aux administrateurs.
- **Espace admin** : statistiques (global, par film, par salle,
  par séance), CRUD films / salles / séances, gestion des
  réservations.
- **Documentation du bug de concurrence** dans `docs/BUGFIX.md`.
- **Déploiement** : `Dockerfile` + `render.yaml` + section dédiée
  dans le README.

### Sécurité

- Mots de passe hachés (PBKDF2-HMAC-SHA256), jamais en clair.
- Accès admin vérifié par rôle (403 sinon).
- Une place ne peut être vendue qu'une seule fois par séance,
  même en cas de requêtes simultanées.

## Checklist

- [x] Page d'accueil et détails films fonctionnels
- [x] Plan de salle et sélection des sièges
- [x] Réservation avec protection anti-double réservation
- [x] Billet électronique avec QR code
- [x] Espace admin : CRUD + statistiques
- [x] Tests pytest + couverture
- [x] `ruff check` propre
- [x] README détaillé en français
- [x] Dockerfile + render.yaml

## Tests

```bash
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term --cov-report=html
ruff check app tests scripts
```

Résultats observés : **24 tests passent**, couverture **76 %**,
`ruff check` propre. Le test `tests/test_concurrency.py` prouve que
deux réservations simultanées de la même place n'en créent qu'une
seule (une réponse 201, une réponse 409).

## Points restants (hors périmètre de cette MR)

- Paiement réel (la réservation simule le paiement).
- Poussée vers GitHub et déploiement Render : préparés, à exécuter
  avec un compte connecté (commandes dans le README).
