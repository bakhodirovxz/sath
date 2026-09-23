"""shift_supervisor roli (SCADA-01): Role enum kengaytmasi

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'shift_supervisor'")
    elif bind.dialect.name == "sqlite":
        # Enum SQLite da VARCHAR(max_len): 'shift_supervisor' (16) sig'ishi uchun
        with op.batch_alter_table('project_members', schema=None) as batch_op:
            batch_op.alter_column(
                'role', existing_type=sa.VARCHAR(length=8), type_=sa.VARCHAR(length=16), existing_nullable=False
            )


def downgrade() -> None:
    bind = op.get_bind()
    # shift_supervisor a'zolar dispetcherga tushiriladi (PG enum qiymati o'chirilmaydi)
    op.execute("UPDATE project_members SET role = 'operator' WHERE role = 'shift_supervisor'")
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table('project_members', schema=None) as batch_op:
            batch_op.alter_column(
                'role', existing_type=sa.VARCHAR(length=16), type_=sa.VARCHAR(length=8), existing_nullable=False
            )
