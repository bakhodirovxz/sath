"""validation (I3): egizak modelining validatsiya yozuvlari (mezon, verdikt, imzo, muddat)

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'validation_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=True),
        sa.Column('calibration_run_id', sa.Integer(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_to', sa.DateTime(timezone=True), nullable=False),
        sa.Column('criteria', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('checks', sa.JSON(), nullable=False),
        sa.Column('verdict', sa.String(length=8), nullable=False, server_default='fail'),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expiry_notified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['version_id'], ['versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['calibration_run_id'], ['calibration_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_validation_project', 'validation_records', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_validation_project', table_name='validation_records')
    op.drop_table('validation_records')
