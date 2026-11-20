from datetime import datetime, timedelta, timezone

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.database import SessionLocal
from app.models.notification import Notification
from app.schemas.notification import NotificationStatus
from app.services.delivery import deliver_notification
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(bind=True, name="notifyhub.process_notification", max_retries=None)
def process_notification_task(self, notification_id: int) -> str:
    """
    状态机：
        pending -> processing -> success
                              -> pending（未超过最大重试次数，延迟重试）
                              -> failed （超过最大重试次数）
    幂等：success / failed 直接跳过；processing 未超时也跳过，防止重复执行。
    """
    with SessionLocal() as db:
        # 行锁 + SKIP LOCKED：同一通知被重复投递时只有一个 Worker 能处理
        notification = db.scalar(
            select(Notification)
            .where(Notification.id == notification_id)
            .with_for_update(skip_locked=True)
        )
        if notification is None:
            logger.warning(
                "通知不存在或正在被其他 Worker 处理 notification_id=%s",
                notification_id,
            )
            return "not-found-or-locked"

        if notification.status in (
            NotificationStatus.SUCCESS.value,
            NotificationStatus.FAILED.value,
        ):
            return "already-finished"

        if (
            notification.status == NotificationStatus.PROCESSING.value
            and notification.updated_at is not None
            and (_utcnow() - notification.updated_at).total_seconds()
            < settings.processing_timeout_seconds
        ):
            return "already-processing"

        if notification.status == NotificationStatus.PROCESSING.value:
            # 该 processing 已超时，说明上一个 Worker 可能已中断：
            # 本次接管必须消耗一次重试预算。
            notification.retry_count += 1
            logger.warning(
                "接管超时 processing notification_id=%s retry_count=%s",
                notification_id,
                notification.retry_count,
            )
            if notification.retry_count > settings.max_notification_retries:
                notification.status = NotificationStatus.FAILED.value
                notification.error_message = (
                    "处理超时超过最大重试次数"
                    f"（{settings.max_notification_retries}），任务已失败"
                )
                db.commit()
                return "failed"

        notification.status = NotificationStatus.PROCESSING.value
        notification.celery_task_id = self.request.id or notification.celery_task_id
        db.commit()
        db.refresh(notification)

        try:
            deliver_notification(notification)
        except Exception as exc:
            reason = (
                "任务执行超时（soft time limit）"
                if isinstance(exc, SoftTimeLimitExceeded)
                else str(exc)
            )
            logger.exception(
                "通知处理失败 notification_id=%s attempt=%s",
                notification_id,
                notification.retry_count + 1,
            )
            notification.retry_count += 1
            if notification.retry_count <= settings.max_notification_retries:
                notification.status = NotificationStatus.PENDING.value
                notification.error_message = (
                    f"第 {notification.retry_count} 次处理失败：{reason}"
                )
                db.commit()

                countdown = min(
                    settings.retry_backoff_base_seconds
                    * (2 ** (notification.retry_count - 1)),
                    300,
                )
                process_notification_task.apply_async(
                    args=[notification_id], countdown=countdown
                )
                return "retry-scheduled"

            notification.status = NotificationStatus.FAILED.value
            notification.error_message = (
                f"超过最大重试次数（{settings.max_notification_retries}）：{reason}"
            )
            db.commit()
            return "failed"

        notification.status = NotificationStatus.SUCCESS.value
        notification.error_message = None
        db.commit()
        logger.info("通知处理成功 notification_id=%s", notification_id)
        return "success"


def _recover_stale_processing(
    db: Session, notification_id: int, cutoff: datetime, now: datetime
) -> str | None:
    """
    原子地恢复“仍然超时且仍为 processing”的通知，并消耗一次重试预算。

    - 条件 UPDATE 同时检查 id、status、updated_at，终态不会被覆盖。
    - retry_count 在 SQL 中原子加 1；超过预算直接转 failed。
    - 返回新的状态（pending/failed）；未命中返回 None。
    """
    next_count = Notification.retry_count + 1
    within_budget = next_count <= settings.max_notification_retries
    result = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == NotificationStatus.PROCESSING.value,
            Notification.updated_at < cutoff,
        )
        .values(
            retry_count=next_count,
            status=case(
                (
                    within_budget,
                    NotificationStatus.PENDING.value,
                ),
                else_=NotificationStatus.FAILED.value,
            ),
            error_message=case(
                (
                    within_budget,
                    "处理超时，Worker 可能已中断，已重新入队",
                ),
                else_=(
                    "处理超时超过最大重试次数"
                    f"（{settings.max_notification_retries}），任务已失败"
                ),
            ),
            updated_at=now,
        )
        .returning(Notification.status)
        .execution_options(synchronize_session=False)
    )
    row = result.first()
    db.commit()
    return row.status if row is not None else None


def _claim_stale_pending(
    db: Session, notification_id: int, cutoff: datetime, now: datetime
) -> bool:
    """
    原子地占用一条过期 pending 通知：先刷新 updated_at，再投递。
    多个 Beat 实例同时扫描时，只有一个能成功占用，避免重复投递。
    """
    result = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == NotificationStatus.PENDING.value,
            Notification.updated_at < cutoff,
        )
        .values(updated_at=now)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return (result.rowcount or 0) == 1


def _record_dispatched_task(
    db: Session, notification_id: int, task_id: str | None
) -> None:
    """仅当通知仍为 pending 时回填任务 ID，不覆盖已被 Worker 修改的状态。"""
    db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == NotificationStatus.PENDING.value,
        )
        .values(celery_task_id=task_id, error_message=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()


@celery_app.task(name="notifyhub.requeue_stuck")
def requeue_stuck_notifications_task() -> dict:
    """
    补偿任务（Celery Beat 每 60 秒执行）：
    1. 处理中超时的通知原子重置为 pending 并重新投递（Worker 崩溃场景）。
    2. pending 且长时间未更新的通知原子占用后重新投递（投递失败/消息丢失场景）。

    所有状态修改都使用带 id/status/updated_at 条件的 UPDATE，并根据 rowcount
    判断是否命中，不依赖 Python 内存中的旧 ORM 对象。
    """
    now = _utcnow()
    requeued = 0
    reset = 0
    failed = 0

    with SessionLocal() as db:
        processing_timeout = now - timedelta(seconds=settings.processing_timeout_seconds)
        stale_processing_ids = db.scalars(
            select(Notification.id)
            .where(
                Notification.status == NotificationStatus.PROCESSING.value,
                Notification.updated_at < processing_timeout,
            )
            .limit(100)
        ).all()
        for notification_id in stale_processing_ids:
            outcome = _recover_stale_processing(
                db, notification_id, processing_timeout, now
            )
            if outcome is None:
                logger.info(
                    "超时 processing 已被其他执行者处理或状态已改变，跳过 "
                    "notification_id=%s",
                    notification_id,
                )
                continue
            if outcome == NotificationStatus.FAILED.value:
                failed += 1
                logger.warning(
                    "超时 processing 重试预算已耗尽，标记 failed "
                    "notification_id=%s",
                    notification_id,
                )
                continue

            reset += 1
            try:
                process_notification_task.apply_async(args=[notification_id])
                requeued += 1
            except Exception:
                logger.exception(
                    "超时通知重新入队失败 notification_id=%s", notification_id
                )

        dispatch_stale = now - timedelta(seconds=settings.dispatch_stale_seconds)
        stale_pending_ids = db.scalars(
            select(Notification.id)
            .where(
                Notification.status == NotificationStatus.PENDING.value,
                Notification.updated_at < dispatch_stale,
            )
            .limit(100)
        ).all()
        for notification_id in stale_pending_ids:
            if not _claim_stale_pending(db, notification_id, dispatch_stale, now):
                logger.info(
                    "过期 pending 已被其他执行者占用或状态已改变，跳过 "
                    "notification_id=%s",
                    notification_id,
                )
                continue
            try:
                result = process_notification_task.apply_async(args=[notification_id])
            except Exception:
                logger.exception(
                    "补偿投递失败 notification_id=%s", notification_id
                )
                continue
            try:
                _record_dispatched_task(db, notification_id, result.id)
                requeued += 1
            except Exception:
                logger.exception(
                    "补偿投递成功但回填任务 ID 失败 notification_id=%s",
                    notification_id,
                )

    if reset or requeued or failed:
        logger.info(
            "补偿任务完成 reset=%s failed=%s requeued=%s",
            reset,
            failed,
            requeued,
        )
    return {
        "reset_processing": reset,
        "failed_processing": failed,
        "requeued": requeued,
    }
