"""soe_events (D3): hodisalar ketma-ketligi (ms aniqlik)

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'soe_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('point', sa.String(length=64), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ts_ms', sa.BigInteger(), nullable=False),
        sa.Column('quality', sa.String(length=16), nullable=False),
        sa.Column('raw', sa.JSON(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'source', 'point', 'ts_ms', 'state', name='uq_soe_event'),
    )
    with op.batch_alter_table('soe_events', schema=None) as batch_op:
        batch_op.create_index('ix_soe_project_ts', ['project_id', 'ts_ms'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('soe_events', schema=None) as batch_op:
        batch_op.drop_index('ix_soe_project_ts')
    op.drop_table('soe_events')
