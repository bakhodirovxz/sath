"""sessions (L2): token versiyasi, majburiy parol almashtirish, refresh sessiyalari jadvali

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('jti', sa.String(length=48), nullable=False),
        sa.Column('prev_jti', sa.String(length=48), nullable=True),
        sa.Column('client', sa.String(length=16), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('user_agent', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoke_reason', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jti'),
    )
    op.create_index(op.f('ix_user_sessions_prev_jti'), 'user_sessions', ['prev_jti'], unique=False)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_prev_jti'), table_name='user_sessions')
    op.drop_table('user_sessions')
    with op.batch_alter_table('users') as b:
        b.drop_column('password_changed_at')
        b.drop_column('must_change_password')
        b.drop_column('token_version')
