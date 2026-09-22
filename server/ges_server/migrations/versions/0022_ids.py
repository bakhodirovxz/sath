"""ids (G2): versiyada IDS tekshiruv natijasi, loyihada IDS majburiyligi

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('versions') as b:
        b.add_column(sa.Column('ids_status', sa.String(length=8), nullable=True))
        b.add_column(sa.Column('ids_result', sa.JSON(), nullable=True))
    with op.batch_alter_table('projects') as b:
        b.add_column(sa.Column('ids_required', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('projects') as b:
        b.drop_column('ids_required')
    with op.batch_alter_table('versions') as b:
        b.drop_column('ids_result')
        b.drop_column('ids_status')
