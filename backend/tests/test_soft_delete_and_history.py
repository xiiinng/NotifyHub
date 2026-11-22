from sqlalchemy import func, select

from app.models.ticket import Ticket, TicketComment, TicketHistory, TicketNotificationEvent


def create_ticket(client, headers, title="审计工单"):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": title,
            "description": "审计测试",
            "category": "other",
            "priority": "low",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_soft_delete_preserves_history_comments_and_events(
    client, user_a, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    comment = client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=support_user["headers"],
        json={"content": "删除前的处理备注"},
    )
    assert comment.status_code == 201

    response = client.delete(
        f"/api/v1/tickets/{created['id']}", headers=user_a["headers"]
    )
    assert response.status_code == 204

    assert (
        client.get(
            f"/api/v1/tickets/{created['id']}", headers=user_a["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/tickets", headers=user_a["headers"]).json()["total"]
        == 0
    )

    db.expire_all()
    ticket = db.get(Ticket, created["id"])
    assert ticket is not None
    assert ticket.deleted_at is not None

    history_count = db.scalar(
        select(func.count())
        .select_from(TicketHistory)
        .where(TicketHistory.ticket_id == created["id"])
    )
    comment_count = db.scalar(
        select(func.count())
        .select_from(TicketComment)
        .where(TicketComment.ticket_id == created["id"])
    )
    event_count = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(TicketNotificationEvent.ticket_id == created["id"])
    )
    assert history_count >= 2  # created + deleted
    assert comment_count == 1
    assert event_count >= 1


def test_update_history_contains_old_and_new_values(
    client, user_a, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"], title="旧标题")

    response = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=user_a["headers"],
        json={"title": "新标题", "description": "新描述"},
    )
    assert response.status_code == 200, response.text

    item = db.scalar(
        select(TicketHistory)
        .where(
            TicketHistory.ticket_id == created["id"],
            TicketHistory.action == "updated",
        )
        .order_by(TicketHistory.id.desc())
    )
    assert item is not None
    assert item.old_value is not None
    assert item.new_value is not None
    assert "旧标题" in item.old_value
    assert "新标题" in item.new_value
    assert "新描述" in item.new_value
