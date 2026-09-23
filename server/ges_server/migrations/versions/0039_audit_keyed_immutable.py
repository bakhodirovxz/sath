"""audit_keyed_immutable (AUTH-05): audit_log.hash_alg (v1 sha256 / v2 HMAC); Postgres da UPDATE/DELETE/TRUNCATE
trigger bilan taqiqlanadi (SQLite da trigger yo'q — fayl darajasida himoya)

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None

_FN = """
CREATE OR REPLACE FUNCTION sath_audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log faqat qo''shiladi: % taqiqlangan (AUTH-05)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql
"""


def create_pg_trigger(conn) -> None:
    """Postgres: audit_log qatorlarini o'zgartirish/o'chirish va TRUNCATE ni taqiqlash (test ham chaqiradi)."""
    conn.execute(sa.text(_FN))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log"))
    conn.execute(
        sa.text(
            "CREATE TRIGGER audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION sath_audit_log_immutable()"
        )
    )
    conn.execute(
        sa.text(
            "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION sath_audit_log_immutable()"
        )
    )


def drop_pg_trigger(conn) -> None:
    conn.execute(sa.text("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS sath_audit_log_immutable()"))


def upgrade() -> None:
    with op.batch_alter_table('audit_log') as b:
        b.add_column(sa.Column('hash_alg', sa.String(length=8), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        create_pg_trigger(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        drop_pg_trigger(bind)
    with op.batch_alter_table('audit_log') as b:
        b.drop_column('hash_alg')
