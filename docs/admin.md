# Sath — administrator qo'llanmasi

## O'rnatish (Docker, tavsiya)

Talab: Linux server (yoki Windows Server + Docker Desktop), 4+ CPU, 8+ GB RAM, 100+ GB disk (IFC fayllar).

```bash
git clone <repo> sath && cd sath/deploy
cp .env.example .env            # GES_ADMIN_PASSWORD, GES_PORT, GES_PUBLIC_URL ni to'ldiring
docker compose up -d --build    # server + web: http://<server>:8000
docker compose logs ges         # admin paroli bo'sh qoldirilgan bo'lsa — fayl yo'li shu yerda
```

Korporativ TLS proksi bo'lsa: `docker compose build --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" --build-arg NPM_STRICT_SSL=false`.

Ixtiyoriy profillar:
- **Postgres** (20+ foydalanuvchi): `.env` da `GES_DATABASE_URL=postgresql+psycopg://ges:ges@postgres:5432/ges`, `docker compose --profile postgres up -d`.
- **CFD** (OpenFOAM worker, ~1.5 GB obraz): `.env` da `GES_CFD_MODE=worker`, `docker compose --profile cfd up -d`. `CFD_CPUS` — worker uchun CPU.
- **MQTT**: `GES_MQTT_URL=mqtt://user:pass@broker:1883` — sensorlar `protocol=mqtt` bilan topic ga obuna bo'ladi (paho-mqtt kerak: `pip install "./server[mqtt]"` Docker obrazida qo'shilgan).
- **Email**: `GES_SMTP_URL=smtp://user:pass@mail.company.uz:587?from=ges@company.uz` — tasdiqlash hodisalari.

Docker siz (Windows/Linux, Python 3.10+):
```bash
pip install -e ./sim -e "./server[postgres,mqtt]"
cd web && npm ci && npm run build && cd ..
GES_DATA_DIR=/srv/ges-data ges-server        # http://0.0.0.0:8000 (web build avtomatik topiladi)
```

## HTTPS

`docker compose --profile https up -d` — Caddy teskari proksi (`deploy/Caddyfile`): `GES_DOMAIN` uchun
sertifikat. Ichki tarmoqda `tls internal` — Caddy o'z CA si; root sertifikatini ishchi kompyuterlarga
o'rnating (`docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt`). Internetga ochiq
domen bo'lsa `tls internal` qatorini olib tashlang (Let's Encrypt). `.env` da `GES_PUBLIC_URL=https://<domen>`.

## Fon hisoblar va historian

- **Yuklashdan keyin** har IFC uchun fonda: fragments (.frag, brauzer uchun tez format — Node kerak, Docker
  obrazda bor) va geometriya tahlili (hajm-miqdor, to'qnashuvlar). Katta modellarda CPU band bo'ladi;
  `GES_PRECOMPUTE_GEOMETRY=false` — faqat birinchi so'rovda hisoblanadi. Natijalar `data/derived/`.
- **Historian**: xom o'lchovlar `GES_READINGS_RETENTION_DAYS` (90) kun saqlanadi, soatlik agregat
  (`readings_hourly`) abadiy; uzoq davr grafiklari va hisobotlar agregatdan. Har `GES_MONITOR_INTERVAL_S`
  soniyada aloqasi uzilgan sensorlar `stale` ga o'tadi (alarm jurnaliga yoziladi).
- **Alarm jurnali** `alarm_events`, **bildirishnomalar** `notifications`, **audit** — Boshqaruv sahifasida
  (filtr: amal, foydalanuvchi; JSON eksport) yoki `GET /api/audit`.

## Tashqi konverterlar (DWG, FBX/3DS, .blend)

Web «Yangi versiya yuklash» DWG/FBX/3DS/.blend fayllarni serverdagi tashqi dasturlar orqali ochadi. Docker obrazda
`libredwg` (DWG) va `assimp` (FBX/3DS) bor; Blender — `docker build --build-arg WITH_BLENDER=1`. Windows/bare-metal
serverda o'zingiz qo'yasiz — server quyidagi joylardan avtomatik topadi (PATH, `GES_TOOLS_DIR`, `~/Tools`,
`C:\Tools`, `C:\Program Files\ODA`, `C:\Program Files\Blender Foundation`, `/opt/tools`, ichki papkalar ham):

| Format | Dastur | Qayerdan |
|---|---|---|
| DWG | LibreDWG `dwg2dxf` (GPL, bepul) | https://github.com/LibreDWG/libredwg/releases → `libredwg-*-win64.zip` ni `~/Tools/libredwg/` ga oching |
| DWG (muqobil) | ODA File Converter (`ODAFileConverter`) | https://www.opendesign.com/guestfiles/oda_file_converter — yangi DWG (2018+) uchun ishonchliroq |
| FBX, 3DS, LWO | Assimp `assimp` CLI | https://github.com/assimp/assimp/releases (yoki `apt install assimp-utils`) |
| .blend | Blender `blender` | https://www.blender.org/download/ |

Python kutubxonalari (Docker obrazida bor, bare-metal da `pip install`): `assimp-py` — FBX/3DS/LWO/X va 40+ mesh
format (CLI shart emas); `cadquery-ocp` (`pip install ".[cad]"`, ~100 MB) — STEP/IGES/BREP; `ezdxf` — DXF/DWG
chizmalar (o'lchamlar, bloklar, matn, shtrix); `opencv-python-headless` + `shapely` — rasmdan model.

`GET /api/import/formats` — qaysi konverter topilganini ko'rsatadi (`available: true/false`). Boshqa joyda bo'lsa
`.env` ga `GES_TOOLS_DIR=D:\konverterlar` yozing va serverni qayta ishga tushiring. LibreDWG ba'zi DWG larni
noto'liq o'qiydi (3DSOLID/ACIS jismlar umuman o'qilmaydi) — bunday chizmalarni AutoCAD da `MESHSMOOTH` → MESH
yoki `EXPORT` → FBX/OBJ qilib yuklang; 2D kontur (yopiq polyline/aylana) bo'lsa yuklash formasida «2D konturlarni
ko'tarish, m» ni kiriting.

## Rollar

Loyiha ichida: ko'ruvchi < **dispetcher (operator)** < muhandis < tasdiqlovchi. Dispetcher — SCADA
amallari (kvitlash, buyruqlar, jurnal, texnik xizmat qaydi), modelni o'zgartirmaydi. Buyruqlar faqat
`writable` sensorlarga; gateway konfiguratsiyasida shu teg bo'lishi kerak (`deploy/gateway/README.md`).
Kunlik hisobot: `GES_DAILY_REPORT_HOUR` (UTC soat, default 6; -1 — o'chirilgan) — muhandis/tasdiqlovchi/
dispetcherlarning emailiga.

## Ma'lumotlar

Hammasi `data/` (Docker: `ges_data` volume) da: `ges.db` (SQLite), `files/` (IFC, sha256 bo'yicha),
`sim/`, `cfd/`, `desktop/`, `secret.key`, `initial-admin-password.txt` (o'chiring).
Zaxira: `deploy/backup.sh` → `backups/ges-YYYYmmdd-HHMM.tar.gz`. Tiklash: volume ga tar ni ochish.
Yangi versiyaga o'tish: `git pull && docker compose up -d --build` — jadval ustunlari avtomatik qo'shiladi.

## Foydalanuvchilar va rollar

Web → **Boshqaruv**: foydalanuvchi yaratish (login, parol, email), faol/nofaol, admin.
Loyiha sahifasida: a'zo qo'shish, rol (Ko'ruvchi / Muhandis / Tasdiqlovchi). Admin hamma loyihada tasdiqlovchi.
Parolni foydalanuvchi o'zi o'zgartira oladi (API `/api/auth/change-password`); admin — «Parolni almashtirish».

## Desktop paketini tarqatish

Windows mashinada (o'rnatilgan FreeCAD 1.1.3, fork `../Sath-FreeCAD`, NSIS — `desktop/README.md`):
```bash
python desktop/build/build_portable.py     # desktop/dist/Sath-<ver>-Windows-x86_64-installer.exe (~600 MB) va .zip
for f in desktop/dist/Sath-0.1.0-Windows-x86_64-installer.exe desktop/dist/Sath-0.1.0-Windows-x86_64.zip; do
  curl -X POST -H "Authorization: Bearer <admin token>" -F file=@$f http://<server>:8000/api/desktop/upload
done
```
Webda «Loyihalar» sahifasida «Sath x.y.z o'rnatish ↓ / zip ↓» tugmalari chiqadi; desktop kirishda
`GET /api/desktop/latest` bilan tekshiradi (installer afzal). Versiya `desktop/GesWorkbench/package.xml` da —
oshirib, `python desktop/build/sync_fork.py` bilan fork ga o'tkazing. Yadro (FreeCAD) o'zgartirilganda
fork dagi GitHub Actions «Sath build» ishlatiladi — natija bir xil nomdagi fayllar.

## SCADA ulanishi

Monitoring → «Ulanish kaliti» (tasdiqlovchi). SCADA tomonidagi kompyuterda `deploy/gateway/ges_gateway.py`
(Modbus TCP / OPC UA / CSV) yoki har qanday skript `POST /api/projects/{id}/readings` ga
`X-Ingest-Key` bilan JSON `[{"key":"AGG1.P","value":24.3}]` yuboradi. Kalitni almashtirish — o'sha tugma.

## Xavfsizlik

- HTTPS: oldiga Caddy/nginx (reverse proxy) qo'ying; WebSocket (`/api/projects/*/live`) ni ham o'tkazing.
- `GES_SECRET_KEY` — o'zgartirilsa hamma sessiya tugaydi (avtomatik yaratilgani `data/secret.key`).
- Audit: `audit_log` jadvali (kim, nima, qachon) — barcha o'zgarishlar.
- Ingest kaliti faqat o'lchov yuboradi; boshqa hech narsaga ruxsat bermaydi.

## API

`http://<server>:8000/docs` — interaktiv OpenAPI hujjat (login → Authorize).
