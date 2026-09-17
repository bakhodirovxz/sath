import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


log = logging.getLogger("ges_server.db")


def ensure_columns() -> None:
    """Yengil migratsiya: modelda bor, jadvalda yo'q ustunlarni ADD COLUMN qiladi.

    Alembic siz — yangi versiyaga o'tganda ma'lumotlar saqlanadi. Ustun o'chirish/o'zgartirish qilmaydi.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}"
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    ddl += (
                        f" DEFAULT {v!r}"
                        if isinstance(v, str)
                        else f" DEFAULT {int(v) if isinstance(v, bool) else v}"
                    )
                log.warning("DB migratsiya: %s", ddl)
                conn.execute(text(ddl))
