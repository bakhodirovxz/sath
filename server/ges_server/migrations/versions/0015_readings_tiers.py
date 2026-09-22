"""readings_tiers (D2): 1m/10m agregat qatlamlari, arxiv siqishi (deadband)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'readings_agg',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sensor_id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(length=4), nullable=False),
        sa.Column('bucket', sa.DateTime(timezone=True), nullable=False),
        sa.Column('n', sa.Integer(), nullable=False),
        sa.Column('avg', sa.Float(), nullable=False),
        sa.Column('min', sa.Float(), nullable=False),
        sa.Column('max', sa.Float(), nullable=False),
        sa.Column('pct_good', sa.Float(), server_default='1', nullable=False),
        sa.Column('n_bad', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sensor_id', 'tier', 'bucket'),
    )
    with op.batch_alter_table('readings_agg', schema=None) as batch_op:
        batch_op.create_index('ix_readings_agg_tier_bucket', ['tier', 'bucket'], unique=False)
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archive_deadband', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('archive_max_interval_s', sa.Integer(), server_default='3600', nullable=False))
        batch_op.add_column(sa.Column('last_archived_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('last_archived_ts', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        for c in ('last_archived_ts', 'last_archived_value', 'archive_max_interval_s', 'archive_deadband'):
            batch_op.drop_column(c)
    with op.batch_alter_table('readings_agg', schema=None) as batch_op:
        batch_op.drop_index('ix_readings_agg_tier_bucket')
    op.drop_table('readings_agg')
