"""historian_dirty (SCADA-10): suv belgisidan oldingi davrga kech kelgan o'lchovlar oralig'i

Revision ID: 0041
Revises: 0031
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0041'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'historian_dirty',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(length=8), nullable=False),
        sa.Column('sensor_id', sa.Integer(), nullable=False),
        sa.Column('ts_min', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ts_max', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_historian_dirty_tier_sensor', 'historian_dirty', ['tier', 'sensor_id'])


def downgrade() -> None:
    op.drop_index('ix_historian_dirty_tier_sensor', table_name='historian_dirty')
    op.drop_table('historian_dirty')
