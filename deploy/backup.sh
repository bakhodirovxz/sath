#!/usr/bin/env sh
# Ma'lumotlar zaxirasi: DB + IFC fayllar (docker volume) → backups/ges-YYYYmmdd-HHMM.tar.gz
set -e
cd "$(dirname "$0")"
mkdir -p backups
name="ges-$(date +%Y%m%d-%H%M).tar.gz"
docker run --rm -v sath_ges_data:/data -v "$(pwd)/backups":/backup alpine \
  tar czf "/backup/$name" -C /data .
echo "Zaxira: backups/$name"
