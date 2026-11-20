from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.notification import Notification
from app.tasks.notify import (
    _claim_stale_pending,
    _recover_stale_processing,
    _utcnow,
    process_notification_task,
    requeue_stuck_notifications_task,
)


def _create_notification(db, user_id, content="通知内容", status="pending"):
    notification = Notification(
        user_id=user_id,
        title="异步通知",
        content=content,
        status=status,
        retry_count=0,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification.id


def _reload(db, notification_id):
    db.expire_all()
    return db.get(Notification, notification_id)


def test_task_processes_notification_successfully(
    db, user_a, task_db, eager_celery
):
    notification_id = _create_notification(db, user_a["profile"]["id"])

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "success"
    assert notification.retry_count == 0
    assert notification.error_message is None


def test_task_is_idempotent_for_finished_notification(
    db, user_a, task_db, eager_celery
):
    notification_id = _create_notification(db, user_a["profile"]["id"])
    process_notification_task.apply_async(args=[notification_id])

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "success"
    assert notification.retry_count == 0


def test_task_skips_recent_processing_notification(
    db, user_a, task_db, eager_celery
):
    notification_id = _create_notification(
        db, user_a["profile"]["id"], status="processing"
    )

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "processing"


def test_task_retries_and_marks_failed_after_max_retries(
    db, user_a, task_db, eager_celery, monkeypatch
):
    monkeypatch.setattr(settings, "allow_failure_simulation", True)
    monkeypatch.setattr(settings, "max_notification_retries", 1)
    monkeypatch.setattr(settings, "retry_backoff_base_seconds", 0)

    notification_id = _create_notification(
        db, user_a["profile"]["id"], content="强制失败 [FAIL]"
    )

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    # 第一次失败 -> 重试一次；第二次失败 -> 超过最大重试次数
    assert notification.retry_count == 2
    assert notification.status == "failed"
    assert "超过最大重试次数" in notification.error_message


def test_task_recovers_processing_timeout(db, user_a, task_db, eager_celery):
    notification_id = _create_notification(
        db, user_a["profile"]["id"], status="processing"
    )
    notification = db.get(Notification, notification_id)
    notification.updated_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.processing_timeout_seconds + 10
    )
    db.commit()

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "success"
    # 超时接管消耗了一次重试预算
    assert notification.retry_count == 1


def test_compensation_requeues_stale_pending(db, user_a, task_db, eager_celery):
    notification_id = _create_notification(db, user_a["profile"]["id"])
    notification = db.get(Notification, notification_id)
    notification.updated_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.dispatch_stale_seconds + 10
    )
    db.commit()

    result = requeue_stuck_notifications_task.apply().get()

    assert result["requeued"] >= 1
    notification = _reload(db, notification_id)
    assert notification.status == "success"


def test_compensation_resets_stuck_processing(db, user_a, task_db, eager_celery):
    notification_id = _create_notification(
        db, user_a["profile"]["id"], status="processing"
    )
    notification = db.get(Notification, notification_id)
    notification.updated_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.processing_timeout_seconds + 10
    )
    db.commit()

    result = requeue_stuck_notifications_task.apply().get()

    assert result["reset_processing"] >= 1
    notification = _reload(db, notification_id)
    assert notification.status == "success"
    assert notification.retry_count == 1


def _make_stale_processing(db, user_id, seconds=600, retry_count=0):
    notification_id = _create_notification(db, user_id, status="processing")
    notification = db.get(Notification, notification_id)
    notification.retry_count = retry_count
    notification.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    db.commit()
    return notification_id


def _make_stale_pending(db, user_id, seconds=600):
    notification_id = _create_notification(db, user_id, status="pending")
    notification = db.get(Notification, notification_id)
    notification.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    db.commit()
    return notification_id


def test_claim_stale_processing_does_not_override_success(db, user_a):
    notification_id = _make_stale_processing(db, user_a["profile"]["id"])
    notification = db.get(Notification, notification_id)
    notification.status = "success"
    db.commit()

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)
    assert _recover_stale_processing(db, notification_id, cutoff, now) is None

    notification = _reload(db, notification_id)
    assert notification.status == "success"


def test_claim_stale_processing_does_not_override_failed(db, user_a):
    notification_id = _make_stale_processing(db, user_a["profile"]["id"])
    notification = db.get(Notification, notification_id)
    notification.status = "failed"
    db.commit()

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)
    assert _recover_stale_processing(db, notification_id, cutoff, now) is None

    notification = _reload(db, notification_id)
    assert notification.status == "failed"


def test_claim_stale_processing_only_succeeds_once(db, user_a):
    notification_id = _make_stale_processing(db, user_a["profile"]["id"])

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)
    assert _recover_stale_processing(db, notification_id, cutoff, now) == "pending"
    # 模拟第二个补偿任务同时执行：条件更新不再命中，预算只消耗一次
    assert _recover_stale_processing(db, notification_id, cutoff, now) is None

    notification = _reload(db, notification_id)
    assert notification.status == "pending"
    assert notification.retry_count == 1
    assert "Worker 可能已中断" in notification.error_message


def test_claim_stale_pending_does_not_override_processing(db, user_a):
    notification_id = _make_stale_pending(db, user_a["profile"]["id"])
    notification = db.get(Notification, notification_id)
    notification.status = "processing"
    db.commit()

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.dispatch_stale_seconds + 10)
    assert _claim_stale_pending(db, notification_id, cutoff, now) is False

    notification = _reload(db, notification_id)
    assert notification.status == "processing"


def test_claim_stale_pending_only_succeeds_once(db, user_a):
    notification_id = _make_stale_pending(db, user_a["profile"]["id"])

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.dispatch_stale_seconds + 10)
    assert _claim_stale_pending(db, notification_id, cutoff, now) is True
    # 第二个执行者拿不到同一行的“投递占用”
    assert _claim_stale_pending(db, notification_id, cutoff, now) is False

    notification = _reload(db, notification_id)
    assert notification.status == "pending"


@pytest.mark.parametrize("terminal_status", ["success", "failed"])
def test_compensation_never_overwrites_terminal_status(
    db, user_a, task_db, eager_celery, terminal_status
):
    notification_id = _create_notification(
        db, user_a["profile"]["id"], status=terminal_status
    )
    notification = db.get(Notification, notification_id)
    notification.updated_at = datetime.now(timezone.utc) - timedelta(seconds=600)
    db.commit()

    result = requeue_stuck_notifications_task.apply().get()

    assert result == {
        "reset_processing": 0,
        "failed_processing": 0,
        "requeued": 0,
    }
    notification = _reload(db, notification_id)
    assert notification.status == terminal_status


def test_recover_stale_processing_consumes_retry_budget(db, user_a):
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=0
    )
    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)

    assert _recover_stale_processing(db, notification_id, cutoff, now) == "pending"

    notification = _reload(db, notification_id)
    assert notification.retry_count == 1
    assert notification.status == "pending"


def test_recover_stale_processing_fails_when_budget_exhausted(db, user_a):
    max_retries = settings.max_notification_retries
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=max_retries
    )
    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)

    assert _recover_stale_processing(db, notification_id, cutoff, now) == "failed"

    notification = _reload(db, notification_id)
    assert notification.status == "failed"
    assert notification.retry_count == max_retries + 1
    assert "超过最大重试次数" in notification.error_message


def test_repeated_crashes_stop_after_budget(db, user_a, monkeypatch):
    monkeypatch.setattr(settings, "max_notification_retries", 2)
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=0
    )

    for attempt in range(1, 3):
        now = _utcnow()
        cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)
        assert _recover_stale_processing(db, notification_id, cutoff, now) == "pending"
        notification = _reload(db, notification_id)
        assert notification.retry_count == attempt
        # 模拟下一次 Worker 崩溃
        notification.status = "processing"
        notification.updated_at = datetime.now(timezone.utc) - timedelta(seconds=600)
        db.commit()

    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)
    assert _recover_stale_processing(db, notification_id, cutoff, now) == "failed"
    notification = _reload(db, notification_id)
    assert notification.status == "failed"
    assert notification.retry_count == 3


def test_concurrent_recovery_consumes_budget_once(db, user_a, task_db):
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=0
    )
    now = _utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds + 10)

    session_one = task_db()
    session_two = task_db()
    try:
        first = _recover_stale_processing(session_one, notification_id, cutoff, now)
        second = _recover_stale_processing(session_two, notification_id, cutoff, now)
    finally:
        session_one.close()
        session_two.close()

    assert first == "pending"
    assert second is None
    notification = _reload(db, notification_id)
    assert notification.retry_count == 1


def test_compensation_marks_failed_when_budget_exhausted(
    db, user_a, task_db, eager_celery
):
    max_retries = settings.max_notification_retries
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=max_retries
    )

    result = requeue_stuck_notifications_task.apply().get()

    assert result["failed_processing"] == 1
    assert result["reset_processing"] == 0
    assert result["requeued"] == 0
    notification = _reload(db, notification_id)
    assert notification.status == "failed"
    assert notification.retry_count == max_retries + 1


def test_task_stale_takeover_fails_when_budget_exhausted(
    db, user_a, task_db, eager_celery
):
    max_retries = settings.max_notification_retries
    notification_id = _make_stale_processing(
        db, user_a["profile"]["id"], retry_count=max_retries
    )

    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "failed"
    assert notification.retry_count == max_retries + 1
    assert "超过最大重试次数" in notification.error_message


def test_soft_time_limit_is_recorded_as_clear_failure(
    db, user_a, task_db, eager_celery, monkeypatch
):
    from billiard.exceptions import SoftTimeLimitExceeded

    def raise_soft_limit(notification):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(
        "app.tasks.notify.deliver_notification", raise_soft_limit
    )
    monkeypatch.setattr(settings, "max_notification_retries", 0)

    notification_id = _create_notification(db, user_a["profile"]["id"])
    process_notification_task.apply_async(args=[notification_id])

    notification = _reload(db, notification_id)
    assert notification.status == "failed"
    assert notification.retry_count == 1
    assert "任务执行超时" in notification.error_message
