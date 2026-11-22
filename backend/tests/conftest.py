import os
from pathlib import Path

TEST_JWT_SECRET = "test-only-jwt-secret-0123456789abcdef0123456789"

os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET
os.environ.setdefault("ALLOW_FAILURE_SIMULATION", "true")

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fakeredis import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.core.rate_limit import LoginRateLimiter, get_login_limiter
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _derive_test_database_url() -> str:
    if settings.test_database_url:
        return settings.test_database_url
    url = make_url(settings.database_url)
    if not url.database:
        raise RuntimeError("DATABASE_URL 必须包含数据库名")
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


TEST_DATABASE_URL = _derive_test_database_url()


def _assert_safe_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    dev_url = make_url(settings.database_url)
    assert url.database and url.database.endswith("_test"), "测试库名必须以 _test 结尾"
    assert url.database not in {"notifyhub", "postgres"}, (
        f"拒绝连接非测试库：{url.database}"
    )
    assert url.database != dev_url.database, "测试库不能与开发库同名"


def _ensure_test_database() -> None:
    """仅创建独立测试库；库名必须以 _test 结尾，防止误伤开发库。"""
    _assert_safe_test_database()
    url = make_url(TEST_DATABASE_URL)

    admin_engine = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _upgrade_test_database() -> str:
    """用 Alembic 初始化测试库，并重复执行一次验证幂等。返回 head revision。"""
    _assert_safe_test_database()
    config = _alembic_config(TEST_DATABASE_URL)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert current == head, f"测试库 revision {current} != head {head}"
    return head


engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    _ensure_test_database()
    _upgrade_test_database()
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE ticket_notification_events, ticket_comments, "
                "ticket_history, tickets, notifications, "
                "notification_templates, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture(autouse=True)
def override_db_dependency():
    def _get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def fake_login_limiter():
    """所有测试使用内存 Redis，不依赖本机 Redis 服务。"""
    limiter = LoginRateLimiter(FakeRedis(decode_responses=True))
    app.dependency_overrides[get_login_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.pop(get_login_limiter, None)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def task_db(monkeypatch):
    """让 Celery 任务使用测试库，而不是开发库。"""
    monkeypatch.setattr("app.tasks.notify.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


@pytest.fixture
def no_dispatch(monkeypatch):
    """同步 API 测试中拦截 Celery 投递，并记录投递过的通知 id。"""
    dispatched: list[int] = []

    def fake_dispatch(notification):
        notification.celery_task_id = "test-task-id"
        dispatched.append(notification.id)

    monkeypatch.setattr(
        "app.services.notification_service._dispatch", fake_dispatch
    )
    return dispatched


@pytest.fixture
def eager_celery():
    """测试中同步执行 Celery 任务，不依赖真实 Worker 与 Broker。"""
    from app.tasks.celery_app import celery_app

    previous = {
        "task_always_eager": celery_app.conf.task_always_eager,
        "task_eager_propagates": celery_app.conf.task_eager_propagates,
        "broker_url": celery_app.conf.broker_url,
    }
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    celery_app.conf.broker_url = "memory://"
    try:
        yield celery_app
    finally:
        for key, value in previous.items():
            setattr(celery_app.conf, key, value)


from tests.helpers import auth_headers, register


@pytest.fixture
def user_a(client):
    response = register(client)
    assert response.status_code == 201, response.text
    return {
        "profile": response.json(),
        "headers": auth_headers(client),
    }


@pytest.fixture
def user_b(client):
    response = register(client, email="bob@example.com", username="bob")
    assert response.status_code == 201, response.text
    return {
        "profile": response.json(),
        "headers": auth_headers(client, email="bob@example.com"),
    }


@pytest.fixture
def support_user(client, db):
    user = User(
        username="support",
        email="support@example.com",
        hashed_password=hash_password("Support123!"),
        role=UserRole.IT_SUPPORT.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "profile": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
        },
        "headers": auth_headers(
            client, email="support@example.com", password="Support123!"
        ),
        "user": user,
    }
