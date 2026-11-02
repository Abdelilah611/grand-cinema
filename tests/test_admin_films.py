"""Film publication, access control, metadata, and poster upload coverage."""

from pathlib import Path

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
    poster = created.json()["poster"]
    assert poster.startswith("uploads/films/")
    assert (Path(__file__).parents[1] / "static" / poster).is_file()
    (Path(__file__).parents[1] / "static" / poster).unlink()


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
