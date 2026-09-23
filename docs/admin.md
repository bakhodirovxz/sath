# Sath — administrator qo'llanmasi

## O'rnatish (Docker, tavsiya)

Talab: Linux server (yoki Windows Server + Docker Desktop), 4+ CPU, 8+ GB RAM, 100+ GB disk (IFC fayllar).

```bash
git clone <repo> sath && cd sath/deploy
cp .env.example .env            # GES_ADMIN_PASSWORD, GES_PORT, GES_PUBLIC_URL ni to'ldiring
docker compose --profile https up -d --build   # server + web: https://<GES_DOMAIN> (8000 — faqat 127.0.0.1)
docker compose logs ges         # admin paroli bo'sh qoldirilgan bo'lsa — fayl yo'li shu yerda
```

Parollar (CODE-08): `POSTGRES_PASSWORD` majburiy (bo'lmasa `docker compose` to'xtaydi; default/zaif parol —
`ges`, `postgres`, ... — bilan server ishga tushmaydi). `GES_ADMIN_PASSWORD` parol siyosatidan o'tmasa
(masalan `admin123`) admin birinchi kirishda parolni almashtirishi shart va startda logda ogohlantirish chiqadi.
Bu tekshiruvlar faqat `GES_DEV_MODE=true` (lokal ishlab chiqish, testlar, CI) da yumshatiladi — ishlab
chiqarishda yoqmang.

Korporativ TLS proksi bo'lsa: `docker compose build --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" --build-arg NPM_STRICT_SSL=false`.

Ixtiyoriy profillar:
- **Sxema migratsiyasi**: Alembic (`server/ges_server/migrations/`). Startda `GES_AUTO_MIGRATE=true` (default) bo'lsa `upgrade head` avtomatik; eski (Alembic siz) DB birinchi startda baseline ga belgilanadi va yangilanadi. Qo'lda: `cd server && alembic upgrade head`; `GES_AUTO_MIGRATE=false` da sxema eskirgan bo'lsa server ishga tushmaydi. Yangilashdan oldin zaxira oling.
- **Historian qatlamlari**: xom (`GES_READINGS_RETENTION_DAYS=90`) → 1 daqiqa (`GES_AGG_1M_RETENTION_DAYS=400`) → 10 daqiqa (`GES_AGG_10M_RETENTION_DAYS=1100`) → 1 soat (abadiy); alarm hodisasi atrofidagi ±1 soat xom o'chirilmaydi. Sensor `archive_deadband` — o'lik zonali siqish (`archive_max_interval_s` dan keyin majburiy yozuv).
- **Ma'lumotlar bazasi**: compose defaulti — Postgres 16 + TimescaleDB (`timescale/timescaledb:latest-pg16`, parol `POSTGRES_PASSWORD`); `readings` hypertable (7 kunlik bo'laklar, `sensor_id` bo'yicha 4 bo'lim), ingest `COPY` bilan partiyali. SQLite faqat ishlab chiqish/sinov uchun (`GES_DATABASE_URL=sqlite:////data/ges.db`; compose da `POSTGRES_PASSWORD` baribir talab qilinadi). SQLite bilan server startda ogohlantiradi (SRV-08): bitta yozuvchi qulfi (ko'p foydalanuvchi/SCADA ingest da kutish), LISTEN/NOTIFY backplane va Timescale yo'q, `GES_ROLE=api|worker` (ko'p jarayon) ishonchsiz, CFD worker SQLite bilan ishlamaydi. Obraz yolg'iz (`docker run`) ishga tushsa default SQLite — faqat sinov. Tashqi Postgres da timescaledb bo'lmasa `readings` oddiy jadval bo'lib qoladi (logda ogohlantirish).
- **CFD** (OpenFOAM worker, ~1.5 GB obraz): `.env` da `GES_CFD_MODE=worker`, `docker compose --profile cfd up -d`. `CFD_CPUS` — worker uchun CPU. Worker server bilan **bir xil DB** ga ulanadi (compose `GES_DATABASE_URL`, default Postgres — SQLite deployda worker navbatni ko'rmaydi va ishga tushmaydi) va faqat `cfd_data` hajmini (`/data/cfd`: case papkalari + `result.json`) ko'radi: `secret.key`, IFC fayllar, `.env` sirlari OpenFOAM konteyneriga berilmaydi (`GES_SECRET_KEY_REQUIRED=false`); solver sirlarsiz muhitda ishlaydi.
- **Alarm rejimi (ISA-18.2)**: shelving default/maksimal muddati `GES_ALARM_SHELVE_DEFAULT_H=8`, `GES_ALARM_SHELVE_MAX_H=24`; out-of-service — muhandis+, sabab majburiy; `suppress_condition` — interlock ifodasi (masalan `AGG1_RUN == 0`).
- **MQTT**: `GES_MQTT_URL=mqtts://broker:8883` + `GES_MQTT_CA_FILE` (majburiy), `GES_MQTT_USERNAME`/`GES_MQTT_PASSWORD` (yoki `_PASSWORD_FILE`; parol URL da emas), ixtiyoriy mTLS `GES_MQTT_CERT_FILE`+`_KEY_FILE` — sensorlar `protocol=mqtt` bilan topic ga obuna bo'ladi (paho-mqtt: `pip install "./server[mqtt]"`, Docker obrazida bor). TLS siz `mqtt://` faqat loopback ga; boshqa hostga faqat `GES_MQTT_ALLOW_INSECURE=true` bilan, aks holda server ishga tushmaydi. `GES_MQTT_TOPIC_ALLOW` (masalan `sath/{project_id}/#`) — sensor topigi ro'yxatga mos kelmasa obuna bo'lmaydi. Aloqa uzilsa obuna sensorlari `bad`, qayta ulanishda qayta obuna; xabarlar partiyalab (`GES_MQTT_BATCH_SIZE/_MS`) yoziladi.
- **Email**: `GES_SMTP_URL=smtp://user:pass@mail.company.uz:587?from=ges@company.uz` — tasdiqlash hodisalari.

Docker siz (Windows/Linux, Python 3.10+):
```bash
pip install -e ./sim -e "./server[postgres,mqtt]"
cd web && npm ci && npm run build && cd ..
GES_DATA_DIR=/srv/ges-data ges-server        # http://0.0.0.0:8000 (web build avtomatik topiladi)
```
Docker siz sozlamalar fayli: `GES_ENV_FILE=/etc/sath/sath.env` (tavsiya) yoki `server/.env` — joriy papkadagi
`.env` ham (eski xatti-harakat) o'qiladi, lekin startda ogohlantiriladi. CFD rejimi default `worker`
(`GES_CFD_MODE`; dev da Docker Desktop bilan — `docker`).

## HTTPS

`docker compose --profile https up -d` — Caddy teskari proksi (`deploy/Caddyfile`): `GES_DOMAIN` uchun
sertifikat. Ichki tarmoqda `tls internal` — Caddy o'z CA si; root sertifikatini ishchi kompyuterlarga
o'rnating (`docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt`). Internetga ochiq
domen bo'lsa `tls internal` qatorini olib tashlang (Let's Encrypt). `.env` da `GES_PUBLIC_URL=https://<domen>`,
`GES_BIND=127.0.0.1` (8000 port tashqariga ochilmaydi — TLS chegarasi aylanib o'tilmaydi) va
`GES_RATE_TRUST_FORWARDED=true` (klient IP `X-Forwarded-For` dan — tezlik cheklovi uchun; Caddy siz **false**).
Caddyfile HSTS, CSP (`connect-src 'self' wss://{host}` — boshqa hostga ulanish yo'q), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` sarlavhalarini qo'shadi; ilova o'zi ham (Caddy siz) xuddi shu sarlavhalarni beradi (HSTS — HTTPS yoki ishonchli proksi `X-Forwarded-Proto: https` bo'lsa). `GES_BIND` default `127.0.0.1`.

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

## Uskuna kodlash (KKS / RDS-PP) va aktiv ierarxiyasi

Aktivlar ISO 14224 taksonomiyasi bo'yicha ierarxiyada (stansiya → tizim → uskuna → komponent → qism):
`parent_id`, `kks_code`, `taxonomy_level`, `function_location`. KKS (VGB-B 105/106) grammatikasi
tekshiriladi: `[n]AAAnn [AAnnn [AAnn]]` — masalan `1MKA10 AH001 MA01` (blok 1, generator tizimi 10,
agregat 001, komponent 01); RDS-PP (IEC 81346-10) — `=1MKA10 AH001`. Noto'g'ri kod 422, band kod 409,
ierarxiya halqasi 400; daraja koddan aniqlanadi (tizim/uskuna/komponent). Sensorlarga ham `kks_code`.
Dispetcher paneli → Aktivlar → «Ierarxiya (KKS)»: daraxt, uskuna holati va sog'ligi komponentlardan
agregatsiya (eng yomon holat / eng past indeks). CSV import: `kks_code,name,parent_kks,taxonomy_level,
element_guid,sensor_key,function_location` (`POST /api/projects/{id}/assets/import-kks`) — mavjud kod
yangilanadi, ota kod bo'yicha bog'lanadi (bo'sh bo'lsa koddan: komponent → uskuna → tizim).
`GET /api/kks/systems` — GES uchun KKS tizim kalitlari (MAA turbina, MKA generator, BAT transformator, LAB
bosimli quvur, HAD suv olish, …).

## Model validatsiyasi (I3)

Kalibrovka modelni ma'lumotga moslashtiradi, validatsiya esa **qaror**: model qaysi davr ma'lumotida,
qanday qabul mezoni bilan, kim tomonidan va qachongacha ishonchli deb tan olindi. Egizak javobida
`validation.status` bo'ladi: `validated` / `expired` / `failed` / `unvalidated`, va interfeysda
egizak sarlavhasida belgisi ko'rinadi.

**Qabul mezonlari** (standart, loyihada o'zgartiriladi va yozuvda saqlanadi): qoldiq RMSE ≤
o'lchanayotgan agregatlar nominal quvvatining 2 % i, |siljish| ≤ 1 %, kamida 72 ta ishlagan soat;
amal qilish muddati 180 kun. Mezon o'lchanayotgan agregatlarga nisbatan olinadi — modelda uch agregat
bo'lib bittasi o'lchanayotgan bo'lsa, mezon yumshab ketmasligi uchun.

**Imzolash** — `POST /api/projects/{id}/validation` (faqat **tasdiqlovchi**, approver): bu muhandislik
qarori. Mezon bajarilmasa yozuv `fail` verdikti bilan saqlanadi (yashirilmaydi). Holat va tarix —
`GET /api/projects/{id}/validation`.

**Qachon amal qilmay qoladi:** muddat tugaganda; oxirgi yozuv `fail` bo'lsa; model versiyasi
o'zgarganda (yozuvdagi versiya bilan joriy versiya farq qilsa) — bu holda «qayta validatsiya kerak»
deb ko'rsatiladi. Muddat tugaganda soatlik fon vazifasi muhandis va yuqori rollarga bir marta
bildirishnoma yuboradi.

## Holat baholash va ortiqchalik (I2)

**Ortiqchalik.** Bitta kattalikning bir nechta manbasi solishtiriladi: umumiy quvvat sensori ↔
agregatlar yig'indisi (chidamlilik 3 % yoki 0.5 MW); quvur sarfi o'lchagichi ↔ egizak modeli
hisoblagan sarf (8 % yoki 1 m³/s). Chegaradan oshsa `alert`, ikki barobardan oshsa `alarm`; natija
`TWIN.CHK.<nom>` virtual sensoriga (og'ish %) yoziladi va oddiy alarm qoidalari bilan ko'rinadi.

**Sath bahosi (Kalman).** Bashorat suv balansidan: `Δh = (Q_kiruvchi − Q_turbina − Q_tashlagich)·Δt /
A(h)`, bu yerda `A(h)` — ko'zgu yuzasi (maydon pasportidagi sath–hajm egri chizig'idan, bo'lmasa
`area_km2`). Yangilash — sath sensori bilan (Kalman koeffitsienti model va sensor shovqinidan).
Baho `TWIN.EST.LEVEL` virtual sensoriga yoziladi.

**Qotgan sensor.** Oxirgi 6 o'lchov bir xil bo'lsa-yu, balans sezilarli o'zgarish kutsa, sensor
«qotgan» deb belgilanadi: baho faqat model qadamidan olinadi, qiymat `substituted` sifati bilan
yoziladi va dispetcher va undan yuqori rollarga bildirishnoma boradi. Balans nolga yaqin bo'lsa
(sath haqiqatan o'zgarmasligi kerak) — qotgan deb belgilanmaydi.

Ma'lumot yetarli bo'lmasa (kiruvchi sarf sensori yoki ombor egri chizig'i yo'q) baho hisoblanmaydi:
`status: insufficient` va nima yetishmayotgani ko'rsatiladi — taxmin qilinmaydi.
API: `GET /api/projects/{id}/estimator` (hisoblaydi, yozmaydi), `POST …/estimator/run` (muhandis,
virtual sensorlarga yozadi); fon vazifasi soatiga bir marta bajaradi.

## Model kalibrovkasi va qoldiq kuzatuvi (I1)

Egizak model parametrlarini IFC pasportidan oladi. Ular o'lchangan ishga moslashtirilmasa, «og'ish %»
haqiqiy degradatsiyani va model xatosini qo'shib ko'rsatadi — shuning uchun egizak javobida
`calibrated` bayrog'i va `model_note` bor, interfeysda esa ogohlantirish chiqadi.

**Kalibrovka.** Dispetcher paneli → Egizak → «Model kalibrovkasi»: oyna (kun) tanlanadi va
«Hisoblash» / «Hisoblash va qo'llash» bosiladi (`POST /api/projects/{id}/calibration/run`, muhandis).
Tarixiy soatlik ma'lumotdan (byef sathlari, sarf, agregat quvvati) qoldiq
`P_o'lchangan − P_model(θ)` ning RMSE si minimallashtiriladi: koordinata bo'yicha tushish + oltin
kesim qidiruvi, parametrlar fizik chegarada (`penstock_roughness_mm` 0.01–5 mm, `max_efficiency`
0.80–0.96). Kamida 24 ta ishlagan soat kerak, aks holda natija `insufficient`.

**Identifikatsiya tekshiruvi.** Har parametr uchun profil sinovi bajariladi: parametr pasport
qiymatida qotiriladi, qolganlari qayta moslashtiriladi. Agar parametrni erkin qoldirish RMSE ni
2 % dan kam yaxshilasa, u shu ma'lumotdan **ajratilmaydi** (masalan, qisqa quvurda g'adir-budurlik
FIK bilan kollinear) va pasport qiymatida qoladi — natijada `diagnostics` da sababi yoziladi.
Bu soxta «kalibrovkalangan» qiymat paydo bo'lishining oldini oladi.

**Qo'llash va bekor qilish.** Natija `calibration_runs` da saqlanadi; qo'llanganda
`Project.calibration` ga yoziladi va egizak shu parametrlar bilan hisoblaydi. Eski yozuvni qayta
qo'llash — `POST /api/calibration/{run_id}/apply`; bekor qilish (pasportga qaytish) —
`DELETE /api/projects/{id}/calibration`.

**Drift.** Soatlik fon vazifasi oxirgi 7 kunlik qoldiqni tekshiradi: siljish (bias) kalibrovka
RMSE sining 2 barobaridan oshsa, model «siljigan» deb belgilanadi va muhandislarga bildirishnoma
yuboriladi (takrorlanmaydi; drift tugasa belgi olib tashlanadi). Holat:
`GET /api/projects/{id}/calibration` → `residuals`.

## Holat monitoringi (ISO 13374 / OSA-CBM)

Sog'liq hisobi olti funksional blokka ajratilgan (`server/ges_server/monitoring/cm/`), har biri
alohida modul va aniq interfeys bilan — shuning uchun uchinchi tomon tizimi istalgan darajadan
ulanadi:

| Blok | Modul | Vazifa |
|---|---|---|
| DA — ma'lumot yig'ish | `cm/da.py` | kanallar (tebranish, podshipnik harorati, val tebranishi, havo oralig'i, qisman razryad, moyda suv), soatlik qatorlar, spektr yozuvlari, mashina guruhi |
| DM — qayta ishlash | `cm/dm.py` | chiziqli trend, baza va z-score, spektr cho'qqilari, 1×/2×/3× garmonikalar, podshipnik nuqson chastotalari |
| SD — holat aniqlash | `cm/sd.py` | ISO 20816-5 zonalari, harorat/PD/havo oralig'i/moy chegaralari, anomaliya, tashqi holat |
| HA — sog'liq bahosi | `cm/ha.py` | 0–100 indeks, kavitatsiya (Toma σ), FIK og'ishi, transformator issiq nuqtasi |
| PA — prognoz | `cm/pa.py` | C/D zonasigacha kun, alarm chegarasigacha kun, RUL (eng qisqasi) |
| AG — tavsiya | `cm/ag.py` | muammo/tavsiya matni, HEALTH.* sensorlari, avtomatik ish buyrug'i (ISO 14224 «holat monitoringi» aniqlash usuli bilan) |

`monitoring/health.py` eski nomlarni saqlab qolgan yupqa moslik qatlami.

**Mashina guruhi** (ISO 20816-5 zona chegaralari uchun) aktiv konfiguratsiyasidan, bo'lmasa ota
aktivdan (H1 ierarxiyasi), bo'lmasa KKS tizimi kalitidan aniqlanadi (MAA turbina — 2 yoki 4,
MKA generator — 4), aks holda 4.

**Spektr saqlash** (`spectra` jadvali — vaqt qatori emas): `POST /api/projects/{id}/cm/spectra`
(`kind`: spectrum | envelope | orbit | waveform, `values` + `f_min`/`f_max` yoki aniq `freqs`,
`rpm`, `unit`, `source`). Yuborish huquqi: muhandis tokeni yoki `X-Ingest-Key` (CM gateway'i).
`GET /api/cm/spectra/{id}` qiymatlar bilan birga DM xususiyatlarini qaytaradi. Podshipnik nuqson
chastotalari aktiv konfiguratsiyasidagi geometriyadan hisoblanadi: `bearing: {n, d_mm, D_mm,
alpha_deg}` (BPFO/BPFI/BSF/FTF — ISO 13373-3, Harris). Nuqson chastotasi envelope-spektr
energiyasining 15 % idan oshsa «ogohlantirish», 30 % idan oshsa «alarm».

**Tashqi tizim natijasi** (Bently Nevada, SKF IMx, Voith OnCare): `POST /api/projects/{id}/cm/results`
— `block` SD | HA | PA, `state`, `health_score` (0–100), `rul_days`, `diagnosis`, `confidence`,
`valid_hours` (muddatidan keyin natija hisobga olinmaydi). Yakuniy sog'liq indeksi ichki va tashqi
bahoning **eng pastiga** tenglashtiriladi — tashqi tizim Sath ko'rmaydigan kanallarni ko'rishi mumkin.
`GET /api/assets/{id}/cm` — aktiv bo'yicha butun zanjir natijasi (dispetcher paneli → Sog'liq →
aktiv kartochkasidagi ⚡ tugmasi).

## Texnik xizmat (CMMS): rejalar, mehnat, qismlar, ruxsatnoma va LOTO

**Profilaktik rejalar.** Dispetcher paneli → Ish buyruqlari → «Profilaktik xizmat rejalari»: davriylik
kun (`interval_days`) yoki agregat ish soati (`interval_hours`, quvvat sensori hisoblagichidan) bo'yicha,
vazifalar ro'yxati, ustuvorlik, muddat (`lead_days`), ruxsatnoma talabi. Muddati kelganda ish buyrug'i
avtomatik yaratiladi (`source="plan"`, soatlik fon vazifasida yoki «Hozir tekshirish» —
`POST /api/projects/{id}/maintenance-plans/run`). Shu reja bo'yicha ochiq buyruq turganda yangisi
yaratilmaydi. Mavjud uskunani ro'yxatga olayotganda «oxirgi bajarilgan xizmat sanasi»
(`last_generated_at`) va ish soati hisoblagichi (`last_run_hours`) ko'rsatiladi.

**Nosozlik kodlari (ISO 14224:2016).** Ish buyrug'ini yopishda nosozlik rejimi (`failure_mode`:
FTS ishga tushmadi, BRD buzilish, VIB tebranish, OHE qizish, ELP tashqi oqish, …), sabab
(`failure_cause`: loyiha, montaj, ekspluatatsiya, texnik xizmat, eskirish, tashqi ta'sir) va aniqlash
usuli (`detection_method`: rejali ko'rik, holat monitoringi, funksional sinov, alarm, …) tanlanadi.
Ro'yxat: `GET /api/cmms/codes`; ro'yxatdan tashqari kod 422.

**Mehnat va xarajat.** `POST /api/work-orders/{id}/labor` — kim, necha soat, izoh (o'z vaqtini dispetcher
yozadi, boshqa xodim nomidan — muhandis). Xarajat avtomatik: mehnat (soat × stavka; yozuvda stavka
bo'lmasa buyruq `labor_rate` i) + sarflangan qismlar + qo'shimcha (`extra_cost`: pudrat, transport).

**Ehtiyot qism bandlash va sarflash.** Bandlash (`/parts/reserve`) ombor qoldig'ini kamaytirmaydi, bo'sh
qoldiqni (qoldiq − ochiq buyruqlardagi bandlik) kamaytiradi; sarflash (`/parts/consume`) ombordan chiqim
qiladi, avval shu buyruqdagi bandlikdan yechadi va xarajatni qayta hisoblaydi. Qoldiq minimal zaxiradan
tushsa muhandislarga bildirishnoma.

**Ruxsatnoma (PTW) va LOTO.** `POST /api/work-orders/{id}/permit` — `requested` (dispetcher) →
`issued`/`closed` (faqat tasdiqlovchi). `POST /api/work-orders/{id}/loto` — energiya izolyatsiyasi
(IEC 60204-1 §5.3): ruxsatnoma talab qilinsa avval berilishi kerak. **LOTO faol ekan shu aktivga tegishli
sensorlarga boshqaruv buyrug'i 409 bilan rad etiladi va chetlab o'tib bo'lmaydi** (tasdiqlovchining
`override` i ham ishlamaydi) — izolyatsiyani ish buyrug'ida olib tashlash kerak (qo'ygan xodim yoki
tasdiqlovchi). LOTO faol bo'lsa ish buyrug'i yopilmaydi. Sensor aktivga quvvat/tebranish/podshipnik
sensori, bir xil IFC elementi yoki KKS kodi prefiksi (H1 ierarxiyasi) orqali bog'lanadi; izolyatsiya
nuqtasida sensor to'g'ridan-to'g'ri ko'rsatilishi ham mumkin. Faol ro'yxat: `GET /api/projects/{id}/loto`.

**Xizmat tarixi.** `GET /api/assets/{id}/history` (Aktivlar → «Tarix»): ish buyruqlari (mehnat soati,
sarflangan qismlar, xarajat taqsimoti, ISO 14224 kodlari), yil bo'yicha jamlanma va nosozlik rejimlari
taqsimoti — ISO 55001 aktiv yozuvi uchun.

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

Hammasi `data/` (Docker: `sath_ges_data` volume) da: `ges.db` (SQLite), `files/` (IFC, sha256 bo'yicha),
`sim/`, `desktop/`, `secret.key`, `initial-admin-password.txt` (o'chiring); CFD case papkalari — alohida
`sath_cfd_data` (`/data/cfd`). Compose loyiha nomi qat'iy `sath` (`name: sath`) — hajm nomlari papka nomiga
bog'liq emas. Eski deploy (nomsiz, `deploy_ges_data`) dan o'tish: `docker compose -p deploy down`, so'ng
ma'lumotni ko'chiring (`docker run --rm -v deploy_ges_data:/from -v sath_ges_data:/to alpine cp -a /from/. /to/`;
Postgres uchun `deploy_pg_data` → `sath_pg_data`) yoki bir martalik `COMPOSE_PROJECT=deploy ./backup.sh` va
yangi stendda `./restore.sh`. `backup.sh` hajm topilmasa (exit 3), SQLite `ges.db` yo'q/bo'sh bo'lsa (exit 5)
yoki `PRAGMA integrity_check` o'tmasa (exit 6) zaxira yozmaydi.
Zaxira va tiklash — quyidagi bo'lim. Yangi versiyaga o'tish: `git pull && docker compose up -d --build` —
sxema Alembic bilan avtomatik yangilanadi (oldin zaxira oling).

## Log va metrikalar

- Log: `GES_LOG_FORMAT=json` (Loki/ELK — bir qator bitta JSON: `ts`, `level`, `logger`, `msg`, `request_id`,
  `exc`) yoki `text` (default); daraja `GES_LOG_LEVEL` (INFO). Har HTTP javobda `X-Request-ID` (kiruvchi
  sarlavha qabul qilinadi) — log yozuvlarida xuddi shu id.
- Prometheus: `GET /api/metrics` — `sath_http_requests_total{method,status}`, `sath_http_request_duration_seconds`,
  `sath_ingest_requests_total{result}`, `sath_job_queue_depth{queue,status}`, `sath_build_info`. Himoya:
  `GES_METRICS_TOKEN` berilsa `Authorization: Bearer <token>`; berilmasa faqat loopback dan. Caddy
  `/api/metrics` ni tashqariga bermaydi (404) — Prometheus ichki tarmoqdan `ges:8000` ga token bilan ulanadi.
  Hisoblagichlar replika boshiga (har replikani alohida scrape qiling).

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
python desktop/build/build_blender_bundle.py --installer   # yoki build_portable.py (FreeCAD fork)
# bir martalik: imzo kalit juftligi (private — CI secret / parol menejeri; ochiq — serverga va addonga)
python desktop/build/publish_desktop.py --gen-key ~/.sath/release-ed25519.pem
python desktop/build/publish_desktop.py --server https://<server> --user admin --product blender \
    --signing-key ~/.sath/release-ed25519.pem   # dist dagi eng yangi installer + zip
```
Yangilanish butunligi (SEC-03):
- Server paketni `.part` ga yozadi va faqat sha256/imzo tekshiruvidan keyin atomik `os.replace` qiladi —
  uzilgan yuklash «latest» bo'lib ko'rinmaydi. Manifest (`<paket>.manifest.json`): product, version, kind,
  name, size, sha256, signature, key_id.
- Imzo — Ed25519, kanonik JSON `{"kind","name","product","sha256","size","version"}` ustidan
  (`server/ges_server/system/release.py`). Private kalit serverda **yo'q** — server buzilsa ham soxta paket
  imzolab bo'lmaydi. `GES_DESKTOP_SIGNING_PUBLIC_KEY` (base64) — server yuklashda imzoni tekshiradi;
  `GES_DESKTOP_REQUIRE_SIGNATURE=true` — imzosiz paket rad etiladi.
- `GET /api/desktop/latest?product=blender|freecad` (default `blender`) — `sha256`, `size`, `signature`,
  `key_id`, `product`; FreeCAD va Blender paketlari serverda alohida (`data/desktop/<product>/`) — bir xil
  nomda to'qnashmaydi. Eski yuklangan paketlar birinchi murojaatda `blender/` ga ko'chiriladi.
- Blender addoni paketni brauzerda ochmaydi: o'zi yuklab oladi, hajm + sha256 ni, sozlamalarda
  «Yangilanish kaliti» (yoki `SATH_UPDATE_PUBLIC_KEY`) berilgan bo'lsa Ed25519 imzoni tekshiradi; mos
  kelmasa o'rnatishni taklif qilmaydi. Addon server manzili default `https://`.
- Kod imzosi (Authenticode): `.github/workflows/blender-fork.yml` da `SATH_SIGN_CERT_PFX_B64` /
  `SATH_SIGN_CERT_PASSWORD` secretlari bo'lsa signtool bilan imzolanadi (bo'lmasa qadam o'tkaziladi);
  lokal NSIS installer — shu sertifikat bilan `signtool sign /fd SHA256 /tr <timestamp> /td SHA256`.

Webda «Loyihalar» sahifasida «Sath x.y.z o'rnatish ↓ / zip ↓» tugmalari chiqadi; desktop kirishda
`GET /api/desktop/latest` bilan tekshiradi (installer afzal). Versiya `desktop/GesWorkbench/package.xml` da —
oshirib, `python desktop/build/sync_fork.py` bilan fork ga o'tkazing. Yadro (FreeCAD) o'zgartirilganda
fork dagi GitHub Actions «Sath build» ishlatiladi.

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
