"""calibration (I1): model kalibrovkasi yozuvlari va loyihaga qo'llangan parametrlar

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'calibration_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_to', sa.DateTime(timezone=True), nullable=False),
        sa.Column('n_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('targets', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ok'),
        sa.Column('params_before', sa.JSON(), nullable=False),
        sa.Column('params_after', sa.JSON(), nullable=False),
        sa.Column('rmse_before', sa.Float(), nullable=True),
        sa.Column('rmse_after', sa.Float(), nullable=True),
        sa.Column('bias_after', sa.Float(), nullable=True),
        sa.Column('improvement_pct', sa.Float(), nullable=True),
        sa.Column('diagnostics', sa.JSON(), nullable=False),
        sa.Column('applied', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calibration_project', 'calibration_runs', ['project_id'])
    with op.batch_alter_table('projects') as b:
        b.add_column(sa.Column('calibration', sa.JSON(), nullable=True))
    op.execute("UPDATE projects SET calibration = '{}' WHERE calibration IS NULL")
    with op.batch_alter_table('projects') as b:
        b.alter_column('calibration', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('projects') as b:
        b.drop_column('calibration')
    op.drop_index('ix_calibration_project', table_name='calibration_runs')
    op.drop_table('calibration_runs')
