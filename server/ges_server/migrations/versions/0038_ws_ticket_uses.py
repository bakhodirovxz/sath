"""ws_ticket_uses (AUTH-02): bir martalik WebSocket chiptalari — iste'mol qilingan jti (bir necha API jarayoni)

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ws_ticket_uses',
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('jti'),
    )
    with op.batch_alter_table('ws_ticket_uses') as b:
        b.create_index(b.f('ix_ws_ticket_uses_expires_at'), ['expires_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('ws_ticket_uses') as b:
        b.drop_index(b.f('ix_ws_ticket_uses_expires_at'))
    op.drop_table('ws_ticket_uses')
