"""readings_hypertable (D1): Postgres + TimescaleDB — readings ni hypertable ga aylantirish

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-22

Faqat PostgreSQL da va timescaledb kengaytmasi mavjud bo'lsa. Hypertable talabi: barcha unikal
indekslar bo'linish ustunlarini (ts, sensor_id) o'z ichiga olishi kerak — shuning uchun `id` bo'yicha PK
`(id, ts, sensor_id)` unikal indeksga almashtiriladi (ORM `id` ni identifikator sifatida ishlatishda davom etadi,
`id` serial qoladi). Bo'laklar: 7 kun; sensor_id bo'yicha 4 ta space partition.
"""
from __future__ import annotations

from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def _timescale_available(bind) -> bool:
    row = bind.exec_driver_sql("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'").first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _timescale_available(bind):
        import logging

        logging.getLogger("alembic").warning(
            "timescaledb kengaytmasi yo'q — readings oddiy jadval bo'lib qoladi (timescale/timescaledb obrazini ishlating)"
        )
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    already = bind.exec_driver_sql(
        "SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'readings'"
    ).first()
    if already:
        return
    op.execute("ALTER TABLE readings DROP CONSTRAINT IF EXISTS readings_pkey")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_readings_id_ts ON readings (id, ts, sensor_id)")
    op.execute(
        "SELECT create_hypertable('readings', 'ts', partitioning_column => 'sensor_id', number_partitions => 4, "
        "chunk_time_interval => INTERVAL '7 days', migrate_data => true)"
    )


def downgrade() -> None:
    # Hypertable ni oddiy jadvalga qaytarish ma'lumotni ko'chirishni talab qiladi — qo'lda (pg_dump/restore)
    pass
