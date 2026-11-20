import hashlib
from functools import lru_cache

from fastapi import Request
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.core.config import settings

_KEY_PREFIX = "notifyhub:login:fail"
_CONNECT_TIMEOUT_SECONDS = 0.5
_SOCKET_TIMEOUT_SECONDS = 0.5


class LoginRateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = max(int(retry_after), 1)
        super().__init__("login rate limited")


class RateLimitUnavailable(Exception):
    """Redis 不可用时的明确降级信号；登录接口将返回 503。"""


def get_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            # Nginx 作为可信入口会覆盖该头，取第一跳即可
            return forwarded.split(",")[0].strip()[:64] or "unknown"
    return request.client.host if request.client else "unknown"


def _hash_email(email: str) -> str:
    normalized = email.strip().lower().encode()
    return hashlib.sha256(normalized).hexdigest()


class LoginRateLimiter:
    """基于 Redis 的固定窗口失败计数器，同时限制 IP 与邮箱维度。"""

    def __init__(self, client: Redis):
        self.client = client

    @staticmethod
    def _ip_key(ip: str) -> str:
        return f"{_KEY_PREFIX}:ip:{ip}"

    @staticmethod
    def _email_key(email: str) -> str:
        return f"{_KEY_PREFIX}:email:{_hash_email(email)}"

    def check(self, ip: str, email: str) -> None:
        limits = (
            (
                self._ip_key(ip),
                settings.login_rate_limit_ip_max,
                settings.login_rate_limit_ip_window,
            ),
            (
                self._email_key(email),
                settings.login_rate_limit_email_max,
                settings.login_rate_limit_email_window,
            ),
        )
        try:
            for key, max_attempts, window in limits:
                count = int(self.client.get(key) or 0)
                if count < max_attempts:
                    continue
                ttl = int(self.client.ttl(key))
                retry_after = ttl if ttl > 0 else window
                raise LoginRateLimitExceeded(retry_after)
        except RedisError as exc:
            raise RateLimitUnavailable("redis unavailable") from exc

    def record_failure(self, ip: str, email: str) -> None:
        limits = (
            (self._ip_key(ip), settings.login_rate_limit_ip_window),
            (self._email_key(email), settings.login_rate_limit_email_window),
        )
        try:
            for key, window in limits:
                count = self.client.incr(key)
                # 计数键首次创建或意外丢失 TTL 时补上过期时间，避免永久锁定
                if count == 1 or int(self.client.ttl(key)) < 0:
                    self.client.expire(key, window)
        except RedisError as exc:
            raise RateLimitUnavailable("redis unavailable") from exc

    def reset_email(self, email: str) -> None:
        try:
            self.client.delete(self._email_key(email))
        except RedisError as exc:
            raise RateLimitUnavailable("redis unavailable") from exc


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        # Redis 8 默认会重试 10 次；登录降级必须快速失败，不能等待重试链
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
    )


@lru_cache
def get_login_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(get_redis_client())
