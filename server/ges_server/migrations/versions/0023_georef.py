"""georef (G3): loyiha CRS — EPSG, lokal kelib chiqish nuqtasining global joyi, burilish

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('projects') as b:
        b.add_column(sa.Column('epsg_code', sa.Integer(), nullable=True))
        b.add_column(sa.Column('origin_e', sa.Float(), nullable=True))
        b.add_column(sa.Column('origin_n', sa.Float(), nullable=True))
        b.add_column(sa.Column('origin_h', sa.Float(), nullable=True))
        b.add_column(sa.Column('crs_rotation_deg', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('projects') as b:
        b.drop_column('crs_rotation_deg')
        b.drop_column('origin_h')
        b.drop_column('origin_n')
        b.drop_column('origin_e')
        b.drop_column('epsg_code')
