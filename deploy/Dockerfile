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
    GES_DATA_DIR=/data GES_DATABASE_URL=sqlite:////data/ges.db GES_WEB_DIST=/app/web/dist
# Node — fragments konvertatsiya uchun (web/tools/ifc2frag.mjs); bo'lmasa brauzer IFC ni o'zi ochadi
# nodejs — fragments konvertatsiya; assimp-utils — FBX/3DS/LWO import; libredwg — DWG → DXF;
# WITH_BLENDER=1 — .blend fayllarni serverda ochish (obraz ~+400 MB)
ARG WITH_BLENDER=0
RUN apt-get update && apt-get install -y --no-install-recommends nodejs assimp-utils \
    && (apt-get install -y --no-install-recommends libredwg-utils || apt-get install -y --no-install-recommends libredwg-tools || true) \
    && (if [ "$WITH_BLENDER" = "1" ]; then apt-get install -y --no-install-recommends blender; fi) \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY sim/ ./sim/
COPY server/ ./server/
RUN pip install --no-cache-dir ./sim "./server[postgres,mqtt,cad]"  # cad — STEP/IGES (OpenCASCADE)
COPY --from=web /web/dist ./web/dist
COPY --from=web /web/tools ./web/tools
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
CMD ["uvicorn", "ges_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
