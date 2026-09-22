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
