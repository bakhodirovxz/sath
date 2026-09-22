"""cmms (H2): profilaktik xizmat rejalari, mehnat yozuvi, qism bandlash, ISO 14224 kodlari, PTW/LOTO

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'maintenance_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('tasks', sa.JSON(), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=True),
        sa.Column('interval_hours', sa.Float(), nullable=True),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='medium'),
        sa.Column('lead_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('permit_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_hours', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_plans_project', 'maintenance_plans', ['project_id'])
    op.create_table(
        'labor_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('hours', sa.Float(), nullable=False),
        sa.Column('rate', sa.Float(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('work_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'part_reservations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_order_id', sa.Integer(), nullable=False),
        sa.Column('part_id', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('work_order_id', 'part_id', name='uq_part_reservation'),
    )
    with op.batch_alter_table('work_orders') as b:
        b.add_column(sa.Column('plan_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('tasks', sa.JSON(), nullable=True))
        b.add_column(sa.Column('failure_mode', sa.String(length=8), nullable=True))
        b.add_column(sa.Column('failure_cause', sa.String(length=8), nullable=True))
        b.add_column(sa.Column('detection_method', sa.String(length=8), nullable=True))
        b.add_column(sa.Column('labor_rate', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('labor_cost', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('parts_cost', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('extra_cost', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('permit_required', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('permit_status', sa.String(length=16), nullable=False, server_default='none'))
        b.add_column(sa.Column('permit_issued_by', sa.Integer(), nullable=True))
        b.add_column(sa.Column('permit_issued_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('permit_note', sa.Text(), nullable=False, server_default=''))
        b.add_column(sa.Column('loto_active', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('loto_points', sa.JSON(), nullable=True))
        b.add_column(sa.Column('loto_applied_by', sa.Integer(), nullable=True))
        b.add_column(sa.Column('loto_applied_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('loto_removed_at', sa.DateTime(timezone=True), nullable=True))
        b.create_foreign_key('fk_wo_plan', 'maintenance_plans', ['plan_id'], ['id'], ondelete='SET NULL')
        b.create_foreign_key('fk_wo_permit_by', 'users', ['permit_issued_by'], ['id'])
        b.create_foreign_key('fk_wo_loto_by', 'users', ['loto_applied_by'], ['id'])
    # Backfill: JSON ustunlari bo'sh ro'yxat; mavjud xarajat "qo'shimcha" deb hisoblanadi
    # (mehnat/qism taqsimoti tarixda yo'q — H2 dan keyingi yozuvlarda to'ldiriladi)
    op.execute("UPDATE work_orders SET tasks = '[]' WHERE tasks IS NULL")
    op.execute("UPDATE work_orders SET loto_points = '[]' WHERE loto_points IS NULL")
    op.execute("UPDATE work_orders SET extra_cost = cost WHERE cost IS NOT NULL AND cost <> 0")
    with op.batch_alter_table('work_orders') as b:  # backfill dan keyin NOT NULL (ORM bilan mos)
        b.alter_column('tasks', existing_type=sa.JSON(), nullable=False)
        b.alter_column('loto_points', existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table('part_movements') as b:
        b.add_column(sa.Column('kind', sa.String(length=16), nullable=False, server_default='move'))
        b.add_column(sa.Column('unit_cost', sa.Float(), nullable=True))
    op.execute("UPDATE part_movements SET kind = 'consume' WHERE qty < 0 AND work_order_id IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table('part_movements') as b:
        b.drop_column('unit_cost')
        b.drop_column('kind')
    with op.batch_alter_table('work_orders') as b:
        b.drop_constraint('fk_wo_loto_by', type_='foreignkey')
        b.drop_constraint('fk_wo_permit_by', type_='foreignkey')
        b.drop_constraint('fk_wo_plan', type_='foreignkey')
        for col in (
            'loto_removed_at', 'loto_applied_at', 'loto_applied_by', 'loto_points', 'loto_active',
            'permit_note', 'permit_issued_at', 'permit_issued_by', 'permit_status', 'permit_required',
            'extra_cost', 'parts_cost', 'labor_cost', 'labor_rate',
            'detection_method', 'failure_cause', 'failure_mode', 'tasks', 'plan_id',
        ):
            b.drop_column(col)
    op.drop_table('part_reservations')
    op.drop_table('labor_entries')
    op.drop_index('ix_plans_project', table_name='maintenance_plans')
    op.drop_table('maintenance_plans')
