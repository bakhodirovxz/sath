# deploy/

Sath serverini ishga tushirish va ekspluatatsiya fayllari. To'liq qo'llanma — [`docs/admin.md`](../docs/admin.md);
xavfsizlik zonalari, kanallar va gateway joylashuvi — [`docs/security-zones.md`](../docs/security-zones.md)
(IEC 62443: Sath — Z3 sanoat DMZ, gateway — Z2 SCADA tarmog'i, Sath hech qachon Z2 ga ulanmaydi).

| Fayl | Vazifa |
|---|---|
| `docker-compose.yml` | `ges` (server+web), `postgres` (TimescaleDB), profillar: `https` (Caddy), `cfd` (OpenFOAM worker), `sim` (simulyator + gateway stendi). Konteynerlar imtiyozsiz, `cap_drop: ALL`, `read_only` |
| `.env.example` | Barcha sozlamalar (portlar, DB, tezlik cheklovi, MFA, sessiyalar, sandbox, DEM kanali) — `.env` ga nusxalang |
| `Dockerfile`, `Dockerfile.cfd` | Obrazlar (root siz `sath` foydalanuvchisi, bubblewrap) |
| `Caddyfile` | HTTPS teskari proksi, HSTS/CSP sarlavhalari |
| `backup.sh`, `restore.sh`, `backup.cron.example` | Shifrlangan zaxira, tiklash (`--test` — sinov), jadval; RTO/RPO — admin.md |
| `gateway/` | SCADA tarmog'ida ishlaydigan gateway (Modbus/OPC UA/IEC 104 → HTTPS) |
| `simulator/` | GES simulyatori (Modbus/OPC UA server) — sinov stendi |

Tezkor ishga tushirish:
```
cp .env.example .env            # GES_ADMIN_PASSWORD, POSTGRES_PASSWORD, GES_DOMAIN, GES_BIND=127.0.0.1
docker compose --profile https up -d --build
docker compose logs ges          # birinchi admin paroli (agar GES_ADMIN_PASSWORD bo'sh bo'lsa)
```
Firewall: Z2 dan faqat gateway IP → 443; korporativ tarmoqdan 443; admin VLAN dan 22; chiquvchi — SMTP va
(kerak bo'lsa) DEM/Let's Encrypt — namunalar `security-zones.md` §4.

Build argumentlari (`deploy/Dockerfile`):
- `WITH_DWG=1` (default) — LibreDWG (`dwg2dxf`) majburiy (Debian da paket yo'q — `dwg` bosqichida GNU
  manbadan `LIBREDWG_VERSION`/`LIBREDWG_SHA256` bilan quriladi, ~3–5 daqiqa): paket o'rnatilmasa build **xato bilan to'xtaydi**
  (jimgina DWG siz obraz chiqmaydi). `WITH_DWG=0` — ataylab DWG siz. Holat: `GET /api/health` → `"dwg": true|false`.
  **Litsenziya:** LibreDWG — GPLv3. Sath uni alohida CLI dastur (`dwg2dxf`) sifatida chaqiradi (bog'lanmaydi).
  Ichki foydalanishda cheklov yo'q; obrazni uchinchi tomonga tarqatsangiz GPLv3 talabi bo'yicha LibreDWG manba
  kodini taklif qiling (obraz GNU manba tarbolidan quriladi: `https://ftp.gnu.org/gnu/libredwg/libredwg-<LIBREDWG_VERSION>.tar.xz` — shu faylni taqdim eting) yoki `WITH_DWG=0` bilan tarqating.
- `WITH_BLENDER=1` — `.blend` importi uchun rasmiy Blender (versiya va sha256 pin — Dockerfile ga qarang).

Takrorlanuvchan build (CI-03): bazaviy va yordamchi obrazlar (`Dockerfile*`, compose, `backup.sh`/`restore.sh`,
CI) `teg@sha256:digest` bilan qotirilgan — yangilash: `docker buildx imagetools inspect <obraz:teg>`, digestni
almashtirib testlarni o'tkazing. Python bog'liqliklari — `server/requirements.lock`, `sim/requirements.lock`
(`pip install -c ...` constraints; `python desktop/build/gen_lock.py` bilan yangilanadi, CI `--check`).
Node: web build va runtime da bir xil Node 22 (runtime ga web bosqichidagi `node` nusxalanadi).
