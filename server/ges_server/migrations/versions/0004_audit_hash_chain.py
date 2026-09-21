"""audit_hash_chain

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21

audit_log ga prev_hash/row_hash; mavjud qatorlar id tartibida zanjirga ulanadi.
Hash funksiyasi bu yerda muzlatilgan (ges_server.audit keyin o'zgarsa ham migratsiya barqaror).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def _canon_ts(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _row_hash(r, prev: str) -> str:
    payload = {
        "created_at": _canon_ts(r.created_at),
        "user_id": r.user_id,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "project_id": r.project_id,
        "detail": json.loads(json.dumps(r.detail or {}, default=str)),
        "prev_hash": prev,
    }
    s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prev_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('row_hash', sa.String(length=64), nullable=True))

    tbl = sa.table(
        "audit_log",
        sa.column("id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("action", sa.String),
        sa.column("target_type", sa.String),
        sa.column("target_id", sa.Integer),
        sa.column("project_id", sa.Integer),
        sa.column("detail", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("prev_hash", sa.String),
        sa.column("row_hash", sa.String),
    )
    conn = op.get_bind()
    prev = ""
    for r in conn.execute(sa.select(tbl).order_by(tbl.c.id)).all():
        h = _row_hash(r, prev)
        conn.execute(tbl.update().where(tbl.c.id == r.id).values(prev_hash=prev, row_hash=h))
        prev = h


def downgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_column('row_hash')
        batch_op.drop_column('prev_hash')
