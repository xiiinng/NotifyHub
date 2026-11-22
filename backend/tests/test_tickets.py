from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.ticket import TicketHistory
from app.services import sla_service


def create_ticket(client, headers, **overrides):
    payload = {
        "title": "电脑无法开机",
        "description": "按下电源键后没有反应",
        "category": "hardware",
        "priority": "medium",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tickets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def ticket_headers(client, user):
    return user["headers"]


def test_create_ticket_defaults(client, user_a, no_dispatch):
    body = create_ticket(client, user_a["headers"])

    assert body["status"] == "pending"
    assert body["priority"] == "medium"
    assert body["category"] == "hardware"
    assert body["ticket_no"].startswith("TK-")
    assert body["creator"]["id"] == user_a["profile"]["id"]
    assert body["assignee"] is None
    assert body["due_at"] is not None
    assert body["is_overdue"] is False
    assert body["resolved_at"] is None
    assert body["closed_at"] is None


def test_ticket_list_pagination_filters_and_search(client, user_a, no_dispatch):
    for index in range(3):
        create_ticket(
            client,
            user_a["headers"],
            title=f"网络问题-{index}",
            category="network",
            priority="high",
        )
    create_ticket(client, user_a["headers"], title="软件安装", category="software")

    response = client.get(
        "/api/v1/tickets?page=1&page_size=2&category=network&priority=high",
        headers=user_a["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["pages"] == 2

    search = client.get(
        "/api/v1/tickets?q=软件", headers=user_a["headers"]
    ).json()
    assert search["total"] == 1
    assert search["items"][0]["title"] == "软件安装"


def test_employee_only_sees_own_tickets(client, user_a, user_b, no_dispatch):
    created = create_ticket(client, user_a["headers"])

    list_b = client.get("/api/v1/tickets", headers=user_b["headers"])
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0

    detail_b = client.get(
        f"/api/v1/tickets/{created['id']}", headers=user_b["headers"]
    )
    assert detail_b.status_code == 404


def test_support_can_view_all_tickets(client, user_a, support_user, no_dispatch):
    created = create_ticket(client, user_a["headers"])

    response = client.get("/api/v1/tickets", headers=support_user["headers"])
    assert response.status_code == 200
    assert response.json()["total"] == 1

    detail = client.get(
        f"/api/v1/tickets/{created['id']}", headers=support_user["headers"]
    )
    assert detail.status_code == 200


def test_employee_updates_basic_fields_and_history(client, user_a, db, no_dispatch):
    created = create_ticket(client, user_a["headers"])

    response = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=user_a["headers"],
        json={"title": "新标题", "description": "新描述", "category": "software"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "新标题"
    assert body["category"] == "software"

    histories = db.scalars(
        select(TicketHistory).where(TicketHistory.ticket_id == created["id"])
    ).all()
    assert any(item.action == "updated" for item in histories)


def test_employee_cannot_change_priority_or_due_date(
    client, user_a, no_dispatch
):
    created = create_ticket(client, user_a["headers"])

    priority = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=user_a["headers"],
        json={"priority": "urgent"},
    )
    assert priority.status_code == 403

    due = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=user_a["headers"],
        json={"due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
    )
    assert due.status_code == 403


def test_support_adjusts_due_date_and_priority_rules(
    client, user_a, support_user, no_dispatch
):
    created = create_ticket(
        client, user_a["headers"], priority="medium"
    )
    assert created["due_at"]

    manual_due = datetime.now(timezone.utc) + timedelta(hours=12)
    adjusted = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=support_user["headers"],
        json={"due_at": manual_due.isoformat()},
    )
    assert adjusted.status_code == 200
    adjusted_due = datetime.fromisoformat(adjusted.json()["due_at"])

    changed = client.patch(
        f"/api/v1/tickets/{created['id']}",
        headers=support_user["headers"],
        json={"priority": "urgent"},
    )
    assert changed.status_code == 200
    # 手工调整截止时间后，优先级变化不能静默覆盖。
    assert datetime.fromisoformat(changed.json()["due_at"]) == adjusted_due

    # 新建的未手工调整工单会按新优先级重新计算 SLA。
    second = create_ticket(client, user_a["headers"], priority="low")
    changed_second = client.patch(
        f"/api/v1/tickets/{second['id']}",
        headers=support_user["headers"],
        json={"priority": "urgent"},
    )
    assert changed_second.status_code == 200
    old_due = datetime.fromisoformat(second["due_at"])
    new_due = datetime.fromisoformat(changed_second.json()["due_at"])
    assert new_due < old_due


def test_only_pending_unassigned_ticket_can_be_deleted(
    client, user_a, support_user, no_dispatch
):
    created = create_ticket(client, user_a["headers"])

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

    second = create_ticket(client, user_a["headers"])
    assert (
        client.post(
            f"/api/v1/tickets/{second['id']}/assign",
            headers=support_user["headers"],
            json={"assignee_id": support_user["profile"]["id"]},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/tickets/{second['id']}", headers=user_a["headers"]
        ).status_code
        == 409
    )


def test_assign_rejects_employee_and_requires_support(
    client, user_a, user_b, support_user, no_dispatch
):
    created = create_ticket(client, user_a["headers"])

    employee_attempt = client.post(
        f"/api/v1/tickets/{created['id']}/assign",
        headers=user_a["headers"],
        json={"assignee_id": support_user["profile"]["id"]},
    )
    assert employee_attempt.status_code == 403

    invalid_assignee = client.post(
        f"/api/v1/tickets/{created['id']}/assign",
        headers=support_user["headers"],
        json={"assignee_id": user_b["profile"]["id"]},
    )
    assert invalid_assignee.status_code == 409

    assigned = client.post(
        f"/api/v1/tickets/{created['id']}/assign",
        headers=support_user["headers"],
        json={"assignee_id": support_user["profile"]["id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee"]["id"] == support_user["profile"]["id"]


def test_status_machine_and_timestamps(client, user_a, support_user, no_dispatch):
    created = create_ticket(client, user_a["headers"])

    invalid = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "closed"},
    )
    assert invalid.status_code == 409

    resolved = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    reopened = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "in_progress"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None

    resolved_again = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "resolved"},
    )
    assert resolved_again.status_code == 200
    closed = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "closed"},
    )
    assert closed.status_code == 200
    assert closed.json()["closed_at"] is not None

    reopen_closed = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=support_user["headers"],
        json={"status": "in_progress"},
    )
    assert reopen_closed.status_code == 409


def test_employee_cannot_change_status(client, user_a, no_dispatch):
    created = create_ticket(client, user_a["headers"])
    response = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        headers=user_a["headers"],
        json={"status": "resolved"},
    )
    assert response.status_code == 403


def test_comments_and_history_visibility(
    client, user_a, user_b, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])

    forbidden = client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=user_a["headers"],
        json={"content": "员工不能写"},
    )
    assert forbidden.status_code == 403

    comment = client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=support_user["headers"],
        json={"content": "已经在处理中"},
    )
    assert comment.status_code == 201
    assert comment.json()["content"] == "已经在处理中"

    own_comments = client.get(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=user_a["headers"],
    )
    assert own_comments.status_code == 200
    assert len(own_comments.json()) == 1

    other_comments = client.get(
        f"/api/v1/tickets/{created['id']}/comments",
        headers=user_b["headers"],
    )
    assert other_comments.status_code == 404

    own_history = client.get(
        f"/api/v1/tickets/{created['id']}/history",
        headers=user_a["headers"],
    )
    assert own_history.status_code == 200
    assert any(item["action"] == "created" for item in own_history.json())

    other_history = client.get(
        f"/api/v1/tickets/{created['id']}/history",
        headers=user_b["headers"],
    )
    assert other_history.status_code == 404


def test_stats_are_role_scoped(client, user_a, user_b, support_user, no_dispatch):
    create_ticket(client, user_a["headers"], priority="high")
    create_ticket(client, user_b["headers"], priority="urgent")

    own = client.get("/api/v1/tickets/stats", headers=user_a["headers"])
    assert own.status_code == 200
    assert own.json()["total"] == 1
    assert own.json()["priorities"]["high"] == 1
    assert own.json()["priorities"]["urgent"] == 0

    global_stats = client.get(
        "/api/v1/tickets/stats", headers=support_user["headers"]
    )
    assert global_stats.status_code == 200
    assert global_stats.json()["total"] == 2
    assert global_stats.json()["priorities"]["urgent"] == 1


def test_support_stats_include_unassigned_and_assignee_counts(
    client, user_a, support_user, no_dispatch
):
    first = create_ticket(client, user_a["headers"], title="已分配统计")
    create_ticket(client, user_a["headers"], title="未分配统计")
    assign = client.post(
        f"/api/v1/tickets/{first['id']}/assign",
        headers=support_user["headers"],
        json={"assignee_id": support_user["profile"]["id"]},
    )
    assert assign.status_code == 200

    response = client.get(
        "/api/v1/tickets/stats", headers=support_user["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["unassigned"] == 1
    assert body["assignees"][0]["assignee_id"] == support_user["profile"]["id"]
    assert body["assignees"][0]["total"] == 1
    assert body["assignees"][0]["open"] == 1


def test_assignees_endpoint_is_support_only(
    client, user_a, support_user, no_dispatch
):
    assert (
        client.get("/api/v1/tickets/assignees", headers=user_a["headers"]).status_code
        == 403
    )
    response = client.get(
        "/api/v1/tickets/assignees", headers=support_user["headers"]
    )
    assert response.status_code == 200
    assert any(item["id"] == support_user["profile"]["id"] for item in response.json())


def test_ticket_create_ignores_forged_user_id(client, user_a, user_b, no_dispatch):
    response = client.post(
        "/api/v1/tickets",
        headers=user_a["headers"],
        json={
            "title": "伪造归属",
            "description": "不应生效",
            "category": "other",
            "priority": "low",
            "user_id": user_b["profile"]["id"],
        },
    )
    assert response.status_code == 201
    assert response.json()["creator"]["id"] == user_a["profile"]["id"]


def test_sla_unit_calculation():
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert sla_service.calculate_due_at("low", created) == created + timedelta(hours=72)
    assert sla_service.calculate_due_at("medium", created) == created + timedelta(hours=24)
    assert sla_service.calculate_due_at("high", created) == created + timedelta(hours=8)
    assert sla_service.calculate_due_at("urgent", created) == created + timedelta(hours=2)
