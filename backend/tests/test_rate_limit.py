import time

from redis.exceptions import RedisError

from app.core.config import settings
from tests.helpers import DEFAULT_PASSWORD, login, register


def wrong_login(client, email, forwarded_ip: str | None = None):
    headers = {"X-Forwarded-For": forwarded_ip} if forwarded_ip else {}
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPass123"},
        headers=headers,
    )


def test_normal_login_is_not_affected(client):
    assert register(client).status_code == 201
    response = login(client)
    assert response.status_code == 200


def test_login_rate_limit_by_email(client, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(settings, "login_rate_limit_email_window", 60)
    monkeypatch.setattr(settings, "login_rate_limit_ip_max", 100)
    monkeypatch.setattr(settings, "login_rate_limit_ip_window", 60)

    assert register(client).status_code == 201
    assert wrong_login(client, "alice@example.com").status_code == 401
    assert wrong_login(client, "alice@example.com").status_code == 401

    blocked = wrong_login(client, "alice@example.com")
    assert blocked.status_code == 429
    assert "登录尝试过于频繁" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) >= 1


def test_login_rate_limit_by_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "login_rate_limit_ip_max", 2)
    monkeypatch.setattr(settings, "login_rate_limit_ip_window", 60)
    monkeypatch.setattr(settings, "login_rate_limit_email_max", 100)
    monkeypatch.setattr(settings, "login_rate_limit_email_window", 60)

    ip = "203.0.113.10"
    assert wrong_login(client, "one@example.com", ip).status_code == 401
    assert wrong_login(client, "two@example.com", ip).status_code == 401
    assert wrong_login(client, "three@example.com", ip).status_code == 429

    # 另一个 IP 不受该 IP 计数影响
    assert wrong_login(client, "four@example.com", "203.0.113.11").status_code == 401


def test_login_rate_limit_window_expires(client, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_email_max", 1)
    monkeypatch.setattr(settings, "login_rate_limit_email_window", 1)
    monkeypatch.setattr(settings, "login_rate_limit_ip_max", 100)
    monkeypatch.setattr(settings, "login_rate_limit_ip_window", 60)

    assert register(client).status_code == 201
    assert wrong_login(client, "alice@example.com").status_code == 401
    assert wrong_login(client, "alice@example.com").status_code == 429

    time.sleep(1.2)
    assert login(client).status_code == 200


def test_successful_login_resets_email_failures(client, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(settings, "login_rate_limit_email_window", 60)
    monkeypatch.setattr(settings, "login_rate_limit_ip_max", 100)
    monkeypatch.setattr(settings, "login_rate_limit_ip_window", 60)

    assert register(client).status_code == 201
    assert wrong_login(client, "alice@example.com").status_code == 401
    assert login(client).status_code == 200

    # 成功登录清除了邮箱失败计数，仍可继续失败两次
    assert wrong_login(client, "alice@example.com").status_code == 401
    assert wrong_login(client, "alice@example.com").status_code == 401
    assert wrong_login(client, "alice@example.com").status_code == 429


class BrokenRedis:
    def get(self, *args, **kwargs):
        raise RedisError("redis down")

    def incr(self, *args, **kwargs):
        raise RedisError("redis down")

    def ttl(self, *args, **kwargs):
        raise RedisError("redis down")

    def expire(self, *args, **kwargs):
        raise RedisError("redis down")

    def delete(self, *args, **kwargs):
        raise RedisError("redis down")


def test_login_fails_closed_when_redis_unavailable(client, fake_login_limiter):
    fake_login_limiter.client = BrokenRedis()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 503
    assert "登录服务暂时不可用" in response.json()["detail"]
