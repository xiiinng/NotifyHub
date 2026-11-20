import pytest


def create_template(client, headers, name="welcome", title="欢迎", content="欢迎使用 NotifyHub"):
    response = client.post(
        "/api/v1/templates",
        headers=headers,
        json={"name": name, "title": title, "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_template(client, user_a):
    template = create_template(client, user_a["headers"])
    assert template["name"] == "welcome"
    assert template["title"] == "欢迎"
    assert template["content"] == "欢迎使用 NotifyHub"
    assert template["id"] > 0


def test_create_template_requires_authentication(client):
    response = client.post(
        "/api/v1/templates",
        json={"name": "welcome", "title": "t", "content": "c"},
    )
    assert response.status_code == 401


def test_create_template_validation(client, user_a):
    response = client.post(
        "/api/v1/templates",
        headers=user_a["headers"],
        json={"name": "", "title": "t", "content": "c"},
    )
    assert response.status_code == 422


def test_duplicate_template_name_conflicts(client, user_a):
    create_template(client, user_a["headers"])
    response = client.post(
        "/api/v1/templates",
        headers=user_a["headers"],
        json={"name": "welcome", "title": "另一个标题", "content": "内容"},
    )
    assert response.status_code == 409


def test_list_templates_only_returns_own(client, user_a, user_b):
    create_template(client, user_a["headers"], name="a1")
    create_template(client, user_a["headers"], name="a2")
    create_template(client, user_b["headers"], name="b1")

    response = client.get("/api/v1/templates", headers=user_a["headers"])
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {"a1", "a2"}


def test_get_template_detail(client, user_a):
    template = create_template(client, user_a["headers"])
    response = client.get(
        f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["id"] == template["id"]


def test_update_template(client, user_a):
    template = create_template(client, user_a["headers"])
    response = client.put(
        f"/api/v1/templates/{template['id']}",
        headers=user_a["headers"],
        json={"title": "新标题", "content": "新内容"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "新标题"
    assert body["content"] == "新内容"
    assert body["name"] == "welcome"


def test_delete_template(client, user_a):
    template = create_template(client, user_a["headers"])
    response = client.delete(
        f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_access_other_users_template(client, user_a, user_b):
    template = create_template(client, user_a["headers"])

    assert (
        client.get(
            f"/api/v1/templates/{template['id']}", headers=user_b["headers"]
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/templates/{template['id']}",
            headers=user_b["headers"],
            json={"title": "hacked"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/templates/{template['id']}", headers=user_b["headers"]
        ).status_code
        == 404
    )

    # 原数据未被修改或删除
    response = client.get(
        f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["title"] == "欢迎"


def test_delete_template_keeps_notifications(client, user_a, no_dispatch):
    template = create_template(client, user_a["headers"])
    created = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"template_id": template["id"]},
    )
    assert created.status_code == 201
    notification = created.json()

    assert (
        client.delete(
            f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
        ).status_code
        == 204
    )

    response = client.get(
        f"/api/v1/notifications/{notification['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "欢迎"
    assert body["content"] == "欢迎使用 NotifyHub"
    assert body["template_id"] is None


@pytest.mark.parametrize("field", ["name", "title", "content"])
def test_update_template_rejects_explicit_null(client, user_a, field):
    template = create_template(
        client, user_a["headers"], name="null-check", title="原标题", content="原内容"
    )

    response = client.put(
        f"/api/v1/templates/{template['id']}",
        headers=user_a["headers"],
        json={field: None},
    )
    assert response.status_code == 422, response.text

    detail = client.get(
        f"/api/v1/templates/{template['id']}", headers=user_a["headers"]
    ).json()
    assert detail["name"] == "null-check"
    assert detail["title"] == "原标题"
    assert detail["content"] == "原内容"


def test_update_name_only_keeps_other_fields(client, user_a):
    template = create_template(
        client, user_a["headers"], name="partial", title="保留标题", content="保留内容"
    )

    response = client.put(
        f"/api/v1/templates/{template['id']}",
        headers=user_a["headers"],
        json={"name": "partial-new"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "partial-new"
    assert body["title"] == "保留标题"
    assert body["content"] == "保留内容"


def test_update_to_duplicate_name_returns_409(client, user_a):
    first = create_template(
        client, user_a["headers"], name="first", title="T1", content="C1"
    )
    second = create_template(
        client, user_a["headers"], name="second", title="T2", content="C2"
    )

    response = client.put(
        f"/api/v1/templates/{second['id']}",
        headers=user_a["headers"],
        json={"name": first["name"]},
    )
    assert response.status_code == 409

    # 409 后事务已回滚，原数据保持不变
    detail = client.get(
        f"/api/v1/templates/{second['id']}", headers=user_a["headers"]
    ).json()
    assert detail["name"] == "second"
    assert detail["title"] == "T2"
    assert detail["content"] == "C2"
