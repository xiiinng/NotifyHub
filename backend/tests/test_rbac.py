from sqlalchemy import select

from app.models.user import User, UserRole
from app.services import user_service
from tests.helpers import auth_headers, register


def create_ticket(client, headers):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "权限测试工单",
            "description": "权限测试",
            "category": "other",
            "priority": "low",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_defaults_to_employee(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["role"] == "employee"

    me = client.get("/api/v1/auth/me", headers=auth_headers(client))
    assert me.status_code == 200
    assert me.json()["role"] == "employee"


def test_registration_cannot_specify_role(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "hacker",
            "email": "hacker@example.com",
            "password": "Passw0rd123",
            "role": "it_support",
        },
    )
    assert response.status_code == 422


def test_employee_cannot_use_support_endpoints(
    client, user_a, no_dispatch
):
    created = create_ticket(client, user_a["headers"])

    assert (
        client.post(
            f"/api/v1/tickets/{created['id']}/assign",
            headers=user_a["headers"],
            json={"assignee_id": 1},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/tickets/{created['id']}/status",
            headers=user_a["headers"],
            json={"status": "resolved"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/tickets/{created['id']}/comments",
            headers=user_a["headers"],
            json={"content": "不允许"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/tickets/assignees", headers=user_a["headers"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/tickets/{created['id']}/notify",
            headers=user_a["headers"],
            json={"title": "不允许", "content": "不允许"},
        ).status_code
        == 403
    )


def test_support_role_is_loaded_from_database(client, support_user):
    me = client.get("/api/v1/auth/me", headers=support_user["headers"])
    assert me.status_code == 200
    assert me.json()["role"] == "it_support"


def test_unauthenticated_ticket_endpoints_return_401(client):
    assert client.get("/api/v1/tickets").status_code == 401
    assert client.get("/api/v1/tickets/stats").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401


def test_user_cannot_forge_role_with_registration_payload(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "normal",
            "email": "normal@example.com",
            "password": "Passw0rd123",
            "role": "it_support",
            "is_admin": True,
        },
    )
    assert response.status_code == 422

    # 普通注册没有创建账号。
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "normal@example.com", "password": "Passw0rd123"},
    )
    assert login_response.status_code == 401


def test_it_support_cli_service_is_idempotent(client, db):
    register(client, email="promote@example.com", username="promote")
    user = db.scalar(select(User).where(User.email == "promote@example.com"))
    assert user is not None
    original_hash = user.hashed_password

    created_user, created = user_service.create_it_support_user(
        db,
        email="promote@example.com",
        username="promote",
        password=None,
    )
    assert created is False
    assert created_user.role == UserRole.IT_SUPPORT.value
    assert created_user.hashed_password == original_hash

    again, created_again = user_service.create_it_support_user(
        db,
        email="promote@example.com",
        username="promote",
        password=None,
    )
    assert created_again is False
    assert again.role == UserRole.IT_SUPPORT.value


def test_user_directory_excludes_self_and_secrets(client, user_a, user_b):
    response = client.get(
        "/api/v1/users/directory", headers=user_a["headers"]
    )
    assert response.status_code == 200
    items = response.json()
    ids = {item["id"] for item in items}
    assert user_b["profile"]["id"] in ids
    assert user_a["profile"]["id"] not in ids
    assert all("hashed_password" not in item for item in items)
    assert all("password" not in item for item in items)
