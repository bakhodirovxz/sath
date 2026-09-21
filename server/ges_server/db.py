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
        # timeout: parallel yozuvchi (masalan audit zanjiri) qulfni 30 s gacha kutadi
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
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


BASELINE_REV = "0001"  # Alembic dan oldingi sxema (create_all + ensure_columns davri)


def _alembic_config():
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", "ges_server:migrations")
    return cfg


def migrate() -> None:
    """Sxemani Alembic bilan `head` ga keltiradi (server startida, GES_AUTO_MIGRATE=true).

    - bo'sh DB → barcha migratsiyalar;
    - Alembic versiyasiz eski DB (create_all davri) → bir martalik catch-up (`ensure_columns` +
      `create_all`), `BASELINE_REV` ga stamp, keyin `head`;
    - aks holda → `upgrade head`.
    Bir vaqtda faqat bitta jarayon chaqirishi kerak (uvicorn --workers 1).
    """
    from alembic import command

    cfg = _alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        names = set(inspect(conn).get_table_names())
        tables = names - {"alembic_version"}
        if not tables:
            if "alembic_version" in names:
                conn.exec_driver_sql("DROP TABLE alembic_version")
            command.upgrade(cfg, "head")
        elif "alembic_version" not in names:
            log.warning("DB Alembic versiyasiz (eski sxema) — %s ga stamp qilinadi", BASELINE_REV)
            _legacy_catch_up(conn)
            command.stamp(cfg, BASELINE_REV)
            command.upgrade(cfg, "head")
        else:
            command.upgrade(cfg, "head")


def stamp_head() -> None:
    """Testlar uchun: `create_all` dan keyin versiyani `head` deb belgilaydi."""
    from alembic import command

    cfg = _alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.stamp(cfg, "head")


def assert_at_head() -> None:
    """GES_AUTO_MIGRATE=false: sxema `head` da bo'lmasa serverni ishga tushirmaydi."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    heads = set(ScriptDirectory.from_config(_alembic_config()).get_heads())
    with engine.connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    if current != heads:
        raise RuntimeError(
            f"DB sxemasi eskirgan (joriy {sorted(current) or '-'}, kerak {sorted(heads)}): "
            "`alembic upgrade head` bajaring yoki GES_AUTO_MIGRATE=true qo'ying"
        )


def _legacy_catch_up(conn) -> None:
    """Alembic dan oldingi DB ni baseline holatiga keltiradi (bir marta, stamp dan oldin).

    Baseline dan ham eski DB da yetishmagan ustunlar/jadvallar bo'lishi mumkin — `ensure_columns`
    va `create_all` ularni qo'shadi. Keyingi relizda olib tashlanadi.
    """
    from . import orm  # noqa: F401  (barcha modellar Base.metadata da ro'yxatga olinsin)

    _ensure_columns_on(conn)
    Base.metadata.create_all(conn)


def ensure_columns() -> None:
    """Eski yengil migratsiya (faqat `migrate()` legacy yo'li uchun saqlanadi)."""
    with engine.begin() as conn:
        _ensure_columns_on(conn)


def _ensure_columns_on(conn) -> None:
    """Modelda bor, jadvalda yo'q ustunlarni ADD COLUMN qiladi. Ustun o'chirish/o'zgartirish yo'q."""
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            if col.default is not None and getattr(col.default, "is_scalar", False):
                v = col.default.arg
                ddl += (
                    f" DEFAULT {v!r}"
                    if isinstance(v, str)
                    else f" DEFAULT {int(v) if isinstance(v, bool) else v}"
                )
            log.warning("DB migratsiya (legacy): %s", ddl)
            conn.execute(text(ddl))
