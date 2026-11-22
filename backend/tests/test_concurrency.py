from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ConflictError
from app.models.notification import Notification
from app.models.ticket import Ticket, TicketHistory, TicketNotificationEvent
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketStatus
from app.services import ticket_service


def create_ticket(client, headers, title="并发工单"):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": title,
            "description": "并发测试",
            "category": "other",
            "priority": "medium",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_concurrent_status_changes_are_serialized(
    client, user_a, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    sessions = sessionmaker(bind=db.get_bind())
    barrier = Barrier(2)

    def change_status():
        with sessions() as session:
            user = session.scalar(
                select(User).where(User.email == support_user["profile"]["email"])
            )
            barrier.wait(timeout=10)
            try:
                ticket_service.change_status(
                    session,
                    user,
                    created["id"],
                    TicketStatus.IN_PROGRESS,
                )
                return "ok"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: change_status(), range(2)))

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 1

    db.expire_all()
    ticket = db.get(Ticket, created["id"])
    assert ticket is not None
    assert ticket.status == TicketStatus.IN_PROGRESS.value

    status_history_count = db.scalar(
        select(func.count())
        .select_from(TicketHistory)
        .where(
            TicketHistory.ticket_id == ticket.id,
            TicketHistory.action == "status_changed",
        )
    )
    status_event_count = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(
            TicketNotificationEvent.ticket_id == ticket.id,
            TicketNotificationEvent.event_type == "ticket_status_changed",
        )
    )
    assert status_history_count == 1
    assert status_event_count == 1


def test_concurrent_same_assignment_is_serialized(
    client, user_a, support_user, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    sessions = sessionmaker(bind=db.get_bind())
    barrier = Barrier(2)

    def assign():
        with sessions() as session:
            user = session.scalar(
                select(User).where(User.email == support_user["profile"]["email"])
            )
            barrier.wait(timeout=10)
            try:
                ticket_service.assign_ticket(
                    session,
                    user,
                    created["id"],
                    support_user["profile"]["id"],
                )
                return "ok"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: assign(), range(2)))

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 1

    db.expire_all()
    ticket = db.get(Ticket, created["id"])
    assert ticket is not None
    assert ticket.assignee_id == support_user["profile"]["id"]

    assignment_history_count = db.scalar(
        select(func.count())
        .select_from(TicketHistory)
        .where(
            TicketHistory.ticket_id == ticket.id,
            TicketHistory.action.in_(["assigned", "reassigned"]),
        )
    )
    assignment_event_count = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(
            TicketNotificationEvent.ticket_id == ticket.id,
            TicketNotificationEvent.event_type == "ticket_assigned",
        )
    )
    assert assignment_history_count == 1
    assert assignment_event_count == 1

    # 只应存在一个分配通知事件，以及工单创建和可能的其他通知。
    notification_count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_a["profile"]["id"])
    )
    assert notification_count >= 2
