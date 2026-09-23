"""model_soft_delete (VCS-06): modelni yumshoq o'chirish — deleted_at / deleted_by

Revision ID: 0037
Revises: 0031
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0037'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('models') as b:
        b.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('deleted_by', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('models') as b:
        b.drop_column('deleted_by')
        b.drop_column('deleted_at')
