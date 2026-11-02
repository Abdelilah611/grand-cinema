# Bug potentiel identifié et corrigé : double réservation en concurrence

## Le bug

Sans protection, deux utilisateurs peuvent réserver la même place pour
la même séance si leurs requêtes arrivent en même temps. Scénario :

1. L'utilisateur A demande la place A1 ; l'application vérifie qu'elle
   est libre (elle l'est).
2. Avant que la réservation de A soit enregistrée, l'utilisateur B
   demande la même place A1 ; l'application vérifie qu'elle est libre
   (elle l'est encore, la réservation de A n'est pas encore validée).
3. Les deux réservations sont enregistrées : la place A1 est vendue
   deux fois. C'est le classique problème de lecture-écriture
   concurrente (« check-then-act » non atomique).

Une simple vérification applicative (« la place est-elle libre ? »)
ne suffit donc pas : entre la vérification et l'enregistrement, l'état
peut changer.

## La correction mise en place

Deux protections complémentaires, appliquées dans
`app/routers/bookings.py` et `app/models.py` :

1. **Contrainte unique en base de données** sur la table
   `reservation_seats` : `UNIQUE (screening_id, seat_label)`. La base
   elle-même refuse toute seconde insertion de la même place pour la
   même séance, quelle que soit la concurrence. C'est la protection
   décisive, car elle ne dépend d'aucun ordre d'exécution.
2. **Transaction atomique** : la réservation, ses places et son billet
   sont créés dans une seule transaction. En cas de violation de la
   contrainte, la transaction entière est annulée (`rollback`) et
   l'API répond **409 Conflict** (« place déjà réservée »).
3. **Robustesse SQLite** : en cas de verrou transitoire
   (`database is locked`) lors d'écritures simultanées, la transaction
   est rejouée jusqu'à 5 fois avec un court délai croissant, avant de
   répondre 503 si le verrou persiste.

## Preuve par le test

`tests/test_concurrency.py` lance deux threads qui réservent la même
place de la même séance en simultané, avec deux comptes différents.
Résultat attendu et vérifié : exactement une réponse **201** et une
réponse **409**, et une seule ligne en base pour cette place.

## Ce que cela ne couvre pas

La correction garantit l'unicité d'une place par séance. Elle ne gère
pas le paiement réel (le paiement est simulé par la création de la
réservation) ni la surréservation volontaire (overbooking), qui sont
hors périmètre de ce projet.
