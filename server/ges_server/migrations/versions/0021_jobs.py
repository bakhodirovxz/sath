"""jobs (L3): ish navbati — sim_jobs ijara/urinish/idempotentlik ustunlari, jobs jadvali

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('sim_jobs') as b:
        b.add_column(sa.Column('worker_id', sa.String(length=128), nullable=True))
        b.add_column(sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='2'))
        b.add_column(sa.Column('idempotency_key', sa.String(length=128), nullable=True))
        b.create_unique_constraint('uq_sim_jobs_idem', ['author_id', 'idempotency_key'])
    # Restart paytida qolib ketgan ishlar: ijarasiz `running` — yarashtirish startda `queued`/`failed` qiladi
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='jobstatus', length=16), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index(op.f('ix_jobs_kind'), 'jobs', ['kind'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_kind'), table_name='jobs')
    op.drop_table('jobs')
    with op.batch_alter_table('sim_jobs') as b:
        b.drop_constraint('uq_sim_jobs_idem', type_='unique')
        b.drop_column('idempotency_key')
        b.drop_column('max_attempts')
        b.drop_column('attempts')
        b.drop_column('started_at')
        b.drop_column('lease_until')
        b.drop_column('worker_id')
