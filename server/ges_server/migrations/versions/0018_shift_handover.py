"""shift_handover (F9): smena topshirish varaqasi va imzolar

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'shift_handovers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('since', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('handed_by', sa.Integer(), nullable=False),
        sa.Column('handed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_by', sa.Integer(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('receive_notes', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['handed_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['received_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('shift_handovers', schema=None) as batch_op:
        batch_op.create_index('ix_shift_project_id', ['project_id', 'id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('shift_handovers', schema=None) as batch_op:
        batch_op.drop_index('ix_shift_project_id')
    op.drop_table('shift_handovers')
