from app.core.config import settings
from app.tasks.celery_app import celery_app


def test_time_limits_and_worker_lost_policy_are_configured():
    assert (
        celery_app.conf.task_soft_time_limit
        == settings.notification_soft_time_limit_seconds
    )
    assert (
        celery_app.conf.task_time_limit
        == settings.notification_time_limit_seconds
    )
    assert (
        celery_app.conf.task_soft_time_limit
        < celery_app.conf.task_time_limit
        < settings.processing_timeout_seconds
    )
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
