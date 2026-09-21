"""Alembic muhiti.

Ikki rejim:
- dasturiy: `ges_server.db.migrate()` `config.attributes["connection"]` orqali ochiq ulanish beradi;
- CLI: `alembic upgrade head` — GES_DATABASE_URL (yoki alembic.ini sqlalchemy.url) dan engine yaratiladi.
"""

from alembic import context
from sqlalchemy import create_engine

from ges_server.config import get_settings
from ges_server.orm import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER cheklovlari uchun jadvalni qayta qurish
        compare_type=True,
        transaction_per_migration=True,
    )


def _run(connection) -> None:
    if connection.dialect.name == "sqlite":
        # batch rejimida jadval qayta qurilganda FK lar _alembic_tmp_* ga ko'chib ketmasin
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    engine = create_engine(url)
    with engine.begin() as conn:
        _run(conn)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
