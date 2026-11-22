from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.ticket import Ticket, TicketNotificationEvent
from app.models.user import User
from app.services import notification_service


def notify_ticket_event(
    db: Session,
    *,
    ticket: Ticket,
    event_key: str,
    event_type: str,
    recipient_user_id: int,
    title: str,
    content: str,
    actor: User | None = None,
) -> Notification | None:
    """在同一事务中写入事件幂等记录和通知记录。

    返回 None 表示该事件已经处理过。调用方负责提交事务，并在提交后投递。
    """
    event_id = db.scalar(
        pg_insert(TicketNotificationEvent)
        .values(
            ticket_id=ticket.id,
            event_key=event_key,
            event_type=event_type,
            recipient_user_id=recipient_user_id,
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
        .returning(TicketNotificationEvent.id)
    )
    if event_id is None:
        return None

    notification = notification_service.create_notification_record(
        db,
        recipient_user_id=recipient_user_id,
        sender_id=actor.id if actor else None,
        title=title[:200],
        content=content[:10000],
        dedupe_key=event_key,
    )
    db.execute(
        update(TicketNotificationEvent)
        .where(TicketNotificationEvent.id == event_id)
        .values(notification_id=notification.id)
    )
    return notification
