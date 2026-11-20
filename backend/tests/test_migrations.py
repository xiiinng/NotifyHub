from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_test_database_revision_matches_alembic_head(db):
    database_name = db.get_bind().url.database
    assert database_name and database_name.endswith("_test")
    assert database_name not in {"notifyhub", "postgres"}

    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert current == head


def test_upgrade_head_is_idempotent(db):
    database_url = db.get_bind().url.render_as_string(hide_password=False)
    config = _alembic_config(database_url)
    head = ScriptDirectory.from_config(config).get_current_head()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with db.get_bind().connect() as connection:
        current = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert current == head
