from celery import Celery

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

celery_app = Celery(
    "notifyhub",
    broker=settings.broker_url,
    include=["app.tasks.notify"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # 软/硬时间限制；Windows solo 无法可靠执行基于 SIGUSR1 的软超时，
    # Docker Linux prefork 下生效。Beat 恢复是 Windows 下的兜底。
    task_soft_time_limit=settings.notification_soft_time_limit_seconds,
    task_time_limit=settings.notification_time_limit_seconds,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 2,
    },
    beat_schedule={
        "requeue-stuck-notifications": {
            "task": "notifyhub.requeue_stuck",
            "schedule": 60.0,
        },
        "check-ticket-sla": {
            "task": "notifyhub.check_ticket_sla",
            "schedule": 300.0,
        },
    },
)
