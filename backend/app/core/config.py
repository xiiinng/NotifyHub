from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_ENVIRONMENTS = {"development", "test", "production"}

# 生产环境拒绝这些明显的默认/示例密钥
_INSECURE_SECRET_MARKERS = (
    "change-me",
    "changeme",
    "dev-only",
    "secret-change-me",
    "placeholder",
)


class Settings(BaseSettings):
    """全部配置从环境变量或 .env 读取，代码中不再硬编码敏感信息。"""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "NotifyHub"
    environment: str = "development"  # development / test / production
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # 默认 URL 不包含密码，真实密码必须来自环境变量或 .env。
    # 使用 127.0.0.1 而非 localhost，避免 Windows 下优先解析到 IPv6 导致连接等待。
    database_url: str = (
        "postgresql+psycopg://notifyhub@127.0.0.1:5432/notifyhub"
    )
    database_echo: bool = False
    # 留空时测试代码自动从 DATABASE_URL 派生 notifyhub_test
    test_database_url: str = ""

    redis_url: str = "redis://127.0.0.1:6379/0"

    # 不再提供可用默认值：缺失或为空时应用拒绝启动
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    max_notification_retries: int = 3
    retry_backoff_base_seconds: int = 5
    processing_timeout_seconds: int = 300
    dispatch_stale_seconds: int = 120
    # Celery 软/硬时间限制，必须满足 soft < hard < processing_timeout
    notification_soft_time_limit_seconds: int = Field(default=240, gt=0)
    notification_time_limit_seconds: int = Field(default=280, gt=0)
    # 未来接入邮件/短信/HTTP 渠道时，单次网络请求应使用的超时
    external_delivery_timeout_seconds: int = Field(default=10, gt=0)
    # 仅开发/演示环境可开启：
    #   [FAIL] 抛错模拟失败；[SLOW] 模拟慢投递用于验证时间限制
    allow_failure_simulation: bool = False

    # 位于可信反向代理（如 Docker Nginx）之后时才可开启
    trust_proxy_headers: bool = False

    # 登录限流：失败次数 / 时间窗口（秒）
    login_rate_limit_ip_max: int = Field(default=20, gt=0)
    login_rate_limit_ip_window: int = Field(default=60, gt=0)
    login_rate_limit_email_max: int = Field(default=5, gt=0)
    login_rate_limit_email_window: int = Field(default=300, gt=0)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_ENVIRONMENTS:
            allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
            raise ValueError(f"ENVIRONMENT 必须是以下之一：{allowed}")
        return normalized

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "Settings":
        secret = self.jwt_secret_key.strip()
        if not secret:
            raise ValueError(
                "JWT_SECRET_KEY 必须通过环境变量或 .env 设置，且不能为空"
            )
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY 长度至少需要 32 个字符")
        if self.is_production and any(
            marker in secret.lower() for marker in _INSECURE_SECRET_MARKERS
        ):
            raise ValueError("生产环境不允许使用默认或示例 JWT_SECRET_KEY")
        self.jwt_secret_key = secret
        return self

    @model_validator(mode="after")
    def validate_time_limits(self) -> "Settings":
        if (
            self.notification_soft_time_limit_seconds
            >= self.notification_time_limit_seconds
        ):
            raise ValueError(
                "NOTIFICATION_SOFT_TIME_LIMIT_SECONDS 必须小于 "
                "NOTIFICATION_TIME_LIMIT_SECONDS"
            )
        if self.notification_time_limit_seconds >= self.processing_timeout_seconds:
            raise ValueError(
                "NOTIFICATION_TIME_LIMIT_SECONDS 必须小于 "
                "PROCESSING_TIMEOUT_SECONDS，避免 Beat 先于 Worker 超时恢复"
            )
        return self

    @property
    def broker_url(self) -> str:
        return self.redis_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
