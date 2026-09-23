#!/usr/bin/env sh
# Sath zaxirasi (L6): DB (Postgres pg_dump -Fc yoki SQLite .backup) + fayllar (IFC, content-addressed) →
# shifrlangan arxiv backups/sath-YYYYmmdd-HHMM.tar.gz.enc + manifest (sha256) + ixtiyoriy tashqi nusxa.
#
#   BACKUP_PASSPHRASE_FILE=/root/.sath-backup-pass ./backup.sh          # tavsiya: parol fayldan (0600)
#   BACKUP_PASSPHRASE=...  ./backup.sh                                   # yoki muhitdan
#   ./backup.sh --no-encrypt                                            # faqat sinov uchun (ochiq arxiv)
#
# Muhit: COMPOSE_PROJECT (default: sath — volume nomi ${COMPOSE_PROJECT}_ges_data), BACKUP_DIR (./backups),
#   BACKUP_KEEP_DAYS (30), BACKUP_COPY_DIR (masalan NAS mount — tashqi nusxa), BACKUP_RCLONE_REMOTE
#   (masalan "nas:sath-backups" — rclone copy), BACKUP_WITH_DERIVED=1 (fragments/QTO keshini ham; qayta
#   hisoblanadi, default yo'q). Jadval: deploy/backup.cron.example (kunlik) — RPO <= 24 soat; soatlik
#   qo'ysangiz RPO <= 1 soat. secret.key arxivga KIRMAYDI — uni alohida (parol menejeri) saqlang:
#   yo'qolsa ma'lumot saqlanadi, lekin sessiyalar tugaydi va audit eksport imzolari tekshirilmaydi.
#   Konteynerlardan ma'lumot stdout orqali olinadi (bind-mount emas) — masofaviy DOCKER_HOST da ham ishlaydi.
#   Jadval, tiklash va RTO/RPO: docs/admin.md → «Zaxira va tiklash».
set -eu
# CI-03: yordamchi obrazlar digest bilan qotirilgan
PY_IMAGE="python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"
ALPINE_IMAGE="alpine:3@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6"
cd "$(dirname "$0")"
PROJECT="${COMPOSE_PROJECT:-sath}"
VOL="${PROJECT}_ges_data"
OUT="${BACKUP_DIR:-$(pwd)/backups}"
KEEP="${BACKUP_KEEP_DAYS:-30}"
ENCRYPT=1
[ "${1:-}" = "--no-encrypt" ] && ENCRYPT=0
# SEC-02: hajm mavjudligi — yo'q bo'lsa `docker run -v` jimgina YANGI BO'SH hajm yaratib, bo'sh zaxira olardi
if ! docker volume inspect "$VOL" >/dev/null 2>&1; then
  echo "XATO: $VOL hajmi topilmadi. Compose loyiha nomi '$PROJECT' mi? (docker volume ls | grep ges_data;" >&2
  echo "      kerak bo'lsa COMPOSE_PROJECT=<nom> ./backup.sh)" >&2
  exit 3
fi
mkdir -p "$OUT"
stamp="$(date +%Y%m%d-%H%M)"
name="sath-$stamp"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# 1) DB
db_kind="sqlite"
if docker compose -p "$PROJECT" ps --status running --services 2>/dev/null | grep -qx postgres; then
  db_kind="postgres"
  echo "DB: Postgres pg_dump (custom format)..."
  docker compose -p "$PROJECT" exec -T postgres pg_dump -U ges -Fc ges > "$work/db.pgdump"
  [ -s "$work/db.pgdump" ] || { echo "XATO: pg_dump bo'sh natija berdi" >&2; exit 4; }
else
  echo "DB: SQLite (.backup API — izchil nusxa, WAL qo'shilgan; yozuvchilarni to'xtatmaydi)..."
  # ges.db yo'q/bo'sh bo'lsa sqlite3.connect yangi bo'sh baza yaratardi — avval tekshiriladi (exit 5);
  # nusxa PRAGMA integrity_check dan o'tmasa zaxira yozilmaydi (exit 6). Skript stdin dan, nusxa stdout ga.
  docker run --rm -i -v "$VOL":/data "$PY_IMAGE" python - > "$work/db.sqlite" <<'PY'
import os, shutil, sqlite3, sys
src = "/data/ges.db"
if not os.path.isfile(src) or os.path.getsize(src) == 0:
    sys.stderr.write("XATO: /data/ges.db topilmadi yoki bo'sh (Postgres rejimimi? postgres servisi ishlayaptimi?)\n")
    sys.exit(5)
s = sqlite3.connect(src)
d = sqlite3.connect("/tmp/db.sqlite")
s.backup(d)
ok = d.execute("pragma integrity_check").fetchone()[0]
d.close()
if ok != "ok":
    sys.stderr.write("XATO: integrity_check: %s\n" % ok)
    sys.exit(6)
with open("/tmp/db.sqlite", "rb") as fh:
    shutil.copyfileobj(fh, sys.stdout.buffer)
PY
  [ -s "$work/db.sqlite" ] || { echo "XATO: SQLite nusxasi bo'sh" >&2; exit 5; }
  echo "SQLite integrity_check: ok"
fi

# 2) Fayllar (content-addressed IFC/mesh; secret.key va vaqtinchalik keshlar chiqarib tashlanadi)
excl="--exclude=./secret.key --exclude=./ges.db --exclude=./ges.db-wal --exclude=./ges.db-shm --exclude=./initial-admin-password.txt --exclude=./sim --exclude=./cfd"
[ "${BACKUP_WITH_DERIVED:-0}" = "1" ] || excl="$excl --exclude=./derived"
echo "Fayllar: $VOL → files.tar..."
docker run --rm -v "$VOL":/data:ro "$ALPINE_IMAGE" sh -c "cd /data && tar cf - $excl ." > "$work/files.tar"

# 3) Manifest
alembic_head="$(docker compose -p "$PROJECT" exec -T ges alembic current 2>/dev/null | tail -1 || true)"
version="$(docker compose -p "$PROJECT" exec -T ges python -c 'import ges_server;print(ges_server.__version__)' 2>/dev/null || true)"
cat > "$work/manifest.json" <<EOF
{"name": "$name", "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "db": "$db_kind", "alembic": "${alembic_head:-?}",
 "version": "${version:-?}", "with_derived": ${BACKUP_WITH_DERIVED:-0}}
EOF
(cd "$work" && sha256sum db.* files.tar manifest.json > SHA256SUMS && tar czf "$name.tar.gz" manifest.json SHA256SUMS files.tar db.*)

# 4) Shifrlash (openssl enc aes-256-cbc + PBKDF2 — keng mavjud; age bo'lsa uni ham ishlatish mumkin)
if [ "$ENCRYPT" = "1" ]; then
  if [ -n "${BACKUP_PASSPHRASE_FILE:-}" ]; then pass_arg="file:$BACKUP_PASSPHRASE_FILE";
  elif [ -n "${BACKUP_PASSPHRASE:-}" ]; then pass_arg="env:BACKUP_PASSPHRASE";
  else echo "BACKUP_PASSPHRASE_FILE yoki BACKUP_PASSPHRASE kerak (yoki --no-encrypt, faqat sinov uchun)" >&2; exit 2; fi
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -in "$work/$name.tar.gz" -out "$OUT/$name.tar.gz.enc" -pass "$pass_arg"
  final="$OUT/$name.tar.gz.enc"
else
  cp "$work/$name.tar.gz" "$OUT/$name.tar.gz"
  final="$OUT/$name.tar.gz"
fi
(cd "$OUT" && sha256sum "$(basename "$final")" > "$(basename "$final").sha256")
echo "Zaxira: $final ($(du -h "$final" | cut -f1)), DB: $db_kind"

# 5) Tashqi nusxa
if [ -n "${BACKUP_COPY_DIR:-}" ]; then
  mkdir -p "$BACKUP_COPY_DIR" && cp "$final" "$final.sha256" "$BACKUP_COPY_DIR/" && echo "Nusxa: $BACKUP_COPY_DIR"
fi
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
  rclone copy "$final" "$BACKUP_RCLONE_REMOTE" && rclone copy "$final.sha256" "$BACKUP_RCLONE_REMOTE" && echo "Nusxa: $BACKUP_RCLONE_REMOTE"
fi

# 6) Eski nusxalarni tozalash (faqat mahalliy papka)
find "$OUT" -maxdepth 1 -name 'sath-*.tar.gz*' -mtime +"$KEEP" -print -delete | sed 's/^/O`chirildi: /' || true
