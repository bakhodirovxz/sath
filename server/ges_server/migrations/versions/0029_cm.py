"""cm (H3): spektr yozuvlari va tashqi holat monitoringi natijalari (ISO 13374 DA / SD-HA-PA)

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'spectra',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('sensor_id', sa.Integer(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='spectrum'),
        sa.Column('unit', sa.String(length=16), nullable=False, server_default='mm/s'),
        sa.Column('rpm', sa.Float(), nullable=True),
        sa.Column('f_min', sa.Float(), nullable=False, server_default='0'),
        sa.Column('f_max', sa.Float(), nullable=False, server_default='0'),
        sa.Column('n_lines', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('values', sa.JSON(), nullable=False),
        sa.Column('freqs', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_spectra_asset_ts', 'spectra', ['asset_id', 'ts'])
    op.create_table(
        'cm_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('block', sa.String(length=4), nullable=False, server_default='HA'),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False, server_default='unknown'),
        sa.Column('health_score', sa.Float(), nullable=True),
        sa.Column('rul_days', sa.Float(), nullable=True),
        sa.Column('diagnosis', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('valid_hours', sa.Float(), nullable=False, server_default='24'),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cm_results_asset_ts', 'cm_results', ['asset_id', 'ts'])


def downgrade() -> None:
    op.drop_index('ix_cm_results_asset_ts', table_name='cm_results')
    op.drop_table('cm_results')
    op.drop_index('ix_spectra_asset_ts', table_name='spectra')
    op.drop_table('spectra')
