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
- **Sxema migratsiyasi**: Alembic (`server/ges_server/migrations/`). Startda `GES_AUTO_MIGRATE=true` (default) bo'lsa `upgrade head` avtomatik; eski (Alembic siz) DB birinchi startda baseline ga belgilanadi va yangilanadi. Qo'lda: `cd server && alembic upgrade head`; `GES_AUTO_MIGRATE=false` da sxema eskirgan bo'lsa server ishga tushmaydi. Yangilashdan oldin zaxira oling.
- **Historian qatlamlari**: xom (`GES_READINGS_RETENTION_DAYS=90`) → 1 daqiqa (`GES_AGG_1M_RETENTION_DAYS=400`) → 10 daqiqa (`GES_AGG_10M_RETENTION_DAYS=1100`) → 1 soat (abadiy); alarm hodisasi atrofidagi ±1 soat xom o'chirilmaydi. Sensor `archive_deadband` — o'lik zonali siqish (`archive_max_interval_s` dan keyin majburiy yozuv).
- **Ma'lumotlar bazasi**: compose defaulti — Postgres 16 + TimescaleDB (`timescale/timescaledb:latest-pg16`, parol `POSTGRES_PASSWORD`); `readings` hypertable (7 kunlik bo'laklar, `sensor_id` bo'yicha 4 bo'lim), ingest `COPY` bilan partiyali. SQLite faqat ishlab chiqish/sinov uchun (`GES_DATABASE_URL=sqlite:////data/ges.db` — u holda postgres servisi kerak emas). Tashqi Postgres da timescaledb bo'lmasa `readings` oddiy jadval bo'lib qoladi (logda ogohlantirish).
- **CFD** (OpenFOAM worker, ~1.5 GB obraz): `.env` da `GES_CFD_MODE=worker`, `docker compose --profile cfd up -d`. `CFD_CPUS` — worker uchun CPU.
- **Alarm rejimi (ISA-18.2)**: shelving default/maksimal muddati `GES_ALARM_SHELVE_DEFAULT_H=8`, `GES_ALARM_SHELVE_MAX_H=24`; out-of-service — muhandis+, sabab majburiy; `suppress_condition` — interlock ifodasi (masalan `AGG1_RUN == 0`).
- **MQTT**: `GES_MQTT_URL=mqtts://broker:8883` + `GES_MQTT_CA_FILE` (majburiy), `GES_MQTT_USERNAME`/`GES_MQTT_PASSWORD` (yoki `_PASSWORD_FILE`; parol URL da emas), ixtiyoriy mTLS `GES_MQTT_CERT_FILE`+`_KEY_FILE` — sensorlar `protocol=mqtt` bilan topic ga obuna bo'ladi (paho-mqtt: `pip install "./server[mqtt]"`, Docker obrazida bor). TLS siz `mqtt://` faqat loopback ga; boshqa hostga faqat `GES_MQTT_ALLOW_INSECURE=true` bilan, aks holda server ishga tushmaydi. `GES_MQTT_TOPIC_ALLOW` (masalan `sath/{project_id}/#`) — sensor topigi ro'yxatga mos kelmasa obuna bo'lmaydi. Aloqa uzilsa obuna sensorlari `bad`, qayta ulanishda qayta obuna; xabarlar partiyalab (`GES_MQTT_BATCH_SIZE/_MS`) yoziladi.
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
Buyruq xavfsizlik konverti (sensor sozlamalarida): `min_setpoint`/`max_setpoint` (diapazon, tashqarida 400),
`max_rate_per_min` (oxirgi buyruq/o'lchovga nisbatan o'zgarish tezligi), `command_ttl_s` (gateway shu vaqt
ichida olmasa buyruq `expired` — eskirgan setpoint bajarilmaydi, default 300 s), `requires_dual_approval`
(ikkinchi operator `approve` qilmaguncha gateway ga bermaydi; muallif o'zini tasdiqlay olmaydi),
`readback_tolerance` (gateway yozgandan keyin o'qigan qiymat farqi, nisbiy; oshsa `mismatch`).
Buyruq ikki bosqichli (select-before-operate): `POST .../commands/select` → 30 s li token →
`POST .../commands/execute`; bir bosqichli `POST .../commands` va gateway uchun `GET .../commands/pending`
olib tashlangan (410) — gateway `POST .../commands/claim`. Gateway olgan (`sent`) buyruq `GES_COMMAND_SENT_TIMEOUT_S` (120 s) ichida javob
qaytarmasa watchdog uni `failed` qiladi va sensor bo'shaydi; `sent` ni qo'lda bekor qilib bo'lmaydi
(PLC ga yozilgan bo'lishi mumkin). Bitta sensorga bir vaqtda bitta ochiq buyruq — DB indeksi bilan.
Blokirovkalar (interlock): muhandis `POST /api/projects/{id}/interlocks` bilan boshqariladigan sensorga shart
ifodasi qo'yadi (`GET .../interlocks/variables` — o'zgaruvchilar: `AGG1.RUN` → `AGG1_RUN`, `value` — buyruq
qiymati; masalan `AGG1_RUN == 0 and RES_H > 890`). Shart bajarilmasa buyruq 409 (sabab bilan); `bad`/`stale`
sensor ifodada bo'lsa baholab bo'lmaydi — taqiq. Chetlab o'tish faqat tasdiqlovchi, sabab majburiy
(`select?override=true&override_reason=...`), audit `command.interlock_override` + dispetcherlarga alarm.
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

Monitoring → «Ulanish kalitlari» (tasdiqlovchi) — ikkita alohida kalit: **ingest** (`X-Ingest-Key`,
faqat `POST /readings`) va **command** (`X-Command-Key`, buyruq kanali: `/commands/claim`, `/ack`,
`/readback`). Ingest kaliti buyruq kanaliga kira olmaydi (403, audit `gateway.key_misuse`) va aksincha.
Har kalitda muddat (default 365 kun; `ttl_days=0` — muddatsiz) va oxirgi ishlatilgan vaqt; muddati
14/7/3/1 kun qolganda tasdiqlovchi va adminlarga bildirishnoma. SCADA tomonidagi kompyuterda
`deploy/gateway/ges_gateway.py` (Modbus TCP / OPC UA / CSV) yoki har qanday skript
`POST /api/projects/{id}/readings` ga `X-Ingest-Key` bilan JSON `[{"key":"AGG1.P","value":24.3}]` yuboradi.
Gateway da buyruq kanali default **o'chiq** (`commands: false`); yoqish uchun `commands: true` va
`command_key` (yoki `GES_GATEWAY_COMMAND_KEY`) shart. Kalitlarni faylda emas, muhit o'zgaruvchilarida
bering (`GES_GATEWAY_INGEST_KEY`, `GES_GATEWAY_COMMAND_KEY`, `GES_GATEWAY_SERVER`, `GES_GATEWAY_PROJECT_ID`).

Har o'lchovda ixtiyoriy `quality` (`good` — default, `uncertain`, `bad`, `substituted`, `manual`) va
`src_ts` (manbadagi vaqt tamg'asi — OPC UA SourceTimestamp yoki gateway o'qish vaqti) bo'lishi mumkin:
`{"key":"AGG1.P","value":24.3,"ts":"...","src_ts":"...","quality":"uncertain"}`. `bad` sifatli qiymat
tarixga yoziladi, lekin sensor holatini, alarmni, agregatni va egizakni o'zgartirmaydi — faqat `bad`
kelayotgan sensor `stale_after_s` dan keyin «aloqa yo'q» bo'ladi. Soatlik agregatda `pct_good` (good ulushi)
va `n_bad` saqlanadi.

Validatsiya: `value` chekli son bo'lishi shart (NaN/inf/matn → butun so'rov 422; gateway o'zi
tozalaydi — o'qish xatosi `quality=bad`, qiymat 0 bilan ketadi). `ts` yaroqsiz, kelajakda
(`GES_INGEST_FUTURE_S`, default 300 s) yoki `GES_INGEST_MAX_AGE_DAYS` (default 30) dan eski bo'lsa element
rad etiladi — javobdagi `rejected: [{key, reason}]` (CSV import tarixiy ma'lumot uchun yosh chegarasisiz).
Sensor `min_raw`/`max_raw` (fizik diapazon) tashqarisidagi qiymat `quality=bad` bilan saqlanadi.

## Xavfsizlik

- HTTPS: oldiga Caddy/nginx (reverse proxy) qo'ying; WebSocket (`/api/projects/*/live`) ni ham o'tkazing.
- `GES_SECRET_KEY` — o'zgartirilsa hamma sessiya tugaydi (avtomatik yaratilgani `data/secret.key`).
- Audit: `audit_log` jadvali (kim, nima, qachon) — barcha o'zgarishlar, shu jumladan kirish xatolari
  (`auth.login_failed`), parol o'zgarishi, WebSocket ulanishlari, ingest partiyalari (`readings.ingest`),
  eksportlar, ingest kalitini o'qish. Yozuvlar SHA-256 hash zanjiri bilan bog'langan:
  `GET /api/audit/verify` (admin) zanjirni tekshiradi va buzilgan birinchi qatorni qaytaradi;
  `GET /api/audit/export?day=YYYY-MM-DD` — kunlik JSONL + `X-Audit-Signature` (HMAC, server kaliti).
  Kunlik eksportni tashqi joyga saqlab boring — DB o'zgartirilsa zanjir va imzo buni ko'rsatadi.
- Gateway kalitlari ajratilgan: ingest kaliti faqat `POST /readings` ni, command kaliti faqat buyruq
  kanalini (`/commands/claim`, `/ack`, `/readback`) avtorizatsiya qiladi. Ingest kaliti sizib chiqsa faqat
  soxta o'lchov yuborish mumkin (validatsiya va sifat bayrog'i bilan cheklangan). Kalitlarni faqat gateway
  hostida (muhit o'zgaruvchisida) saqlang, muddatini qisqa qo'ying, almashtirish auditda.

## API

`http://<server>:8000/docs` — interaktiv OpenAPI hujjat (login → Authorize).
