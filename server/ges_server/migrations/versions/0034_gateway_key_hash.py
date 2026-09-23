"""gateway kalitlari xesh bilan (SCADA-04): ingest/command kalit o'rniga SHA-256 xesh + prefiks, buyruq imzo kaliti

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-23

"""
from __future__ import annotations

import hashlib
import hmac

import sqlalchemy as sa
from alembic import op

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None

SIGN_CONTEXT = b"sath-command-sign-v1"  # ges_server.monitoring.keys.SIGN_CONTEXT bilan bir xil


def _h(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ingest_key_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('ingest_key_prefix', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('command_key_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('command_key_prefix', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('command_sign_key', sa.String(length=64), nullable=True))
    # Mavjud ochiq kalitlar xeshlanadi — gateway lar o'sha kalit bilan ishlashda davom etadi
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, ingest_key, command_key FROM projects")).all()
    for pid, ik, ck in rows:
        vals = {"id": pid, "ih": None, "ip": None, "ch": None, "cp": None, "cs": None}
        if ik:
            vals["ih"], vals["ip"] = _h(ik), ik[:6]
        if ck:
            vals["ch"], vals["cp"] = _h(ck), ck[:6]
            vals["cs"] = hmac.new(ck.encode("utf-8"), SIGN_CONTEXT, hashlib.sha256).hexdigest()
        conn.execute(
            sa.text(
                "UPDATE projects SET ingest_key_hash = :ih, ingest_key_prefix = :ip, command_key_hash = :ch, "
                "command_key_prefix = :cp, command_sign_key = :cs WHERE id = :id"
            ),
            vals,
        )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('command_key')
        batch_op.drop_column('ingest_key')


def downgrade() -> None:
    # Ochiq kalitni xeshdan tiklab bo'lmaydi — downgrade dan keyin kalitlarni almashtirish kerak
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ingest_key', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('command_key', sa.String(length=64), nullable=True))
        batch_op.drop_column('command_sign_key')
        batch_op.drop_column('command_key_prefix')
        batch_op.drop_column('command_key_hash')
        batch_op.drop_column('ingest_key_prefix')
        batch_op.drop_column('ingest_key_hash')
