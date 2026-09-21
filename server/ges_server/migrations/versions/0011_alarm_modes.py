"""alarm_modes (C2): shelving, out-of-service, suppression-by-design

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alarm_mode', sa.String(length=24), server_default='normal', nullable=False))
        batch_op.add_column(sa.Column('alarm_mode_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('alarm_mode_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('alarm_mode_reason', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('alarm_mode_since', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('suppress_condition', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('suppressed', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_foreign_key('fk_sensors_alarm_mode_by_users', 'users', ['alarm_mode_by'], ['id'])
    with op.batch_alter_table('alarm_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('suppressed', sa.String(length=24), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('alarm_events', schema=None) as batch_op:
        batch_op.drop_column('suppressed')
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sensors_alarm_mode_by_users', type_='foreignkey')
        for c in ('suppressed', 'suppress_condition', 'alarm_mode_since', 'alarm_mode_reason', 'alarm_mode_by', 'alarm_mode_until', 'alarm_mode'):
            batch_op.drop_column(c)
