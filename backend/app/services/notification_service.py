from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
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


def create_notification(
    db: Session, user: User, data: NotificationCreate
) -> Notification:
    template = None
    if data.template_id is not None:
        # 关键权限校验：模板必须属于当前用户
        template = template_service.get_owned_template(
            db, user.id, data.template_id
        )

    notification = Notification(
        user_id=user.id,
        template_id=template.id if template else None,
        title=template.title if template else data.title,
        content=template.content if template else data.content,
        status=NotificationStatus.PENDING.value,
        retry_count=0,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    _dispatch(notification)

    if getattr(notification, "celery_task_id", None):
        db.commit()
        db.refresh(notification)
    else:
        # 任务投递失败：保留 pending，由 Celery Beat 周期补偿
        notification.error_message = "任务投递失败，等待补偿任务重新投递"
        db.commit()
        db.refresh(notification)

    return notification


def list_notifications(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
    status: NotificationStatus | None = None,
) -> tuple[list[Notification], int]:
    filters = [Notification.user_id == user_id]
    if status is not None:
        filters.append(Notification.status == status.value)

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


def build_page(items: list[Notification], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }
