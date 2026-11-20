def create_direct(client, headers, title="手动通知", content="手动内容"):
    return client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"title": title, "content": content},
    )


def test_create_direct_notification(client, user_a, no_dispatch):
    response = create_direct(client, user_a["headers"])
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "手动通知"
    assert body["content"] == "手动内容"
    assert body["status"] == "pending"
    assert body["retry_count"] == 0
    assert body["template_id"] is None
    assert no_dispatch == [body["id"]]


def test_create_notification_from_template_with_snapshot(
    client, user_a, no_dispatch
):
    template = client.post(
        "/api/v1/templates",
        headers=user_a["headers"],
        json={"name": "tpl", "title": "模板标题", "content": "模板内容"},
    ).json()

    response = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"template_id": template["id"]},
    )
    assert response.status_code == 201
    notification = response.json()
    assert notification["template_id"] == template["id"]
    assert notification["title"] == "模板标题"
    assert notification["content"] == "模板内容"

    # 修改模板后，已创建通知的内容快照不受影响
    client.put(
        f"/api/v1/templates/{template['id']}",
        headers=user_a["headers"],
        json={"title": "修改后的标题", "content": "修改后的内容"},
    )
    detail = client.get(
        f"/api/v1/notifications/{notification['id']}", headers=user_a["headers"]
    ).json()
    assert detail["title"] == "模板标题"
    assert detail["content"] == "模板内容"


def test_create_notification_requires_source(client, user_a):
    response = client.post(
        "/api/v1/notifications", headers=user_a["headers"], json={}
    )
    assert response.status_code == 422


def test_create_notification_rejects_ambiguous_payload(client, user_a):
    response = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"template_id": 1, "title": "t", "content": "c"},
    )
    assert response.status_code == 422


def test_create_notification_with_other_users_template_fails(
    client, user_a, user_b, no_dispatch
):
    template = client.post(
        "/api/v1/templates",
        headers=user_a["headers"],
        json={"name": "tpl", "title": "A", "content": "A content"},
    ).json()

    response = client.post(
        "/api/v1/notifications",
        headers=user_b["headers"],
        json={"template_id": template["id"]},
    )
    assert response.status_code == 404
    assert no_dispatch == []


def test_notification_requires_authentication(client):
    assert create_direct(client, {}).status_code == 401


def test_get_notification_detail(client, user_a, no_dispatch):
    created = create_direct(client, user_a["headers"]).json()
    response = client.get(
        f"/api/v1/notifications/{created['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_user_cannot_read_other_users_notification(
    client, user_a, user_b, no_dispatch
):
    created = create_direct(client, user_a["headers"]).json()
    response = client.get(
        f"/api/v1/notifications/{created['id']}", headers=user_b["headers"]
    )
    assert response.status_code == 404


def test_list_notifications_only_returns_own(client, user_a, user_b, no_dispatch):
    create_direct(client, user_a["headers"], title="A 的通知")
    create_direct(client, user_b["headers"], title="B 的通知")

    response = client.get("/api/v1/notifications", headers=user_a["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "A 的通知"


def test_notification_pagination_and_order(client, user_a, no_dispatch):
    for index in range(5):
        response = create_direct(
            client, user_a["headers"], title=f"通知-{index}", content="内容"
        )
        assert response.status_code == 201

    response = client.get(
        "/api/v1/notifications?page=1&page_size=2",
        headers=user_a["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["pages"] == 3
    assert len(body["items"]) == 2
    # 按创建时间倒序（同一时间以 id 倒序兜底）
    assert body["items"][0]["title"] == "通知-4"
    assert body["items"][1]["title"] == "通知-3"

    last_page = client.get(
        "/api/v1/notifications?page=3&page_size=2",
        headers=user_a["headers"],
    ).json()
    assert len(last_page["items"]) == 1
    assert last_page["items"][0]["title"] == "通知-0"

    empty_page = client.get(
        "/api/v1/notifications?page=4&page_size=2",
        headers=user_a["headers"],
    ).json()
    assert empty_page["items"] == []


def test_notification_status_filter(client, user_a, db, no_dispatch):
    from app.models.notification import Notification

    first = create_direct(client, user_a["headers"], title="成功通知").json()
    create_direct(client, user_a["headers"], title="待处理通知")

    notification = db.get(Notification, first["id"])
    notification.status = "success"
    db.commit()

    response = client.get(
        "/api/v1/notifications?status=success", headers=user_a["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "成功通知"

    response = client.get(
        "/api/v1/notifications?status=pending", headers=user_a["headers"]
    )
    assert response.json()["total"] == 1


def test_invalid_status_filter_rejected(client, user_a):
    response = client.get(
        "/api/v1/notifications?status=unknown", headers=user_a["headers"]
    )
    assert response.status_code == 422


def test_enqueue_failure_keeps_pending_with_error(client, user_a, monkeypatch):
    from app.tasks.notify import process_notification_task

    def fail_publish(*args, **kwargs):
        raise ConnectionError("redis down")

    # 投递时禁用 Celery 的自动重试，快速失败
    monkeypatch.setattr(
        process_notification_task, "apply_async", fail_publish
    )

    response = create_direct(client, user_a["headers"])
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert "投递失败" in body["error_message"]
