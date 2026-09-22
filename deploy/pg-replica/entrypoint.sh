#!/usr/bin/env sh
# Postgres oqimli replika (L8): bo'sh data papka → primary dan pg_basebackup (standby.signal bilan), keyin
# odatdagi entrypoint. Primary tomonida: CREATE ROLE repl REPLICATION LOGIN PASSWORD '...'; pg_hba: host
# replication repl 0.0.0.0/0 scram-sha-256 (compose tarmog'i); wal_level=replica (default), max_wal_senders>=3.
set -eu
PGDATA="${PGDATA:-/var/lib/postgresql/data}"
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "replika: $PRIMARY_HOST dan pg_basebackup..."
  until pg_isready -h "$PRIMARY_HOST" -U "$REPL_USER" >/dev/null 2>&1; do sleep 2; done
  PGPASSWORD="$REPL_PASSWORD" pg_basebackup -h "$PRIMARY_HOST" -U "$REPL_USER" -D "$PGDATA" -R -X stream -C -S "replica_$(hostname | tr -c 'a-z0-9' '_')" -P
  chown -R postgres:postgres "$PGDATA"; chmod 0700 "$PGDATA"
fi
exec docker-entrypoint.sh postgres
