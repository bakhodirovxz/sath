"""iso19650 (G4): yaroqlilik/reviziya kodlari, nomlash qoidasi, loyiha hujjatlari (EIR/BEP)

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('versions') as b:
        b.add_column(sa.Column('suitability_code', sa.String(length=4), nullable=True))
        b.add_column(sa.Column('revision_code', sa.String(length=6), nullable=True))
    with op.batch_alter_table('projects') as b:
        b.add_column(sa.Column('naming_template', sa.String(length=128), nullable=False, server_default=''))
        b.add_column(sa.Column('naming_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Backfill: holatdan default kod (wip S0, shared S3, published A1) — tarixiy versiyalar ham ISO 19650 ko'rinishida
    op.execute("UPDATE versions SET suitability_code = 'S0' WHERE state = 'wip' AND suitability_code IS NULL")
    op.execute("UPDATE versions SET suitability_code = 'S3' WHERE state = 'shared' AND suitability_code IS NULL")
    op.execute("UPDATE versions SET suitability_code = 'A1' WHERE state = 'published' AND suitability_code IS NULL")
    op.create_table(
        'project_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=False),
        sa.Column('file_sha256', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('ext', sa.String(length=16), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_documents_project_id'), 'project_documents', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_project_documents_project_id'), table_name='project_documents')
    op.drop_table('project_documents')
    with op.batch_alter_table('projects') as b:
        b.drop_column('naming_required')
        b.drop_column('naming_template')
    with op.batch_alter_table('versions') as b:
        b.drop_column('revision_code')
        b.drop_column('suitability_code')
