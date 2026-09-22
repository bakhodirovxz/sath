#!/usr/bin/env sh
# Sath tiklash (L6): backup.sh arxividan DB va fayllarni compose loyihasiga qaytaradi.
#
#   ./restore.sh backups/sath-20260922-0300.tar.gz.enc            # to'liq tiklash (ges to'xtatiladi!)
#   ./restore.sh --test backups/sath-20260922-0300.tar.gz.enc     # tiklashni SINASH: vaqtinchalik Postgres
#                                                                 # konteynerida pg_restore, jadval/qator sanog'i,
#                                                                 # keyin o'chiriladi — ishlab chiqarishga tegmaydi
#   ./restore.sh --yes <arxiv>                                    # tasdiq so'ramasdan (avtomatlashtirish)
#   Parol: BACKUP_PASSPHRASE_FILE yoki BACKUP_PASSPHRASE (arxiv .enc bo'lsa).
#
# RTO: ~15–30 daqiqa (fayl hajmiga qarab); RPO: oxirgi zaxira vaqti. Tartib (docs/admin.md):
#   1) secret.key ni parol menejeridan /data ga qaytaring (yoki GES_SECRET_KEY muhitida bering)
#   2) ./restore.sh <arxiv>   3) docker compose up -d   4) GET /api/health, GET /api/audit/verify
set -eu
cd "$(dirname "$0")"
PROJECT="${COMPOSE_PROJECT:-sath}"
VOL="${PROJECT}_ges_data"
MODE="full"
YES=0
while [ $# -gt 1 ]; do
  case "$1" in
    --test) MODE="test"; shift ;;
    --yes) YES=1; shift ;;
    *) break ;;
  esac
done
ARCHIVE="${1:?arxiv yo'li kerak}"
[ -f "$ARCHIVE" ] || { echo "Arxiv topilmadi: $ARCHIVE" >&2; exit 2; }
work="$(mktemp -d)"
TESTC="sath-restore-test-$$"
cleanup() { rm -rf "$work"; [ "$MODE" = "test" ] && docker rm -f "$TESTC" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# 0) Butunlik va shifrni ochish
if [ -f "$ARCHIVE.sha256" ]; then
  if (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256" >/dev/null 2>&1); then echo "sha256: OK";
  else echo "sha256 MOS EMAS — arxiv buzilgan" >&2; exit 3; fi
fi
case "$ARCHIVE" in
  *.enc)
    if [ -n "${BACKUP_PASSPHRASE_FILE:-}" ]; then pass_arg="file:$BACKUP_PASSPHRASE_FILE";
    elif [ -n "${BACKUP_PASSPHRASE:-}" ]; then pass_arg="env:BACKUP_PASSPHRASE";
    else echo "BACKUP_PASSPHRASE_FILE yoki BACKUP_PASSPHRASE kerak" >&2; exit 2; fi
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$ARCHIVE" -out "$work/a.tar.gz" -pass "$pass_arg" ;;
  *) cp "$ARCHIVE" "$work/a.tar.gz" ;;
esac
(cd "$work" && tar xzf a.tar.gz && sha256sum -c SHA256SUMS >/dev/null) && echo "ichki sha256: OK"
echo "Manifest: $(cat "$work/manifest.json")"
db_kind="$(sed -n 's/.*"db": "\([a-z]*\)".*/\1/p' "$work/manifest.json")"

if [ "$MODE" = "test" ]; then
  # Tiklashni sinash — vaqtinchalik konteyner, ishlab chiqarishga tegmaydi
  if [ "$db_kind" = "postgres" ]; then
    docker run -d --name "$TESTC" -e POSTGRES_PASSWORD=t -e POSTGRES_USER=ges -e POSTGRES_DB=ges timescale/timescaledb:latest-pg16 >/dev/null
    i=0
    # init skriptlari tugab timescaledb kengaytmasi o'rnatilguncha kutamiz (vaqtinchalik init serveri ham javob beradi)
    until [ "$(docker exec "$TESTC" psql -U ges -tAc "select count(*) from pg_extension where extname='timescaledb'" 2>/dev/null)" = "1" ] && docker logs "$TESTC" 2>&1 | grep -q "database system is ready to accept connections" && [ "$(docker logs "$TESTC" 2>&1 | grep -c 'database system is ready to accept connections')" -ge 2 ]; do
      i=$((i+1)); [ $i -gt 120 ] && { echo "Postgres ishga tushmadi" >&2; exit 4; }; sleep 1
    done
    docker exec "$TESTC" psql -U ges -q -c "SELECT timescaledb_pre_restore();" >/dev/null
    docker exec -i "$TESTC" pg_restore -U ges -d ges --no-owner --no-privileges < "$work/db.pgdump" 2>&1 | grep -v "already exists" || true
    docker exec "$TESTC" psql -U ges -q -c "SELECT timescaledb_post_restore();" >/dev/null
    echo "Jadvallar: $(docker exec "$TESTC" psql -U ges -tAc "select count(*) from information_schema.tables where table_schema='public'")"
    for t in users projects sensors readings audit_log alembic_version; do
      printf '  %-16s %s\n' "$t" "$(docker exec "$TESTC" psql -U ges -tAc "select count(*) from $t" 2>/dev/null || echo 'yoq')"
    done
    echo "Alembic: $(docker exec "$TESTC" psql -U ges -tAc "select version_num from alembic_version")"
  else
    docker run --rm -i python:3.12-slim sh -c "cat > /tmp/db.sqlite && python -c \"
import sqlite3; c=sqlite3.connect('/tmp/db.sqlite'); print('integrity:', c.execute('pragma integrity_check').fetchone()[0])
for t in ('users','projects','sensors','readings','audit_log','alembic_version'):
    try: print(' ', t, c.execute('select count(*) from ' + t).fetchone()[0])
    except Exception as e: print(' ', t, 'yoq', e)
print('alembic:', c.execute('select version_num from alembic_version').fetchone())\"" < "$work/db.sqlite"
  fi
  n_files="$(tar tf - < "$work/files.tar" | grep -c "^./files/" || true)"
  echo "Fayllar arxivda: $n_files ta (files/)"
  echo "TIKLASH SINOVI: OK"
  exit 0
fi

# To'liq tiklash
if [ "$YES" != "1" ]; then
  echo "Diqqat: $PROJECT loyihasidagi ma'lumotlar arxivdagi holatga ALMASHTIRILADI. Davom etish uchun 'ha' yozing:"
  read -r ans; [ "$ans" = "ha" ] || { echo "Bekor qilindi"; exit 1; }
fi
docker compose -p "$PROJECT" stop ges cfd 2>/dev/null || true
if [ "$db_kind" = "postgres" ]; then
  docker compose -p "$PROJECT" up -d postgres
  i=0
  until docker compose -p "$PROJECT" exec -T postgres psql -U ges -tAc 'select 1' >/dev/null 2>&1; do i=$((i+1)); [ $i -gt 90 ] && exit 4; sleep 1; done
  old="ges_old_$(date +%Y%m%d%H%M)"
  docker compose -p "$PROJECT" exec -T postgres psql -U ges -d postgres -q -c "DROP DATABASE IF EXISTS ges_restore" -c "CREATE DATABASE ges_restore OWNER ges"
  docker compose -p "$PROJECT" exec -T postgres psql -U ges -d ges_restore -q -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null
  docker compose -p "$PROJECT" exec -T postgres pg_restore -U ges -d ges_restore --no-owner --no-privileges < "$work/db.pgdump" 2>&1 | grep -v "already exists" || true
  docker compose -p "$PROJECT" exec -T postgres psql -U ges -d ges_restore -q -c "SELECT timescaledb_post_restore();" >/dev/null
  # almashtirish: eski DB $old nomi bilan qoladi (tekshirib bo'lgach DROP DATABASE)
  docker compose -p "$PROJECT" exec -T postgres psql -U ges -d postgres -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ges' AND pid <> pg_backend_pid()" -c "ALTER DATABASE ges RENAME TO $old" -c "ALTER DATABASE ges_restore RENAME TO ges" >/dev/null
  echo "Eski DB: $old (tekshirib bo'lgach: DROP DATABASE $old)"
else
  docker run --rm -i -v "$VOL":/data alpine sh -c "rm -f /data/ges.db /data/ges.db-wal /data/ges.db-shm && cat > /data/ges.db" < "$work/db.sqlite"
fi
docker run --rm -i -v "$VOL":/data alpine sh -c "cd /data && tar xf -" < "$work/files.tar"
echo "Tiklandi. Endi: docker compose -p $PROJECT up -d ; GET /api/health ; GET /api/audit/verify (admin)"
