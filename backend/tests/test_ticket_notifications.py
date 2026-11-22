from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification
from app.models.ticket import Ticket, TicketNotificationEvent
from app.services import notification_service, ticket_service


def create_ticket(client, headers, title="通知工单", priority="medium"):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": title,
            "description": "用于通知测试",
            "category": "other",
            "priority": priority,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def notifications_for(db, user_id):
    return db.scalars(
        select(Notification).where(Notification.user_id == user_id)
    ).all()


def test_ticket_created_creates_unread_notification(
    client, user_a, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    notifications = notifications_for(db, user_a["profile"]["id"])
    assert len(notifications) == 1
    assert notifications[0].sender_id == user_a["profile"]["id"]
    assert notifications[0].read_at is None
    assert created["ticket_no"] in notifications[0].content


def test_ticket_assignment_status_and_comment_create_notifications(
    client, user_a, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    assigned = client.post(
        f"/api/v1/tickets/{created['id']}/assign",
        headers=support_user["headers"],
        json={"assignee_id": support_user["profile"]["id"]},
    )
    assert assigned.status_code == 200

    changed = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "in_progress"},
    )
    assert changed.status_code == 200

    commented = client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=support_user["headers"],
        json={"content": "请提供电脑型号"},
    )
    assert commented.status_code == 201

    notifications = notifications_for(db, user_a["profile"]["id"])
    assert len(notifications) == 4
    contents = "\n".join(item.content for item in notifications)
    assert "已创建" in contents
    assert "已分配" in contents
    assert "in_progress" in contents
    assert "请提供电脑型号" in contents


def test_ticket_notifications_are_idempotent_at_database_level(
    client, user_a, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    ticket = db.get(Ticket, created["id"])
    assert ticket is not None

    # 重复触发同一个业务事件时，不应再生成事件或通知。
    first = ticket_service.ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:created",
        event_type="ticket_created",
        recipient_user_id=ticket.user_id,
        title="重复通知",
        content="不应生成",
        actor=None,
    )
    db.commit()
    assert first is None

    event_count = db.scalar(
        select(func.count()).select_from(TicketNotificationEvent)
    )
    assert event_count == 1
    assert len(notifications_for(db, user_a["profile"]["id"])) == 1


def test_employee_can_send_to_other_employee_and_receiver_is_isolated(
    client, user_a, user_b, db, no_dispatch
):
    response = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={
            "recipient_user_id": user_b["profile"]["id"],
            "title": "同事消息",
            "content": "这是一条定向通知",
            "sender_id": user_b["profile"]["id"],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user_id"] == user_b["profile"]["id"]
    # 客户端伪造 sender_id 不会生效。
    assert body["sender_id"] == user_a["profile"]["id"]

    b_list = client.get("/api/v1/notifications", headers=user_b["headers"])
    assert b_list.status_code == 200
    assert b_list.json()["total"] == 1

    a_list = client.get("/api/v1/notifications", headers=user_a["headers"])
    assert a_list.status_code == 200
    assert a_list.json()["total"] == 0

    other_read = client.get(
        f"/api/v1/notifications/{body['id']}", headers=user_a["headers"]
    )
    assert other_read.status_code == 404


def test_support_can_notify_ticket_creator_only(
    client, user_a, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    response = client.post(
        f"/api/v1/tickets/{created['id']}/notify",
        headers=support_user["headers"],
        json={"title": "处理进展", "content": "正在联系供应商"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == user_a["profile"]["id"]
    assert body["sender_id"] == support_user["profile"]["id"]
    assert body["title"] == "处理进展"

    notifications = notifications_for(db, user_a["profile"]["id"])
    assert any(item.title == "处理进展" for item in notifications)


def test_self_recipient_and_invalid_recipient_are_rejected(
    client, user_a, no_dispatch
):
    self_response = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={
            "recipient_user_id": user_a["profile"]["id"],
            "title": "自己",
            "content": "不允许",
        },
    )
    assert self_response.status_code == 409

    invalid_response = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={
            "recipient_user_id": 999999,
            "title": "不存在",
            "content": "不允许",
        },
    )
    assert invalid_response.status_code == 404


def test_unread_count_and_mark_read(client, user_a, user_b, no_dispatch):
    first = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"title": "未读一", "content": "内容一"},
    ).json()
    second = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"title": "未读二", "content": "内容二"},
    ).json()

    count = client.get(
        "/api/v1/notifications/unread-count", headers=user_a["headers"]
    )
    assert count.status_code == 200
    assert count.json()["unread_count"] == 2

    marked = client.patch(
        f"/api/v1/notifications/{first['id']}/read",
        headers=user_a["headers"],
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    assert (
        client.get(
            "/api/v1/notifications/unread-count", headers=user_a["headers"]
        ).json()["unread_count"]
        == 1
    )

    # 已读操作幂等。
    assert (
        client.patch(
            f"/api/v1/notifications/{first['id']}/read",
            headers=user_a["headers"],
        ).status_code
        == 200
    )

    other = client.patch(
        f"/api/v1/notifications/{second['id']}/read",
        headers=user_b["headers"],
    )
    assert other.status_code == 404

    all_read = client.post(
        "/api/v1/notifications/read-all", headers=user_a["headers"]
    )
    assert all_read.status_code == 200
    assert all_read.json()["updated"] == 1
    assert (
        client.get(
            "/api/v1/notifications/unread-count", headers=user_a["headers"]
        ).json()["unread_count"]
        == 0
    )


def test_notification_unread_filter(client, user_a, no_dispatch):
    first = client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"title": "一", "content": "一"},
    ).json()
    client.post(
        "/api/v1/notifications",
        headers=user_a["headers"],
        json={"title": "二", "content": "二"},
    )
    client.patch(
        f"/api/v1/notifications/{first['id']}/read",
        headers=user_a["headers"],
    )

    response = client.get(
        "/api/v1/notifications?unread_only=true", headers=user_a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_ticket_creation_survives_enqueue_failure(
    client, user_a, db, monkeypatch
):
    from app.tasks.notify import process_notification_task

    def fail_publish(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(process_notification_task, "apply_async", fail_publish)

    response = client.post(
        "/api/v1/tickets",
        headers=user_a["headers"],
        json={
            "title": "队列不可用工单",
            "description": "不应回滚",
            "category": "network",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.text
    notifications = notifications_for(db, user_a["profile"]["id"])
    assert len(notifications) == 1
    assert notifications[0].status == "pending"
    assert "投递失败" in (notifications[0].error_message or "")


def test_dispatch_happens_after_ticket_transaction_commit(
    client, user_a, db, monkeypatch
):
    observed: list[int] = []
    check_session_factory = sessionmaker(bind=db.get_bind())

    def fake_dispatch(notification):
        with check_session_factory() as check_db:
            ticket = check_db.scalar(
                select(Ticket).where(Ticket.user_id == notification.user_id)
            )
            assert ticket is not None
            observed.append(ticket.id)
        notification.celery_task_id = "order-check-task"

    monkeypatch.setattr(notification_service, "_dispatch", fake_dispatch)

    response = client.post(
        "/api/v1/tickets",
        headers=user_a["headers"],
        json={
            "title": "事务顺序工单",
            "description": "检查投递顺序",
            "category": "software",
            "priority": "medium",
        },
    )
    assert response.status_code == 201
    assert observed == [response.json()["id"]]


def test_sla_notifications_are_idempotent(
    client, user_a, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"], priority="urgent")
    ticket = db.get(Ticket, created["id"])
    fixed = datetime.now(timezone.utc)
    ticket.due_at = fixed + timedelta(minutes=10)
    db.commit()

    first = ticket_service.check_ticket_sla(db, now=fixed)
    second = ticket_service.check_ticket_sla(db, now=fixed)

    assert first["due_soon"] == 1
    assert second["due_soon"] == 1
    event_count = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(TicketNotificationEvent.event_type == "sla_due_soon")
    )
    assert event_count == 1
    notification_count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_a["profile"]["id"])
    )
    # 工单创建通知 + 一条临近到期通知
    assert notification_count == 2
