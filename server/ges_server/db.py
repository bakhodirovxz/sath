import logging
from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event, inspect, text
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
    - Alembic versiyasiz eski DB (create_all davri) → bir martalik catch-up baseline sxemasigacha,
      `BASELINE_REV` ga stamp, keyin `head`;
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


def _baseline_metadata() -> MetaData:
    """`BASELINE_REV` migratsiyasini xotiradagi SQLite da bajarib, o'sha sxemani reflect qiladi."""
    from alembic import command

    mem = create_engine("sqlite://")
    cfg = _alembic_config()
    with mem.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, BASELINE_REV)
    md = MetaData()
    md.reflect(bind=mem)
    md.remove(md.tables["alembic_version"])
    mem.dispose()
    return md


def _legacy_catch_up(conn) -> None:
    """Alembic dan oldingi DB ni aynan baseline holatiga keltiradi (bir marta, stamp dan oldin).

    Baseline dan ham eski DB da yetishmagan ustunlar/jadvallar bo'lishi mumkin; ular baseline
    sxemasidan (hozirgi ORM dan emas — keyingi migratsiyalar ikki marta qo'shmasin) olinadi.
    Keyingi relizda olib tashlanadi.
    """
    from . import orm  # noqa: F401  (python default lar uchun Base.metadata to'liq bo'lsin)

    base_md = _baseline_metadata()
    insp = inspect(conn)
    existing_tables = set(insp.get_table_names())
    missing = [t for t in base_md.sorted_tables if t.name not in existing_tables]
    if missing:
        log.warning("DB migratsiya (legacy): jadvallar %s", [t.name for t in missing])
        base_md.create_all(conn, tables=missing)
    for table in base_md.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        orm_table = Base.metadata.tables.get(table.name)
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            orm_col = orm_table.columns.get(col.name) if orm_table is not None else None
            default = orm_col.default if orm_col is not None else None
            v = default.arg if default is not None and getattr(default, "is_scalar", False) else None
            if v is None and not col.nullable:
                v = _type_default(col.type)
            if v is not None:
                ddl += f" DEFAULT {v!r}" if isinstance(v, str) else f" DEFAULT {int(v)}"
                if not col.nullable:
                    ddl += " NOT NULL"
            log.warning("DB migratsiya (legacy): %s", ddl)
            conn.execute(text(ddl))


def _type_default(t) -> str | int | None:
    """NOT NULL ustun uchun turga qarab bo'sh default (legacy catch-up)."""
    from sqlalchemy import JSON, Boolean, Float, Integer, String, Text

    if isinstance(t, JSON):
        return "{}"
    if isinstance(t, String | Text):
        return ""
    if isinstance(t, Integer | Float | Boolean):
        return 0
    return None
