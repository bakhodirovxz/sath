# Postgres oqimli replika va failover (L8)

`docker compose -f docker-compose.yml -f docker-compose.ha.yml --profile pg-replica up -d postgres-replica`

Primary da bir marta (compose `postgres` konteynerida):
```
docker compose exec postgres psql -U ges -c "CREATE ROLE repl WITH REPLICATION LOGIN PASSWORD 'repl';"
docker compose exec postgres sh -c "echo 'host replication repl 0.0.0.0/0 scram-sha-256' >> /var/lib/postgresql/data/pg_hba.conf"
docker compose exec postgres psql -U ges -c "ALTER SYSTEM SET max_wal_senders = 5; ALTER SYSTEM SET wal_keep_size = '1GB';"
docker compose restart postgres
```
`.env`: `PG_REPL_PASSWORD=...`. Replika birinchi startda `pg_basebackup` (slot bilan) qiladi va standby bo'lib
oqimni kuzatadi; kechikish: `SELECT now() - pg_last_xact_replay_timestamp();` (replikada).

**Failover (qo'lda, RTO ≈ 5 daqiqa):**
1. Primary qaytmasligiga ishonch hosil qiling (split-brain xavfi — eski primary ni to'xtating).
2. Replikada: `docker compose exec postgres-replica psql -U ges -c "SELECT pg_promote();"`
3. `.env` da `GES_DATABASE_URL=postgresql+psycopg://ges:...@postgres-replica:5432/ges`;
   `docker compose up -d ges ges-worker` (yoki `postgres` nomini replika konteyneriga ko'chiring).
4. `GET /api/ready` — `db: ok`, `schema: head`; keyin eski primary ni yangi replika sifatida qayta quring
   (data papkasini bo'shatib `pg-replica` profili bilan).
Avtomatik failover (Patroni/repmgr, VIP) — mustaqil loyiha; TimescaleDB bilan Patroni mos.
