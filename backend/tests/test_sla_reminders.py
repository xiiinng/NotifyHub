from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification
from app.models.ticket import Ticket, TicketNotificationEvent
from app.services import ticket_service
from app.tasks.celery_app import celery_app


def create_ticket(client, headers, title="SLA 工单"):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": title,
            "description": "SLA 提醒测试",
            "category": "other",
            "priority": "urgent",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_beat_schedule_contains_five_minute_sla_check():
    entry = celery_app.conf.beat_schedule["check-ticket-sla"]
    assert entry["task"] == "notifyhub.check_ticket_sla"
    assert entry["schedule"] == 300.0


def test_due_soon_and_overdue_events_are_idempotent(
    client, user_a, db, no_dispatch
):
    due_soon = create_ticket(client, user_a["headers"], "即将到期")
    overdue = create_ticket(client, user_a["headers"], "已经超时")
    resolved = create_ticket(client, user_a["headers"], "已解决不提醒")
    closed = create_ticket(client, user_a["headers"], "已关闭不提醒")

    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    due_soon_ticket = db.get(Ticket, due_soon["id"])
    overdue_ticket = db.get(Ticket, overdue["id"])
    resolved_ticket = db.get(Ticket, resolved["id"])
    closed_ticket = db.get(Ticket, closed["id"])
    due_soon_ticket.due_at = fixed + timedelta(minutes=10)
    overdue_ticket.due_at = fixed - timedelta(minutes=5)
    resolved_ticket.due_at = fixed + timedelta(minutes=10)
    resolved_ticket.status = "resolved"
    closed_ticket.due_at = fixed + timedelta(minutes=10)
    closed_ticket.status = "closed"
    db.commit()

    first = ticket_service.check_ticket_sla(db, now=fixed)
    second = ticket_service.check_ticket_sla(db, now=fixed)

    assert first["due_soon"] == 1
    assert first["overdue"] == 1
    assert second["due_soon"] == 1
    assert second["overdue"] == 1

    events = db.scalars(
        select(TicketNotificationEvent).order_by(TicketNotificationEvent.id)
    ).all()
    event_keys = {event.event_key for event in events}
    assert f"ticket:{due_soon['id']}:sla_due_soon" in event_keys
    assert f"ticket:{overdue['id']}:sla_overdue" in event_keys
    assert f"ticket:{resolved['id']}:sla_due_soon" not in event_keys
    assert f"ticket:{closed['id']}:sla_due_soon" not in event_keys

    due_soon_events = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(TicketNotificationEvent.event_type == "sla_due_soon")
    )
    overdue_events = db.scalar(
        select(func.count())
        .select_from(TicketNotificationEvent)
        .where(TicketNotificationEvent.event_type == "sla_overdue")
    )
    assert due_soon_events == 1
    assert overdue_events == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_a["profile"]["id"])
        )
        == 6  # 4 条创建通知 + 1 条即将到期 + 1 条超时
    )


def test_due_soon_then_overdue_generates_two_distinct_events(
    client, user_a, db, no_dispatch
):
    created = create_ticket(client, user_a["headers"])
    ticket = db.get(Ticket, created["id"])
    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ticket.due_at = fixed + timedelta(minutes=10)
    db.commit()

    ticket_service.check_ticket_sla(db, now=fixed)
    later = fixed + timedelta(minutes=20)
    ticket_service.check_ticket_sla(db, now=later)

    event_types = db.scalars(
        select(TicketNotificationEvent.event_type).where(
            TicketNotificationEvent.ticket_id == ticket.id
        )
    ).all()
    assert "sla_due_soon" in event_types
    assert "sla_overdue" in event_types


def test_sla_window_includes_thirty_minutes_boundary(
    client, user_a, db, no_dispatch
):
    boundary = create_ticket(client, user_a["headers"], "边界工单")
    outside = create_ticket(client, user_a["headers"], "窗口外工单")
    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    boundary_ticket = db.get(Ticket, boundary["id"])
    outside_ticket = db.get(Ticket, outside["id"])
    boundary_ticket.due_at = fixed + timedelta(minutes=30)
    outside_ticket.due_at = fixed + timedelta(minutes=30, seconds=1)
    db.commit()

    result = ticket_service.check_ticket_sla(db, now=fixed, window_minutes=30)
    assert result["due_soon"] == 1

    keys = db.scalars(
        select(TicketNotificationEvent.event_key)
    ).all()
    assert f"ticket:{boundary['id']}:sla_due_soon" in keys
    assert f"ticket:{outside['id']}:sla_due_soon" not in keys


def test_due_soon_is_not_starved_by_more_than_200_overdue_tickets(
    client, user_a, db, no_dispatch
):
    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    user_id = user_a["profile"]["id"]

    overdue_tickets = []
    for index in range(201):
        ticket = Ticket(
            ticket_no=f"BULK-{index:03d}",
            user_id=user_id,
            title=f"历史超时-{index}",
            description="历史超时",
            category="other",
            priority="low",
            status="pending",
            due_at=fixed - timedelta(hours=1),
            created_at=fixed - timedelta(hours=2),
            updated_at=fixed - timedelta(hours=2),
        )
        db.add(ticket)
        overdue_tickets.append(ticket)
    db.flush()
    for ticket in overdue_tickets:
        db.add(
            TicketNotificationEvent(
                ticket_id=ticket.id,
                event_key=f"ticket:{ticket.id}:sla_overdue",
                event_type="sla_overdue",
                recipient_user_id=user_id,
            )
        )
    due_soon = Ticket(
        ticket_no="DUE-SOON",
        user_id=user_id,
        title="新临近到期工单",
        description="不应被历史超时挤掉",
        category="other",
        priority="urgent",
        status="pending",
        due_at=fixed + timedelta(minutes=10),
        created_at=fixed - timedelta(hours=1),
        updated_at=fixed - timedelta(hours=1),
    )
    db.add(due_soon)
    db.commit()

    result = ticket_service.check_ticket_sla(db, now=fixed)

    assert result["due_soon"] == 1
    db.expire_all()
    due_soon_event = db.scalar(
        select(TicketNotificationEvent).where(
            TicketNotificationEvent.ticket_id == due_soon.id,
            TicketNotificationEvent.event_type == "sla_due_soon",
        )
    )
    assert due_soon_event is not None
    notification = db.get(Notification, due_soon_event.notification_id)
    assert notification is not None
    assert notification.user_id == user_id


def test_sla_scan_rechecks_status_after_row_lock(
    client, user_a, db, no_dispatch, monkeypatch
):
    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ticket = Ticket(
        ticket_no="RACE-SLA",
        user_id=user_a["profile"]["id"],
        title="并发解决工单",
        description="SLA 扫描前已解决",
        category="other",
        priority="urgent",
        status="pending",
        due_at=fixed + timedelta(minutes=10),
        created_at=fixed - timedelta(hours=1),
        updated_at=fixed - timedelta(hours=1),
    )
    db.add(ticket)
    db.commit()
    ticket_id = ticket.id

    # 主会话先锁住工单，模拟 SLA 扫描已选中但尚未处理。
    locked = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update(of=Ticket)
    )
    assert locked is not None

    started = Event()
    original = ticket_service._process_sla_event

    def wrapped(*args, **kwargs):
        started.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(ticket_service, "_process_sla_event", wrapped)
    sessions = sessionmaker(bind=db.get_bind())

    def run_sla_scan():
        with sessions() as session:
            ticket_service.check_ticket_sla(session, now=fixed)

    thread = Thread(target=run_sla_scan)
    thread.start()
    assert started.wait(timeout=10)

    # SLA 扫描线程已进入处理函数并等待行锁；此时解决工单并提交。
    locked.status = "resolved"
    db.commit()
    thread.join(timeout=10)
    assert not thread.is_alive()

    db.expire_all()
    event = db.scalar(
        select(TicketNotificationEvent).where(
            TicketNotificationEvent.ticket_id == ticket_id,
            TicketNotificationEvent.event_type == "sla_due_soon",
        )
    )
    assert event is None


def test_sla_check_uses_creator_as_recipient(client, user_a, db, no_dispatch):
    created = create_ticket(client, user_a["headers"])
    ticket = db.get(Ticket, created["id"])
    fixed = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ticket.due_at = fixed + timedelta(minutes=5)
    db.commit()

    ticket_service.check_ticket_sla(db, now=fixed)

    notification = db.scalar(
        select(Notification)
        .join(
            TicketNotificationEvent,
            TicketNotificationEvent.notification_id == Notification.id,
        )
        .where(
            TicketNotificationEvent.ticket_id == ticket.id,
            TicketNotificationEvent.event_type == "sla_due_soon",
        )
    )
    assert notification is not None
    assert notification.user_id == user_a["profile"]["id"]
    assert notification.sender_id is None
