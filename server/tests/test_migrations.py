"""Alembic migratsiyalari: eski sxemadan head ga, ORM bilan drift yo'q, downgrade ishlaydi.

Global test enginei emas — har test o'z vaqtinchalik SQLite faylida ishlaydi.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from ges_server import db as gdb
from ges_server.orm import Base
from sqlalchemy import create_engine, inspect, text


def _cfg(conn) -> Config:
    cfg = gdb._alembic_config()
    cfg.attributes["connection"] = conn
    return cfg


def _engine(tmp_path):
    return create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")


def _current(conn) -> str | None:
    return MigrationContext.configure(conn).get_current_revision()


def test_upgrade_from_baseline_keeps_data(tmp_path):
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), gdb.BASELINE_REV)
        assert _current(conn) == gdb.BASELINE_REV
        conn.execute(
            text(
                "INSERT INTO users (id, username, full_name, email, password_hash, is_admin, "
                "is_active, created_at) VALUES (1, 'a', 'A', '', 'x', 1, 1, '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO projects (id, name, description, location, dashboard, site, "
                "created_by, created_at) VALUES (1, 'P', '', '', '{}', '{}', 1, '2026-01-01 00:00:00')"
            )
        )
        for i in range(3):
            conn.execute(
                text(
                    "INSERT INTO audit_log (user_id, action, target_type, target_id, project_id, "
                    "detail, created_at) VALUES (1, 'a.b', 'x', :i, 1, '{\"k\": 1}', "
                    "'2026-01-01 00:00:0" + str(i) + ".000000')"
                ),
                {"i": i},
            )
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        assert _current(conn) != gdb.BASELINE_REV or _heads() == {gdb.BASELINE_REV}
        assert conn.execute(text("SELECT count(*) FROM projects")).scalar() == 1
        # audit zanjiri backfill: barcha qatorlar ulangan
        rows = conn.execute(
            text("SELECT prev_hash, row_hash FROM audit_log ORDER BY id")
        ).all()
        assert rows[0][0] == "" and all(r[1] for r in rows)
        assert [r[0] for r in rows[1:]] == [r[1] for r in rows[:-1]]
    from ges_server import audit
    from sqlalchemy.orm import Session

    with Session(eng) as db:
        assert audit.verify_chain(db)["ok"]


def _heads() -> set[str]:
    from alembic.script import ScriptDirectory

    return set(ScriptDirectory.from_config(gdb._alembic_config()).get_heads())


def test_head_matches_orm_metadata(tmp_path):
    """Migratsiyalar bilan qurilgan sxema ORM dan farq qilmasin (autogenerate diff bo'sh)."""
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), "head")
    with eng.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff


def test_downgrade_to_base_and_back(tmp_path):
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        command.downgrade(_cfg(conn), "base")
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
        command.upgrade(_cfg(conn), "head")
        assert "sensors" in inspect(conn).get_table_names()


def test_migrate_legacy_db_without_alembic_version(tmp_path, monkeypatch):
    """create_all davridagi DB (alembic_version yo'q) → stamp baseline → head."""
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), gdb.BASELINE_REV)
        conn.exec_driver_sql("DROP TABLE alembic_version")
        # Baseline dan ham eski holatni taqlid qilamiz: bitta ustun va bitta jadval yo'q
        conn.exec_driver_sql("ALTER TABLE sensors DROP COLUMN priority")
        conn.exec_driver_sql("DROP TABLE journal_entries")
        conn.execute(
            text(
                "INSERT INTO users (id, username, full_name, email, password_hash, is_admin, "
                "is_active, created_at) VALUES (1, 'a', 'A', '', 'x', 1, 1, '2026-01-01 00:00:00')"
            )
        )
    monkeypatch.setattr(gdb, "engine", eng)
    gdb.migrate()
    with eng.connect() as conn:
        assert _current(conn) in _heads()
        cols = {c["name"] for c in inspect(conn).get_columns("sensors")}
        assert {"priority", "last_quality"} <= cols
        assert "journal_entries" in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(ctx, Base.metadata) == []


def test_assert_at_head_rejects_stale_schema(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), gdb.BASELINE_REV)
    monkeypatch.setattr(gdb, "engine", eng)
    if _heads() == {gdb.BASELINE_REV}:
        gdb.assert_at_head()  # baseline = head bo'lsa xato yo'q
    else:
        import pytest

        with pytest.raises(RuntimeError):
            gdb.assert_at_head()
