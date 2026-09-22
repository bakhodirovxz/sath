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
domen bo'lsa `tls internal` qatorini olib tashlang (Let's Encrypt). `.env` da `GES_PUBLIC_URL=https://<domen>`,
`GES_BIND=127.0.0.1` (8000 port tashqariga ochilmaydi — TLS chegarasi aylanib o'tilmaydi) va
`GES_RATE_TRUST_FORWARDED=true` (klient IP `X-Forwarded-For` dan — tezlik cheklovi uchun; Caddy siz **false**).
Caddyfile HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` sarlavhalarini qo'shadi.

## Ish navbati (simulyatsiya, fragments, geometriya)

Simulyatsiyalar va yuklangan IFC uchun hosilaviy ishlar (fragments `.frag`, QTO/to'qnashuv) DB navbatida
(`sim_jobs`, `jobs`): server qayta ishga tushsa ish yo'qolmaydi — startda egasiz `running` ishlar
yarashtiriladi (urinish qolsa qayta navbatga, aks holda `failed` + sabab). Ishchi ishni atomik claim qiladi
(ikki ishchi bir ishni ololmaydi) va ijarani (90 s) uzaytirib turadi; ijara tugasa ish egasiz hisoblanadi.
Jarayon ichidagi ishchi: `GES_JOBS_CONCURRENCY` (2) ta ish bir vaqtda. CFD `GES_CFD_MODE=worker` da alohida
`cfd` konteyneri (`ges-worker`) oladi — bir necha worker xavfsiz. Kvota: foydalanuvchi bo'yicha
`GES_SIM_MAX_ACTIVE_PER_USER` (3), loyiha bo'yicha `GES_SIM_MAX_ACTIVE_PER_PROJECT` (10); CFD — muhandis+.
Takror so'rov (tarmoq uzilishi) uchun `idempotency_key` — mavjud ish qaytadi. Bir hostda bitta Sath jarayoni
kutiladi (restart yarashtirishi hostname bo'yicha); ko'p replika — L8.

## Yuklash chegaralari va parser sandboxi

Barcha yuklashlar oqimda cheklanadi (xotiraga olgandan keyin emas): IFC/mesh `GES_MAX_UPLOAD_MB` (2048),
CSV import va BCF `GES_SMALL_UPLOAD_MB` (50) — oshsa 413, qolgani o'qilmaydi; Content-Length chegaradan
katta so'rov tanasi umuman o'qilmaydi. CSV/BCF parse va ingest thread hovuzida — WebSocket tarqatish
bloklanmaydi. Tashqi konverterlar (dwg2dxf, ODA, `blender --python`, assimp, Node/web-ifc) `GES_SANDBOX`
rejimida ishlaydi: Linux da `bwrap` (tarmoqsiz, PID ajratilgan, faqat ish papkasi yoziladi, `/data`
ko'rinmaydi), u ishlamasa `rlimit` (xotira 4 GB, CPU vaqti, jarayonlar soni), doim vaqt chegarasi. Docker
default seccomp profili bwrap ga yo'l bermaydi — konteynerda `rlimit` ishlaydi (sinalgan: xotira chegarasi
MemoryError beradi, tarmoq ochiq). Qattiqroq izolyatsiya uchun `ges` servisiga
`security_opt: [no-new-privileges:true, seccomp=unconfined]` bering — u holda `bwrap` yoqiladi (sinalgan:
tarmoq yo'q, ildiz FS faqat o'qish, `/data` yashirin); tanlov: seccomp syscall filtri ↔ konverter nom
maydoni izolyatsiyasi. Konteynerlar root siz (`sath`,
uid 10001), `cap_drop: ALL`, `no-new-privileges`, `ges` faqat o'qiladigan ildiz FS (`/data`, `/tmp`
yoziladi), `pids_limit`, `GES_MEM_LIMIT`. Eslatma: `docker` CFD rejimi (server o'zi `docker run` qiladi)
konteyner ichida ishlamaydi — `worker` rejimini ishlating.

## Jonli oqim (WebSocket) va ko'p replika

Har klientning o'z chegaralangan navbati (200 xabar) va yuboruvchisi bor: sekin/qotgan HMI boshqalarni
to'xtatmaydi — navbat to'lsa eng eski xabar tashlanadi, 10 s da yuborilmagan xabar ulanishni yopadi.
Diagnostika: `GET /api/projects/{id}/live/clients` (muhandis+) — navbat chuqurligi, tashlangan xabarlar,
`slow` belgisi. Server 10 s da `ping` yuboradi, klient `pong` qaytaradi; `GES_WS_IDLE_S` (90) davomida
javob bo'lmasa 4408 bilan yopiladi (yarim ochiq soketlar yig'ilmaydi). Foydalanuvchi bo'yicha
`GES_WS_MAX_PER_USER` (8) ulanish (4429). Bir necha `ges` replikasi (load balancer ortida) bo'lsa jonli
xabarlar Postgres `LISTEN/NOTIFY` (`sath_live`) orqali replikalar orasida tarqaladi
(`GES_LIVE_BACKPLANE=auto` — Postgres bo'lsa yoqiq; SQLite da bitta jarayon). Load balancer WebSocket ni
(`/api/projects/*/live`) o'tkazishi va bitta ulanishni bitta replikaga yopishtirishi shart emas — chipta
va sessiya DB da. Tezlik cheklovi (L1) esa replika boshiga hisoblanadi.

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

## IFC sxemasi (IFC4 / IFC4.3)

`GES_IFC_SCHEMA` — webdan yaratilgan/import qilingan yangi modellar sxemasi: `IFC4` (default, barcha
vositalar bilan mos) yoki `IFC4X3_ADD2` (ISO 16739-1:2024). IFC4.3 da GES obyektlari infratuzilma
entitylariga xaritalanadi: suv tashlagich / suv qabul qilgich / mashina zali → `IfcFacilityPartCommon`
(USERDEFINED, ObjectType SPILLWAY/INTAKE/POWERHOUSE; maydonga agregatsiya), tuproqli/toshli to'g'on →
`IfcEarthworksFill` (EMBANKMENT), beton to'g'on → `IfcWall`, bosimli quvur → `IfcPipeSegment`
(RIGIDSEGMENT/PENSTOCK), generator ENGINEGENERATOR, transformator VOLTAGE, relyef → `IfcGeographicElement`
TERRAIN; `Pset_GES_*` ikkala sxemada saqlanadi. Mavjud IFC4 modellar o'qilishda davom etadi (viewer, QTO,
IDS, klassifikatsiya). Aniq berilgan sinf nomi sxemaga nisbatan tekshiriladi — noto'g'ri nom xato (server
`models/ifc_schema.py`, desktop `ifc_classes.py` — ro'yxat `desktop/build/gen_ifc_classes.py` bilan
yangilanadi). Namuna: `docs/samples/namuna_ges_v2_ifc4x3.ifc` (`make_sample_ges.py --schema=IFC4X3_ADD2`).
`GET /api/ifc/schemas` — sxemalar va xarita. Cheklov: brauzer viewer (web-ifc/fragments) IFC4.3 geometriyasini
chizadi, lekin `IfcFacilityPartCommon` fazoviy elementini outlinerda hozircha ko'rsatmaydi (kutubxona
chegarasi); server tomonida (QTO, to'qnashuv, IDS, klassifikatsiya, COBie) to'liq qo'llab-quvvatlanadi.

## IDS — axborot talablari (model tekshiruvi)

Har yuklangan IFC `docs/ids/sath-ges.ids` (IDS 1.0, buildingSMART; `ifctester`) bo'yicha avtomatik
tekshiriladi: loyiha nomi, maydon georeferensiyasi (RefLatitude/RefLongitude), elementlar nomlangan,
`Pset_GES_Dam/Turbine/Penstock` pasport maydonlari (qiymat chegaralari, ro'yxatdan turi). Natija versiya
ro'yxatida `IDS ✓/✗` belgisi, Model → Tekshiruv → IDS (talab bo'yicha yiqilgan elementlar, bosilsa 3D da
tanlanadi, «Qayta tekshirish»). Loyiha sahifasida tasdiqlovchi «IDS majburiy» ni yoqsa o'tmagan versiya
tasdiqlanmaydi va merge qilinmaydi (409, sabab bilan); o'chiq bo'lsa faqat ogohlantirish. Talablarni
o'zgartirish: IDS faylini tahrirlang (`GES_IDS_FILE` bilan boshqa fayl) — sxema/kalitlar bir joyda.

## ISO 19650: yaroqlilik va reviziya kodlari, nomlash, EIR/BEP

Har versiya ISO 19650 (UK NA / PAS 1192 lineage) yaroqlilik kodi bilan: yuklash → **S0** (WIP), tasdiqqa
yuborish → **S3** (shared; tasdiqlovchi S1–S7 ni o'zgartira oladi), merge → **A1** (published; A1–An, B1–Bn,
CR, PR), rad → S0. Reviziya: yuklashda P01, P02…; merge da C01, C02… (avtomatik; tasdiqlovchi qo'lda
o'zgartirishi mumkin, holatga mos bo'lmagan kod rad etiladi). Loyihada konteyner nomlash shabloni
(`{project}-{originator}-{volume}-{level}-{type}-{role}-{number}`, maydonlar [A-Z0-9]+) — mos kelmagan
fayl ogohlantiradi, «majburiy» bo'lsa yuklash rad etiladi. Hujjatlar: EIR, BEP, TIDP/MIDP (pdf/docx/xlsx…)
loyiha sahifasida (muhandis yuklaydi, tasdiqlovchi o'chiradi). Eski versiyalar migratsiyada holatdan
kod oladi (wip S0, shared S3, published A1).

## Aktiv topshiruvi (COBie ga o'xshash)

Model versiyasidan aktiv registri: `GET /api/versions/{id}/assets/register` (JSON) yoki `?format=csv` —
COBie 2.4 soddalashtirilgan CSV varaqlari (Facility, Floor, Type, Component, Attribute) zip da: tur,
joylashuv (qavat), ishlab chiqaruvchi/model (`Pset_ManufacturerTypeInformation` yoki `Pset_GES_*`
Ishlab_chiqaruvchi/Model), seriya (`Pset_ManufacturerOccurrence.SerialNumber` / Seriya), kafolat
(`Pset_Warranty` / Kafolat_oy), texnik xizmat davri (TX_davri_soat), klassifikatsiya kodi. Dispetcher
paneli → Aktivlar → «IFC dan aktivlar…» turbina/generator/transformator/zatvor/nasos elementlarini `Asset`
yozuvlariga bog'laydi (element GUID bo'yicha yangilanadi, pasport ma'lumotlari `config` da). Har aktivga
hujjat: qo'llanma, pasport, zavod sinov protokoli, ishga tushirish akti (operator yuklaydi, muhandis
o'chiradi).

## Klassifikatsiya va federatsiya

Klassifikatorlar: **SATH-KSI** (mahalliy GES inshoot/uskuna sinflari: GTS.01 to'g'on … USK.03 transformator)
va **Uniclass 2015** (Ss_/Pr_/En_ kodlari). Webdan yaratilgan/import qilingan har element GES turi bo'yicha
`IfcClassificationReference` oladi; mavjud modelni Model → Versiyalar → «Klassifikatsiya» yangi versiyaga
klassifikatsiyalaydi (`POST /api/versions/{id}/classify`). Versiya tafsilotida kodlar bo'yicha soni.
Federatsiya (loyiha sahifasi): bir necha model bitta koordinata fazosida — a'zo bo'yicha siljish (m) va
burilish; «3D + to'qnashuvlar» birlashtirilgan IFC ni ko'rsatadi va faqat modellar orasidagi to'qnashuvlarni
ro'yxatlaydi (`GET /api/federations/{id}/clashes`, kesh). To'qnashuv tekshiruvi endi keng bosqich panjara
indeksi bilan — element soni cheklanmaydi (ilgari 1500 dan keyin faqat bbox).

## Georeferensiya (CRS)

Loyiha sahifasida tasdiqlovchi EPSG (WGS 84/UTM 41N `32641`, 42N `32642`; Pulkovo 1942/Gauss-Krüger 11–12
`28411`/`28412`), lokal (0,0,0) ning global E/N/H joyi va X o'qi burilishini beradi («Taklif» — lat/lon dan
zona va origin). Shundan keyin webdan yaratilgan/ import qilingan har versiya `IfcProjectedCRS` +
`IfcMapConversion` va `IfcSite RefLatitude/RefLongitude` bilan yoziladi; yuklangan faylda ular bo'lmasa
versiya ogohlantiradi va «Georeferensiyalash» tugmasi mavjud modelga qo'shadi. Elementni tanlaganda
xususiyatlar panelida global E/N/H va lat/lon; DEM import loyiha CRS bo'yicha joylashadi (markaz lat/lon →
lokal x,y, balandlik global − origin H). API: `GET /api/projects/{id}/crs/convert?x&y&z` yoki `?lat&lon`.
Proyeksiya kutubxonasiz (Krüger qatorlari, zona ichida < 1 mm); Pulkovo ↔ WGS 84 Helmert (EPSG::15865,
~1–3 m) — geodeziya bilan solishtirishda hisobga oling. IDS SATH-02 talabi georeferensiyani tekshiradi.

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
Zaxira va tiklash — quyidagi bo'lim. Yangi versiyaga o'tish: `git pull && docker compose up -d --build` —
sxema Alembic bilan avtomatik yangilanadi (oldin zaxira oling).

## Yuqori ishonchlilik (ko'p replika)

Kichik deploy: bitta `ges` (`GES_ROLE=all`). Uzluksizlik kerak bo'lsa `deploy/docker-compose.ha.yml`:
`ges` 2+ replika (`GES_ROLE=api`, Caddy `Caddyfile.ha` — Docker DNS orqali taqsimlash, `/api/ready`
bo'yicha nosoz replikani chetlash), `ges-worker` bitta nusxa (fon sikli, ish navbati, MQTT; Postgres
advisory lock — ikkinchi nusxa tasodifan ishga tushsa ham davriy ishlar takrorlanmaydi), jonli oqim
replikalar orasida LISTEN/NOTIFY, sessiya/chipta DB da (yopishqoq sessiya shart emas). Bitta replika
o'chirilganda xizmat uzilmaydi (ochiq WebSocket lar qayta ulanadi — klient eksponensial kechikish bilan).
Endpointlar: `GET /api/health` — tiriklik; `GET /api/ready` — tayyorlik (DB, sxema head, backplane,
worker rolida ish navbati) — 503 bo'lsa trafik berilmaydi. Postgres oqimli replika va qo'lda failover
(RTO ≈ 5 daqiqa) — `deploy/pg-replica/README.md`.

## Zaxira va tiklash (RTO/RPO)

| | Qiymat | Izoh |
|---|---|---|
| **RPO** (yo'qotilishi mumkin bo'lgan davr) | ≤ 24 soat (kunlik jadval), ≤ 1 soat (soatlik) | `backup.cron.example`; o'lchov oqimi muhim bo'lsa soatlik + gateway spool (E) |
| **RTO** (tiklash vaqti) | ≈ 15–30 daqiqa | `restore.sh` + `docker compose up -d`; katta IFC arxivida (10+ GB) fayl nusxasi vaqti qo'shiladi |
| Saqlash | 30 kun mahalliy (`BACKUP_KEEP_DAYS`) + tashqi nusxa | NAS (`BACKUP_COPY_DIR`) yoki `rclone` (`BACKUP_RCLONE_REMOTE`) |

`deploy/backup.sh`: Postgres `pg_dump -Fc` (yoki SQLite `.backup` — izchil nusxa) + `files/` (IFC/mesh,
content-addressed) + manifest (`alembic` versiyasi, sha256) → `backups/sath-YYYYmmdd-HHMM.tar.gz.enc`
(AES-256-CBC, PBKDF2 200k, `BACKUP_PASSPHRASE_FILE`). `secret.key` arxivga **kirmaydi** — uni parol
menejerida alohida saqlang (yo'qolsa ma'lumot saqlanadi, sessiyalar tugaydi, audit eksport imzolari
tekshirilmaydi). `derived/` (fragments, QTO keshi) default kirmaydi — qayta hisoblanadi
(`BACKUP_WITH_DERIVED=1` bilan kiradi). `sim/`, `cfd/` natijalari kirmaydi.

Tiklash protsedurasi (yangi serverda ham):
1. `git clone` + `deploy/.env` (eski `GES_SECRET_KEY` yoki `secret.key` ni parol menejeridan qaytaring);
   `docker compose up -d postgres` (SQLite bo'lsa shart emas).
2. `BACKUP_PASSPHRASE_FILE=... ./restore.sh backups/sath-....tar.gz.enc` — sha256 va ichki manifest
   tekshiriladi, `ges` to'xtatiladi, DB `ges_restore` ga tiklanib almashtiriladi (eski DB `ges_old_<vaqt>`
   nomi bilan qoladi), fayllar volume ga ochiladi.
3. `docker compose up -d` → `GET /api/health`, admin bilan `GET /api/audit/verify` (`ok: true`),
   loyihalar/modellar ko'rinadi, historian grafigi oxirgi zaxira vaqtigacha.
4. Gateway spool (E) mavjud bo'lsa yetkazilmagan o'lchovlar o'zi keladi; qolgan oyna — RPO.

Tiklashni davriy sinash: `./restore.sh --test <arxiv>` — vaqtinchalik TimescaleDB konteynerida
`pg_restore`, jadval/qator sanog'i va Alembic versiyasi chiqariladi, keyin konteyner o'chiriladi
(ishlab chiqarishga tegmaydi). `backup.cron.example` da haftalik sinov qatori bor; natija
`/var/log/sath-restore-test.log` da `TIKLASH SINOVI: OK` bo'lishi shart. Sinalgan: 2026-09-22
(SQLite va Postgres arxivlari, `--test` va to'liq tiklash — L6).

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

Zonalar/kanallar modeli (IEC 62443), gateway joylashuvi, firewall namunalari va O'zbekiston KAI tekshirish
ro'yxati — [`security-zones.md`](security-zones.md). Tashqi DEM kanali: `GES_DEM_ENABLED`/`GES_DEM_TILE_URL`.

- HTTPS: oldiga Caddy/nginx (reverse proxy) qo'ying; WebSocket (`/api/projects/*/live`) ni ham o'tkazing.
- `GES_SECRET_KEY` — o'zgartirilsa hamma sessiya tugaydi (avtomatik yaratilgani `data/secret.key`).
- Sessiyalar (L2): access token 15 daqiqa (`GES_ACCESS_TOKEN_MINUTES`), refresh token 12 soat
  (`GES_REFRESH_TOKEN_HOURS`) — brauzerda HttpOnly `sath_refresh` cookie (JS o'qimaydi), desktop/gateway
  uchun javob tanasida; har ishlatilganda aylantiriladi, eski tokenning takrori hamma sessiyani bekor qiladi
  (`auth.session_reuse`). Parol/rol o'zgarishi, a'zolikdan chiqarish, o'chirish — foydalanuvchining barcha
  tokenlari darhol yaroqsiz (`token_version`). Profil → Sessiyalar: qurilmalar ro'yxati, yakunlash, «Barcha
  qurilmalardan chiqish». WebSocket 60 s li chipta bilan ochiladi (sessiya tokeni URL/loglarga tushmaydi) va
  har `GES_WS_REAUTH_S` da huquq qayta tekshiriladi. JWT `iss=sath`, `aud=sath-api`.
- Parol siyosati (NIST 800-63B): kamida `GES_PASSWORD_MIN_LENGTH` (8; tavsiya 12) belgi, harf+raqam aralash,
  keng tarqalgan parollar va login parol ichida bo'lishi rad etiladi. Admin bergan yoki boshlang'ich
  (`initial-admin-password.txt`) parol birinchi kirishda majburiy almashtiriladi (`must_change_password`;
  yaratishda «Birinchi kirishda parolni almashtirsin» belgisi — xizmat hisoblari uchun o'chiriladi).
- Tezlik cheklovi (429, `Retry-After`): login — IP bo'yicha (`GES_RATE_LOGIN_PER_MIN`, 30), ingest —
  loyiha bo'yicha so'rovlar (`GES_RATE_INGEST_PER_MIN`, 600; gateway partiyalab yuborsin), buyruqlar va sim
  ishlari — foydalanuvchi bo'yicha (60 / 20). Hisoblar jarayon ichida (replika boshiga).
- Hisobni bloklash: `GES_LOGIN_MAX_FAILURES` (10) ketma-ket noto'g'ri parol/MFA → `GES_LOGIN_LOCKOUT_MINUTES`
  (15) davomida 423, auditda `auth.account_locked`. Ochish: Boshqaruv → foydalanuvchi → «Blokni ochish»
  (`PATCH /api/users/{id}` `{"unlock": true}`).
- MFA (TOTP, RFC 6238 — Google Authenticator/Aegis/FreeOTP): Profil → MFA → kalitni ilovaga kiritib kod bilan
  tasdiqlash. `GES_MFA_REQUIRED_FOR_ADMINS=true` — admin MFA yoqmaguncha admin amallari 403 (tavsiya).
  Telefon yo'qolsa admin `{"mfa_reset": true}` bilan bekor qiladi (auditda).
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
