"""asset_documents (G6): aktiv hujjatlari (qo'llanma, pasport, sinov protokoli, ishga tushirish akti)

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'asset_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=False),
        sa.Column('file_sha256', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('ext', sa.String(length=16), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_asset_documents_asset_id'), 'asset_documents', ['asset_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_asset_documents_asset_id'), table_name='asset_documents')
    op.drop_table('asset_documents')
