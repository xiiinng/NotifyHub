from datetime import datetime, timedelta, timezone

from app.schemas.ticket import TicketPriority, TicketStatus

SLA_HOURS: dict[str, int] = {
    TicketPriority.LOW.value: 72,
    TicketPriority.MEDIUM.value: 24,
    TicketPriority.HIGH.value: 8,
    TicketPriority.URGENT.value: 2,
}

OPEN_STATUSES = {
    TicketStatus.PENDING.value,
    TicketStatus.IN_PROGRESS.value,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def calculate_due_at(
    priority: str,
    created_at: datetime | None = None,
) -> datetime:
    created = ensure_utc(created_at or utcnow())
    hours = SLA_HOURS[priority]
    return created + timedelta(hours=hours)


def sla_remaining_seconds(
    due_at: datetime | None,
    now: datetime | None = None,
) -> int | None:
    if due_at is None:
        return None
    current = ensure_utc(now or utcnow())
    return int((ensure_utc(due_at) - current).total_seconds())


def is_overdue(
    status: str,
    due_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    if due_at is None or status not in OPEN_STATUSES:
        return False
    return ensure_utc(due_at) < ensure_utc(now or utcnow())
