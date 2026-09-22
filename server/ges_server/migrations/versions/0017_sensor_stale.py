"""sensor_stale (F4): aloqa holati alarm holatidan ajratildi

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stale', sa.Boolean(), server_default='1', nullable=False))
    # Eski holat: alarm='stale' → stale=1, jarayon holati ok; boshqalar — aloqa bor
    op.execute("UPDATE sensors SET stale = 0 WHERE alarm <> 'stale'")
    op.execute("UPDATE sensors SET alarm = 'ok' WHERE alarm = 'stale'")


def downgrade() -> None:
    op.execute("UPDATE sensors SET alarm = 'stale' WHERE stale = 1")
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_column('stale')
