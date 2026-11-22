from datetime import datetime, timezone
from math import ceil

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationStatus
from app.services import template_service

logger = get_logger(__name__)


def _dispatch(notification: Notification) -> None:
    """在数据库提交之后投递 Celery 任务；投递失败的通知留给补偿任务重试。"""
    from app.tasks.notify import process_notification_task

    try:
        result = process_notification_task.apply_async(args=[notification.id])
    except Exception:
        logger.exception(
            "Celery 任务投递失败 notification_id=%s，等待补偿任务处理",
            notification.id,
        )
        return

    notification.celery_task_id = result.id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_notification_record(
    db: Session,
    *,
    recipient_user_id: int,
    sender_id: int | None,
    title: str,
    content: str,
    template_id: int | None = None,
    dedupe_key: str | None = None,
) -> Notification:
    """在当前事务中创建通知记录，不提交、不投递。"""
    notification = Notification(
        user_id=recipient_user_id,
        sender_id=sender_id,
        template_id=template_id,
        title=title,
        content=content,
        status=NotificationStatus.PENDING.value,
        retry_count=0,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    db.flush()
    return notification


def dispatch_after_commit(db: Session, notification: Notification) -> Notification:
    """业务事务已提交后投递 Celery；失败时保留 pending 供 Beat 恢复。"""
    try:
        _dispatch(notification)
    except Exception:
        logger.exception(
            "通知投递异常 notification_id=%s，保留 pending 等待补偿",
            notification.id,
        )
        notification.celery_task_id = None

    if getattr(notification, "celery_task_id", None):
        db.commit()
        db.refresh(notification)
    else:
        notification.error_message = "任务投递失败，等待补偿任务重新投递"
        db.commit()
        db.refresh(notification)
    return notification


def dispatch_notifications(db: Session, notification_ids: list[int]) -> None:
    for notification_id in notification_ids:
        notification = db.get(Notification, notification_id)
        if notification is not None:
            dispatch_after_commit(db, notification)


def create_notification(
    db: Session, user: User, data: NotificationCreate
) -> Notification:
    template = None
    if data.template_id is not None:
        # 模板属于发送者；收件人可以是其他用户。
        template = template_service.get_owned_template(
            db, user.id, data.template_id
        )

    recipient_id = user.id
    if data.recipient_user_id is not None:
        recipient = db.get(User, data.recipient_user_id)
        if recipient is None:
            raise NotFoundError("接收用户不存在")
        if recipient.id == user.id:
            raise ConflictError("不能向自己发送通知")
        recipient_id = recipient.id

    notification = create_notification_record(
        db,
        recipient_user_id=recipient_id,
        sender_id=user.id,
        template_id=template.id if template else None,
        title=template.title if template else data.title or "",
        content=template.content if template else data.content or "",
    )
    db.commit()
    db.refresh(notification)
    return dispatch_after_commit(db, notification)


def list_notifications(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
    status: NotificationStatus | None = None,
    unread_only: bool = False,
) -> tuple[list[Notification], int]:
    filters = [Notification.user_id == user_id]
    if status is not None:
        filters.append(Notification.status == status.value)
    if unread_only:
        filters.append(Notification.read_at.is_(None))

    total = db.scalar(
        select(func.count()).select_from(Notification).where(*filters)
    ) or 0

    stmt = (
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(stmt).all()), total


def get_owned_notification(
    db: Session, user_id: int, notification_id: int
) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if notification is None:
        raise NotFoundError("通知不存在")
    return notification


def mark_read(db: Session, user_id: int, notification_id: int) -> Notification:
    notification = get_owned_notification(db, user_id, notification_id)
    if notification.read_at is None:
        notification.read_at = _utcnow()
        db.commit()
        db.refresh(notification)
    return notification


def mark_all_read(db: Session, user_id: int) -> int:
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=_utcnow())
    )
    db.commit()
    return result.rowcount or 0


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def build_page(items: list[Notification], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }
