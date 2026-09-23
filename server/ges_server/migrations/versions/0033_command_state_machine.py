"""buyruq holat mashinasi (SCADA-03): `unknown` holati, manzil snapshoti, override belgisi, nonce; TTL 60 s

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE commandstatus ADD VALUE IF NOT EXISTS 'unknown'")
    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.add_column(sa.Column('protocol', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('address', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('interlock_override', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('nonce', sa.String(length=32), nullable=True))
    # Mavjud ochiq buyruqlar: manzil snapshoti sensordan
    op.execute(
        "UPDATE commands SET protocol = (SELECT protocol FROM sensors WHERE sensors.id = commands.sensor_id), "
        "address = (SELECT address FROM sensors WHERE sensors.id = commands.sensor_id) "
        "WHERE status IN ('pending', 'pending_approval', 'sent')"
    )
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.alter_column('command_ttl_s', existing_type=sa.Integer(), server_default='60', existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.alter_column('command_ttl_s', existing_type=sa.Integer(), server_default='300', existing_nullable=False)
    op.execute("UPDATE commands SET status = 'failed' WHERE status = 'unknown'")
    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.drop_column('nonce')
        batch_op.drop_column('interlock_override')
        batch_op.drop_column('address')
        batch_op.drop_column('protocol')
