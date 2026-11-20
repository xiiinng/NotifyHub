import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
VALID_SECRET = "x" * 48
INSECURE_SECRET = "dev-only-secret-change-me-use-env-in-production"


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_missing_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(environment="development", jwt_secret_key="")
    with pytest.raises(ValidationError):
        make_settings(environment="development", jwt_secret_key="   ")


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(environment="development", jwt_secret_key="too-short")


def test_production_rejects_insecure_jwt_secret():
    with pytest.raises(ValidationError):
        make_settings(environment="production", jwt_secret_key=INSECURE_SECRET)
    with pytest.raises(ValidationError):
        make_settings(
            environment="production",
            jwt_secret_key="placeholder-secret-placeholder-secret",
        )


def test_production_accepts_strong_jwt_secret():
    config = make_settings(environment="production", jwt_secret_key=VALID_SECRET)
    assert config.is_production is True


def test_environment_whitelist():
    with pytest.raises(ValidationError):
        make_settings(environment="prod", jwt_secret_key=VALID_SECRET)
    with pytest.raises(ValidationError):
        make_settings(environment="staging", jwt_secret_key=VALID_SECRET)


def test_environment_is_case_insensitive():
    config = make_settings(environment="Production", jwt_secret_key=VALID_SECRET)
    assert config.environment == "production"


def test_test_environment_accepts_dedicated_test_secret():
    config = make_settings(
        environment="test",
        jwt_secret_key="test-only-jwt-secret-0123456789abcdef0123456789",
    )
    assert config.environment == "test"


def _run_app_import(tmp_path, secret: str, environment: str = "development"):
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": environment,
            "JWT_SECRET_KEY": secret,
            "DATABASE_URL": (
                "postgresql+psycopg://notifyhub@localhost:5432/notifyhub"
            ),
            "REDIS_URL": "redis://localhost:6379/0",
            "PYTHONPATH": str(BACKEND_DIR),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def test_app_startup_fails_without_secret(tmp_path):
    result = _run_app_import(tmp_path, secret="")
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


def test_app_startup_succeeds_with_valid_secret(tmp_path):
    result = _run_app_import(tmp_path, secret=VALID_SECRET)
    assert result.returncode == 0, result.stderr


def test_time_limits_must_be_ordered():
    with pytest.raises(ValidationError):
        make_settings(
            environment="test",
            jwt_secret_key=VALID_SECRET,
            notification_soft_time_limit_seconds=10,
            notification_time_limit_seconds=10,
        )
    with pytest.raises(ValidationError):
        make_settings(
            environment="test",
            jwt_secret_key=VALID_SECRET,
            notification_time_limit_seconds=300,
            processing_timeout_seconds=300,
        )


def test_default_time_limits_are_coordinated():
    config = make_settings(environment="test", jwt_secret_key=VALID_SECRET)
    assert (
        config.notification_soft_time_limit_seconds
        < config.notification_time_limit_seconds
        < config.processing_timeout_seconds
    )
    assert config.external_delivery_timeout_seconds > 0
