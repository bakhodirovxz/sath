"""kks (H1): aktiv ierarxiyasi (parent_id), KKS/RDS-PP kodi, taksonomiya darajasi, sensor KKS kodi

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('assets') as b:
        b.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('kks_code', sa.String(length=32), nullable=True))
        b.add_column(sa.Column('taxonomy_level', sa.String(length=16), nullable=True))
        b.add_column(sa.Column('function_location', sa.String(length=128), nullable=False, server_default=''))
        b.create_foreign_key('fk_assets_parent', 'assets', ['parent_id'], ['id'], ondelete='SET NULL')
        b.create_unique_constraint('uq_assets_kks', ['project_id', 'kks_code'])
    # Backfill: mavjud aktivlar — uskuna darajasi (agregat/transformator), kodsiz (CSV import bilan to'ldiriladi)
    op.execute("UPDATE assets SET taxonomy_level = 'equipment' WHERE taxonomy_level IS NULL")
    with op.batch_alter_table('sensors') as b:
        b.add_column(sa.Column('kks_code', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('sensors') as b:
        b.drop_column('kks_code')
    with op.batch_alter_table('assets') as b:
        b.drop_constraint('uq_assets_kks', type_='unique')
        b.drop_constraint('fk_assets_parent', type_='foreignkey')
        b.drop_column('function_location')
        b.drop_column('taxonomy_level')
        b.drop_column('kks_code')
        b.drop_column('parent_id')
