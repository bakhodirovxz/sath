"""login_lockout_mfa (L1): hisobni bloklash hisoblagichlari va TOTP MFA maydonlari

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('failed_logins', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('mfa_secret', sa.String(length=64), nullable=True))
        b.add_column(sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('mfa_last_counter', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.drop_column('mfa_last_counter')
        b.drop_column('mfa_enabled')
        b.drop_column('mfa_secret')
        b.drop_column('locked_until')
        b.drop_column('failed_logins')
