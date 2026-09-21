"""command_sbo

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21 23:44:51.675057

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # CommandStatus ga yangi qiymatlar — enum turi kengaytiriladi
        op.execute("ALTER TYPE commandstatus ADD VALUE IF NOT EXISTS 'pending_approval'")
        op.execute("ALTER TYPE commandstatus ADD VALUE IF NOT EXISTS 'mismatch'")
    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('readback_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('readback_at', sa.DateTime(timezone=True), nullable=True))
        if bind.dialect.name == "sqlite":
            # Enum SQLite da VARCHAR(max_len): 'pending_approval' (16) sig'ishi uchun
            batch_op.alter_column(
                'status',
                existing_type=sa.VARCHAR(length=9),
                type_=sa.VARCHAR(length=16),
                existing_nullable=False,
            )
        batch_op.create_foreign_key('fk_commands_approved_by_users', 'users', ['approved_by'], ['id'])

    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('readback_tolerance', sa.Float(), server_default='0.01', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_column('readback_tolerance')

    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.drop_constraint('fk_commands_approved_by_users', type_='foreignkey')
        batch_op.drop_column('readback_at')
        batch_op.drop_column('readback_value')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
