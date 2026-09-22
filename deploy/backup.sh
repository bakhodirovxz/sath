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
cd "$(dirname "$0")"
PROJECT="${COMPOSE_PROJECT:-sath}"
VOL="${PROJECT}_ges_data"
OUT="${BACKUP_DIR:-$(pwd)/backups}"
KEEP="${BACKUP_KEEP_DAYS:-30}"
ENCRYPT=1
[ "${1:-}" = "--no-encrypt" ] && ENCRYPT=0
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
else
  echo "DB: SQLite (.backup API — izchil nusxa, WAL qo'shilgan; yozuvchilarni to'xtatmaydi)..."
  docker run --rm -v "$VOL":/data python:3.12-slim \
    python -c "import sqlite3,sys,shutil; s=sqlite3.connect('/data/ges.db'); d=sqlite3.connect('/tmp/db.sqlite'); s.backup(d); d.close(); shutil.copyfileobj(open('/tmp/db.sqlite','rb'), sys.stdout.buffer)" > "$work/db.sqlite"
fi

# 2) Fayllar (content-addressed IFC/mesh; secret.key va vaqtinchalik keshlar chiqarib tashlanadi)
excl="--exclude=./secret.key --exclude=./ges.db --exclude=./ges.db-wal --exclude=./ges.db-shm --exclude=./initial-admin-password.txt --exclude=./sim --exclude=./cfd"
[ "${BACKUP_WITH_DERIVED:-0}" = "1" ] || excl="$excl --exclude=./derived"
echo "Fayllar: $VOL → files.tar..."
docker run --rm -v "$VOL":/data:ro alpine sh -c "cd /data && tar cf - $excl ." > "$work/files.tar"

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
