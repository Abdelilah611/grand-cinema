"""Tests d'authentification : inscription, connexion, profil."""

from tests.conftest import login
from sqlalchemy.exc import OperationalError


def test_login_form_uses_post_without_query_credentials(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert 'method="post" action="/login"' in response.text
    assert response.request.url.query == b""


def test_registration_form_uses_post_without_query_credentials(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert 'method="post" action="/register"' in response.text
    assert response.request.url.query == b""


def test_registration_form_fallback_posts_and_redirects(client):
    response = client.post(
        "/register",
        data={
            "full_name": "Compte de test",
            "email": "fallback@example.test",
            "password": "Secret123!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login?registered=1"
    assert response.request.url.query == b""


def test_registration_form_duplicate_email_is_shown_without_password(client):
    response = client.post(
        "/register",
        data={
            "full_name": "Compte existant",
            "email": "user@grandcinema.fr",
            "password": "Secret123!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Cet e-mail est déjà utilisé." in response.text
    assert "Secret123!" not in response.text
    assert response.request.url.query == b""


def test_admin_login_form_redirects_to_admin_and_sets_session(client):
    response = client.post(
        "/login",
        data={"email": "admin@grandcinema.fr", "password": "Admin123!"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert "access_token" in response.cookies
    current = client.get("/api/auth/me")
    assert current.status_code == 200
    assert current.json()["role"] == "admin"


def test_regular_user_login_form_redirects_to_home(client):
    response = client.post(
        "/login",
        data={"email": "user@grandcinema.fr", "password": "User123!"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.get("/api/auth/me").json()["role"] == "user"


def test_login_form_invalid_credentials_render_clear_error(client):
    response = client.post(
        "/login",
        data={"email": "admin@grandcinema.fr", "password": "wrong-secret"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "E-mail ou mot de passe incorrect." in response.text
    assert "wrong-secret" not in response.text
    assert response.request.url.query == b""


def test_login_form_database_error_renders_retry_message(client, monkeypatch):
    def failing_authentication(db, email, password):
        raise OperationalError("select user", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(
        "app.routers.pages.authenticate_credentials", failing_authentication
    )
    response = client.post(
        "/login",
        data={"email": "admin@grandcinema.fr", "password": "Admin123!"},
        follow_redirects=False,
    )
    assert response.status_code == 503
    assert "Connexion temporairement indisponible. Réessayez." in response.text


def test_register_creates_user(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "nouveau@exemple.fr",
            "password": "Secret123!",
            "full_name": "Nouveau",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "nouveau@exemple.fr"
    assert response.json()["role"] == "user"


def test_register_duplicate_email_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "user@grandcinema.fr", "password": "Secret123!"},
    )
    assert response.status_code == 400


def test_login_success_sets_cookie_and_me_works(client):
    response = login(client, "user@grandcinema.fr", "User123!")
    assert response.status_code == 200
    assert response.json()["email"] == "user@grandcinema.fr"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "user"


def test_login_wrong_password_rejected(client):
    response = login(client, "user@grandcinema.fr", "MauvaisMotDePasse")
    assert response.status_code == 401


def test_me_without_auth_rejected(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout_clears_session(client):
    login(client, "user@grandcinema.fr", "User123!")
    assert client.get("/api/auth/me").status_code == 200
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    cookie_header = response.headers["set-cookie"]
    assert "access_token=" in cookie_header
    assert "Max-Age=0" in cookie_header
    assert "Path=/" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "access_token" not in client.cookies
    assert client.get("/api/auth/me").status_code == 401
