# Sath server + web (bitta konteyner). Kontekst: repo ildizi.
# 1-bosqich: web build
FROM node:22-alpine AS web
# Korporativ proksi (TLS intercept) bo'lsa: --build-arg NPM_STRICT_SSL=false
ARG NPM_STRICT_SSL=true
ENV NPM_CONFIG_STRICT_SSL=$NPM_STRICT_SSL NPM_CONFIG_FETCH_RETRIES=5
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN node scripts/copy-assets.mjs && npx vite build
# Server tomonida IFC → fragments konvertatsiya vositasi (faqat kerakli paketlar, ~90 MB)
RUN cd tools && npm ci --no-audit --no-fund --omit=dev

# 2-bosqich: Python server
FROM python:3.12-slim
# Korporativ proksi (TLS intercept) bo'lsa: --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"
ARG PIP_TRUSTED_HOST=""
ENV PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    GES_DATA_DIR=/data GES_WEB_DIST=/app/web/dist
# GES_DATABASE_URL compose dan keladi (Postgres+TimescaleDB default); obraz yolg'iz ishga tushsa — SQLite /data da
ENV GES_DATABASE_URL=sqlite:////data/ges.db
# Node — fragments konvertatsiya uchun (web/tools/ifc2frag.mjs); bo'lmasa brauzer IFC ni o'zi ochadi
# nodejs — fragments konvertatsiya; assimp-utils — FBX/3DS/LWO import; libredwg — DWG → DXF;
# WITH_BLENDER=1 — .blend fayllarni serverda ochish (obraz ~+400 MB)
ARG WITH_BLENDER=0
# WITH_DWG=1 (default) — LibreDWG (dwg2dxf) MAJBURIY: o'rnatilmasa build xato bilan to'xtaydi (CAD-10, jimgina
# yo'qolmasin). WITH_DWG=0 — ataylab DWG siz obraz. Holat: GET /api/health → "dwg": true/false.
# Litsenziya: LibreDWG — GPLv3 (alohida CLI dastur sifatida chaqiriladi); obrazni tashqariga tarqatsangiz
# manba taklifi kerak — deploy/README.md.
ARG WITH_DWG=1
# bubblewrap — ishonchsiz CAD/IFC parserlari uchun sandbox (L5; foydalanuvchi nom maydoni yopiq bo'lsa rlimit rejimi)
RUN apt-get update && apt-get install -y --no-install-recommends nodejs assimp-utils bubblewrap \
    && if [ "$WITH_DWG" = "1" ]; then \
         { apt-get install -y --no-install-recommends libredwg-utils || apt-get install -y --no-install-recommends libredwg-tools; } \
         && command -v dwg2dxf >/dev/null \
         || { echo "XATO: WITH_DWG=1, lekin LibreDWG (dwg2dxf) o'rnatilmadi — DWG siz obraz uchun WITH_DWG=0" >&2; exit 1; }; \
       fi \
    && rm -rf /var/lib/apt/lists/*
# WITH_BLENDER=1 — rasmiy Blender (CAD-08): Debian apt dagi blender eski (3.4) va 5.x .blend ni ochmaydi.
# Versiya va sha256 pin qilingan; sha256 mos kelmasa build to'xtaydi. Yangilash: BLENDER_VERSION va
# BLENDER_SHA256 ni birga o'zgartiring (https://download.blender.org/release/BlenderX.Y/blender-X.Y.Z.sha256,
# qator `blender-X.Y.Z-linux-x64.tar.xz`). Korporativ TLS proksi: --build-arg BLENDER_CURL_OPTS=-k
# (butunlikni sha256 kafolatlaydi). Ishonchsiz .blend `--factory-startup --disable-autoexec` bilan ochiladi
# (mesh_import.py).
ARG BLENDER_VERSION=5.2.2
ARG BLENDER_SHA256=84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168
ARG BLENDER_CURL_OPTS=""
RUN if [ "$WITH_BLENDER" = "1" ]; then \
      [ -n "$BLENDER_SHA256" ] || { echo "XATO: WITH_BLENDER=1 uchun BLENDER_SHA256 kerak" >&2; exit 1; }; \
      apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils \
        libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1 libegl1 \
      && curl -fsSL $BLENDER_CURL_OPTS -o /tmp/blender.tar.xz \
         "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
      && echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c - \
      && mkdir -p /opt/blender && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
      && ln -s /opt/blender/blender /usr/local/bin/blender \
      && blender -b --factory-startup --version | head -1 \
      && rm -f /tmp/blender.tar.xz && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /app
COPY sim/ ./sim/
COPY server/ ./server/
COPY docs/ids/ ./docs/ids/
RUN pip install --no-cache-dir ./sim "./server[postgres,mqtt,cad]"  # cad — STEP/IGES (OpenCASCADE)
COPY --from=web /web/dist ./web/dist
COPY --from=web /web/tools ./web/tools
# Root siz (L5): sath foydalanuvchisi; /data hajmi shu egaga (named volume birinchi yaratilganda egalikni oladi)
RUN useradd --system --uid 10001 --create-home --home-dir /home/sath sath \
    && mkdir -p /data/cfd && chown -R sath:sath /data /app
USER sath
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/ready')" || exit 1
CMD ["uvicorn", "ges_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
