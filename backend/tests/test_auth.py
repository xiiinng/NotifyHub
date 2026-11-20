from tests.helpers import DEFAULT_PASSWORD, auth_headers, login, register


def test_register_success(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["username"] == "alice"
    assert "hashed_password" not in body
    assert "password" not in body
    assert body["id"] > 0


def test_register_duplicate_email_fails(client):
    assert register(client).status_code == 201
    response = register(client, username="alice2")
    assert response.status_code == 409
    assert "邮箱" in response.json()["detail"]


def test_register_duplicate_email_is_case_insensitive(client):
    assert register(client, email="Alice@Example.com").status_code == 201
    response = register(client, email="alice@example.com", username="alice2")
    assert response.status_code == 409


def test_register_weak_password_rejected(client):
    response = register(client, password="short")
    assert response.status_code == 422

    response = register(client, password="onlyletters")
    assert response.status_code == 422

    response = register(client, password="12345678")
    assert response.status_code == 422


def test_register_invalid_email_rejected(client):
    response = register(client, email="not-an-email")
    assert response.status_code == 422


def test_login_success(client):
    register(client)
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password_fails(client):
    register(client)
    response = login(client, password="WrongPass123")
    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


def test_login_unknown_email_fails_with_same_message(client):
    response = login(client, email="nobody@example.com")
    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


def test_me_requires_authentication(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_invalid_token_fails(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.value"}
    )
    assert response.status_code == 401


def test_me_with_valid_token(client, user_a):
    response = client.get("/api/v1/auth/me", headers=user_a["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "hashed_password" not in body


def test_password_is_not_stored_in_plaintext(client, db):
    from app.models.user import User

    from sqlalchemy import select

    register(client)
    user = db.scalar(select(User).where(User.email == "alice@example.com"))
    assert user is not None
    assert user.hashed_password != DEFAULT_PASSWORD
    assert user.hashed_password.startswith("$argon2")


def test_username_is_stripped_before_validation(client):
    response = register(client, username=" abc ")
    assert response.status_code == 201
    assert response.json()["username"] == "abc"


def test_padded_short_username_is_rejected(client):
    response = register(client, username=" a ")
    assert response.status_code == 422


def test_whitespace_only_username_is_rejected(client):
    response = register(client, username="    ")
    assert response.status_code == 422
