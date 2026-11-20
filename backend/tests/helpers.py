DEFAULT_PASSWORD = "Passw0rd123"


def register(
    client,
    email="alice@example.com",
    username="alice",
    password=DEFAULT_PASSWORD,
):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def login(client, email="alice@example.com", password=DEFAULT_PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def auth_headers(client, email="alice@example.com", password=DEFAULT_PASSWORD):
    response = login(client, email, password)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
