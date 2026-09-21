"""alarm_levels (C1): LL/HH chegaralar, o'lik zona, kechikishlar, ROC; AlarmState kengaytmasi

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

NEW_STATES = ("lowlow", "highhigh", "roc", "deviation")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for v in NEW_STATES:
            op.execute(f"ALTER TYPE alarmstate ADD VALUE IF NOT EXISTS '{v}'")
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ll_alarm', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('hh_alarm', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('deadband', sa.Float(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('on_delay_s', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('off_delay_s', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('roc_limit_per_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('alarm_pending', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('alarm_pending_since', sa.DateTime(timezone=True), nullable=True))
        if bind.dialect.name == "sqlite":
            # Enum SQLite da VARCHAR(max_len): 'highhigh'/'deviation' sig'ishi uchun
            batch_op.alter_column('alarm', existing_type=sa.VARCHAR(length=5), type_=sa.VARCHAR(length=16), existing_nullable=False)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table('alarm_events', schema=None) as batch_op:
            batch_op.alter_column('state', existing_type=sa.VARCHAR(length=5), type_=sa.VARCHAR(length=16), existing_nullable=False)
    # Egizak og'ish sensorlari — alohida alarm turi (deviation)
    op.execute("UPDATE sensors SET kind='deviation' WHERE protocol='twin' AND key LIKE 'TWIN.%.DEV'")


def downgrade() -> None:
    op.execute("UPDATE sensors SET kind='value' WHERE kind='deviation'")
    op.execute("UPDATE sensors SET alarm='ok' WHERE alarm IN ('lowlow','highhigh','roc','deviation')")
    op.execute("UPDATE alarm_events SET state='high' WHERE state IN ('highhigh','roc','deviation')")
    op.execute("UPDATE alarm_events SET state='low' WHERE state='lowlow'")
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        for c in ('alarm_pending_since', 'alarm_pending', 'roc_limit_per_min', 'off_delay_s', 'on_delay_s', 'deadband', 'hh_alarm', 'll_alarm'):
            batch_op.drop_column(c)
