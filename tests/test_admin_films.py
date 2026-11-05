"""Film publication, access control, metadata, and poster upload coverage."""



from tests.conftest import login


def test_admin_can_manage_publication_and_metadata(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    created = client.post(
        "/api/admin/films",
        json={
            "title": "Film brouillon",
            "genre": "Drame",
            "duration_min": 108,
            "synopsis": "Description complète.",
            "director": "A. Réalisatrice",
            "release_date": "2026-11-01",
            "age_rating": "12+",
            "language": "Français",
            "cast_names": "Actrice A, Acteur B",
            "trailer_url": "https://youtu.be/abcdefghijk",
        },
    )
    assert created.status_code == 201
    film_id = created.json()["id"]
    assert created.json()["is_published"] is False
    assert client.get("/api/films").status_code == 200
    assert client.get(f"/api/films/{film_id}").status_code == 404
    assert f"/films/{film_id}" not in client.get("/").text

    updated = client.put(
        f"/api/admin/films/{film_id}",
        json={
            "title": "Film publié",
            "genre": "Drame",
            "duration_min": 110,
            "synopsis": "Description mise à jour.",
            "director": "A. Réalisatrice",
            "release_date": "2026-11-01",
            "age_rating": "12+",
            "language": "Français",
            "cast_names": "Actrice A, Acteur B",
            "trailer_url": "https://youtu.be/abcdefghijk",
            "is_published": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["cast"] == "Actrice A, Acteur B"
    assert client.post(f"/api/admin/films/{film_id}/publish").status_code == 200
    assert client.get(f"/api/films/{film_id}").json()["release_date"] == "2026-11-01"
    assert client.post(f"/api/admin/films/{film_id}/unpublish").status_code == 200
    assert client.get(f"/api/films/{film_id}").status_code == 404
    assert client.delete(f"/api/admin/films/{film_id}").status_code == 200


def test_non_admin_cannot_manage_films(client):
    login(client, "user@grandcinema.fr", "User123!")
    assert client.get("/api/admin/films").status_code == 403
    assert client.post("/api/admin/films", json={"title": "Interdit"}).status_code == 403
    assert client.put("/api/admin/films/1", json={"title": "Interdit"}).status_code == 403
    assert client.post("/api/admin/films/1/publish").status_code == 403
    assert client.delete("/api/admin/films/1").status_code == 403


def test_poster_upload_is_validated_and_saved(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    invalid = client.post(
        "/api/admin/films",
        data={"title": "Affiche invalide", "duration_min": "90"},
        files={"poster_file": ("poster.png", b"not an image", "image/png")},
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/admin/films",
        data={"title": "Affiche valide", "duration_min": "90"},
        files={"poster_file": ("poster.png", b"\x89PNG\r\n\x1a\n" + b"test", "image/png")},
    )
    assert created.status_code == 201
    film_id = created.json()["id"]
    assert created.json()["poster"] == f"/api/films/{film_id}/poster"

    # Les octets sont réellement en base, rien n'est écrit sur le disque.
    from app.database import SessionLocal
    from app.models import Film

    with SessionLocal() as db:
        film = db.get(Film, film_id)
        assert film.poster_data == b"\x89PNG\r\n\x1a\ntest"
        assert film.poster_content_type == "image/png"
        assert film.poster == ""

    served = client.get(f"/api/films/{film_id}/poster")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == b"\x89PNG\r\n\x1a\ntest"

    # Revalidation : 304 si l'affiche n'a pas changé.
    cached = client.get(
        f"/api/films/{film_id}/poster",
        headers={"If-None-Match": served.headers["etag"]},
    )
    assert cached.status_code == 304


def test_editing_film_without_new_file_keeps_db_poster(client):
    """Le formulaire admin renvoie l'URL API dans `poster` : ne doit pas échouer."""
    login(client, "admin@grandcinema.fr", "Admin123!")
    created = client.post(
        "/api/admin/films",
        data={"title": "Garde mon affiche", "duration_min": "90"},
        files={"poster_file": ("p.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    film_id = created.json()["id"]
    edited = client.put(
        f"/api/admin/films/{film_id}",
        data={
            "title": "Titre modifié",
            "duration_min": "95",
            "poster": f"/api/films/{film_id}/poster",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Titre modifié"
    assert edited.json()["poster"] == f"/api/films/{film_id}/poster"
    assert client.get(f"/api/films/{film_id}/poster").content == b"\x89PNG\r\n\x1a\nabc"


def test_public_pages_use_api_url_for_db_posters(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    created = client.post(
        "/api/admin/films",
        data={"title": "Affiche en base", "duration_min": "90", "is_published": "true"},
        files={"poster_file": ("p.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    film_id = created.json()["id"]
    assert f"/api/films/{film_id}/poster" in client.get("/").text
    assert f"/api/films/{film_id}/poster" in client.get(f"/films/{film_id}").text


def test_invalid_trailer_and_oversized_poster_are_rejected(client):
    login(client, "admin@grandcinema.fr", "Admin123!")
    invalid_url = client.post(
        "/api/admin/films",
        json={"title": "Mauvais lien", "trailer_url": "https://example.com/video"},
    )
    assert invalid_url.status_code == 422
    oversized = client.post(
        "/api/admin/films",
        data={"title": "Affiche trop lourde"},
        files={
            "poster_file": (
                "large.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024),
                "image/png",
            )
        },
    )
    assert oversized.status_code == 413
