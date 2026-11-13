"""Tests du catalogue public : films, séances et salles."""


def test_public_catalog_lists_film_screening_and_room(client, db):
    film_id = db[1]["film"].id
    future = db[1]["future"]

    films = client.get("/api/films")
    assert films.status_code == 200
    assert [film["id"] for film in films.json()] == [film_id]

    film = client.get(f"/api/films/{film_id}")
    assert film.status_code == 200
    assert [screening["id"] for screening in film.json()["screenings"]] == [future.id]

    screenings = client.get(
        "/api/screenings",
        params={
            "film_id": film_id,
            "date": future.start_time.strftime("%Y-%m-%d"),
        },
    )
    assert screenings.status_code == 200
    assert [screening["id"] for screening in screenings.json()] == [future.id]

    screening = client.get(f"/api/screenings/{future.id}")
    assert screening.status_code == 200
    assert screening.json()["film_id"] == film_id

    rooms = client.get("/api/rooms")
    assert rooms.status_code == 200
    assert rooms.json()[0]["name"] == db[1]["room"].name


def test_public_catalog_hides_unpublished_film_and_rejects_bad_queries(client, db):
    film_id = db[1]["film"].id
    screening_id = db[1]["future"].id
    db[1]["film"].is_published = False
    db[0].commit()

    assert client.get("/api/films").json() == []
    assert client.get(f"/api/films/{film_id}").status_code == 404
    assert client.get(f"/api/screenings/{screening_id}").status_code == 404
    assert client.get("/api/screenings").json() == []
    assert client.get("/api/screenings", params={"date": "invalid"}).status_code == 400
    assert client.get("/api/films/99999").status_code == 404
