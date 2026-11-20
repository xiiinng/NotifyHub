import time

from app.core.config import settings
from app.core.logging import get_logger
from app.models.notification import Notification

logger = get_logger(__name__)

_SLOW_SIMULATION_SECONDS = 15


class DeliveryError(Exception):
    pass


def deliver_notification(notification: Notification) -> None:
    """
    第一版站内通知的"投递"：通知记录本身即收件箱，这里做投递前的校验与日志。
    后续接入邮件/短信时，只需替换本函数，任务层与状态机无需改动。
    """
    if not notification.title or not notification.content:
        raise DeliveryError("通知内容为空")

    if settings.allow_failure_simulation and "[FAIL]" in notification.content:
        raise DeliveryError("模拟投递失败（演示/测试开关已开启）")

    if settings.allow_failure_simulation and "[SLOW]" in notification.content:
        # 仅用于验证 Celery soft/hard time limit，不会在默认配置下触发
        time.sleep(_SLOW_SIMULATION_SECONDS)

    # 未来接入邮件/短信/HTTP 渠道时：
    # 单次网络请求必须使用 settings.external_delivery_timeout_seconds，
    # 并在此处捕获超时异常，交给任务重试逻辑处理。

    logger.info(
        "站内通知已投递 notification_id=%s user_id=%s title=%s",
        notification.id,
        notification.user_id,
        notification.title,
    )
