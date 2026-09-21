"""alarm_rationalization (C3): ISA-18.2 ratsionalizatsiya maydonlari

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cause', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('consequence', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('corrective_action', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('response_time_s', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('priority_basis', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('rationalized_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rationalized_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_sensors_rationalized_by_users', 'users', ['rationalized_by'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sensors_rationalized_by_users', type_='foreignkey')
        for c in ('rationalized_at', 'rationalized_by', 'priority_basis', 'response_time_s', 'corrective_action', 'consequence', 'cause'):
            batch_op.drop_column(c)
