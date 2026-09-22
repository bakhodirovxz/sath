# Sath — xavfsizlik zonalari va kanallari (IEC 62443-3-2)

Holat: 2026-09-22 (roadmap L7). Sath — stansiya boshqaruv tizimi (SCADA/DCS) emas: u SCADA dan ma'lumot
oluvchi zavod axborot va raqamli egizak qatlami (Purdue L3 / L3.5). Bu hujjat qaysi komponent qaysi zonada
turishi, zonalar orasidagi kanallar (conduit), har kanalning xavfsizlik darajasi maqsadi (SL-T) va gateway
o'rnatish qoidalarini belgilaydi. Deploy (`deploy/docker-compose.yml`, `deploy/Caddyfile`, gateway) shu
modelni aks ettirishi shart; o'zgarish — avval shu hujjatga.

## 1. Zonalar

| Zona | Purdue | Nima bor | Sath komponenti | Egasi |
|---|---|---|---|---|
| **Z0/Z1 — jarayon/boshqaruv** | L0–L1 | Datchiklar, ijro mexanizmlari, PLC/RTU, turbina regulyatori, himoya avtomatikasi | **yo'q** (Sath bu zonaga hech qachon ulanmaydi) | Stansiya avtomatikasi |
| **Z2 — SCADA/HMI** | L2 | SCADA serverlari, operator HMI, tarixchi, OPC UA/Modbus/IEC 104 serverlari | **Sath gateway** (`deploy/gateway/ges_gateway.py`) — SCADA tarmog'idagi alohida host (yoki SCADA serverida xizmat) | Stansiya IT/ASU TP |
| **Z3 — sanoat DMZ (Sath)** | L3/L3.5 | Sath serveri (`ges`), Postgres/TimescaleDB, CFD worker, Caddy TLS | `docker compose` stek; faqat HTTPS (443) kirish, ichki 8000 port yopiq (`GES_BIND=127.0.0.1`) | Sath admin |
| **Z4 — korporativ** | L4 | Brauzerlar (dispetcher, muhandis, tasdiqlovchi), FreeCAD/Blender desktop, SMTP, parol menejeri | Web UI, desktop mijoz | Korporativ IT |
| **Z5 — tashqi (internet)** | — | DEM plitkalari (AWS Terrain Tiles), Let's Encrypt (ochiq domen bo'lsa), Telegram/SMS (P5) | ixtiyoriy chiquvchi kanallar — default yopiq bo'lishi kerak | — |

Zona ichida ishonch to'liq emas: Z3 ichida konteynerlar root siz, `cap_drop: ALL`, faqat o'qiladigan FS,
parserlar sandboxda (L5); Postgres faqat compose tarmog'ida (host portga chiqarilmaydi).

## 2. Kanallar (conduit) va SL-T

SL-T — IEC 62443-3-3 bo'yicha maqsadli daraja (SL 1 — tasodifiy, SL 2 — oddiy vositali qasddan hujum, SL 3 —
maxsus ko'nikma/resursli hujum). Yo'nalish — TCP ulanishni kim ochadi.

| Kanal | Zonalar | Yo'nalish | Protokol/port | Autentifikatsiya | SL-T | Amaldagi nazorat |
|---|---|---|---|---|---|---|
| **C1 o'lchov** | Z2 → Z2 (gateway ↔ SCADA server) | gateway → SCADA | Modbus TCP 502, OPC UA 4840, IEC 104 2404 | OPC UA: sertifikat/parol (`security_policy`), Modbus/IEC 104: yo'q (protokol) | **SL 2** (o'qish) | Gateway faqat SCADA tarmog'ida; Modbus/IEC 104 uchun firewall faqat gateway IP → server IP:port |
| **C1w buyruq** | Z2 (gateway → SCADA) | gateway → SCADA | shu portlar, yozish | shu | **SL 3** | Default o'chiq (`commands: false`); yoqilsa Z3 dagi B qoidalari (SBO, chegara, tezlik, ikki tasdiq, interlock, readback) + gateway `commands` ro'yxati; buyruq kanali alohida kalit (`command_key`) |
| **C2 ingest** | Z2 → Z3 | gateway → Sath (chiquvchi) | HTTPS 443 | `X-Ingest-Key` (muddatli, loyiha bo'yicha), TLS (Caddy; ichki CA root gateway hostida) | **SL 2** | Firewall: Z2 dan Z3 ga faqat gateway IP → Sath:443; Z3 → Z2 hech narsa (Sath SCADA ga ulanmaydi); tezlik cheklovi, validatsiya, sifat bayrog'i |
| **C2c buyruq navbati** | Z2 → Z3 | gateway → Sath (claim/ack/readback) | HTTPS 443 | `X-Command-Key` | **SL 3** | Ingest kaliti buyruq kanaliga yaramaydi; auditda har amal; kalit muddati qisqa |
| **C3 foydalanuvchi** | Z4 → Z3 | brauzer/desktop → Sath | HTTPS 443, WSS | Parol siyosati + MFA (adminlar majburiy), 15 daqiqalik token, refresh cookie, lockout, IP tezlik cheklovi | **SL 2** (tasdiqlovchi/admin — SL 3 talab: MFA) | L1/L2; HSTS/CSP; sessiyalar ro'yxati; rol o'zgarsa tokenlar bekor |
| **C4 email** | Z3 → Z4 | Sath → SMTP | SMTPS 465 / STARTTLS 587 | SMTP parol | SL 1 | Faqat bildirishnoma matni; sozlanmasa yo'q |
| **C5 DEM plitkalari** | Z3 → Z5 | Sath → AWS S3 | HTTPS 443 | yo'q (ochiq ma'lumot) | SL 1 | **Ma'lumot joylashuvi:** so'rovda faqat plitka koordinatalari, lekin bu ob'ekt joylashuvini uchinchi tomonga oshkor qiladi. Yopiq stansiyada `GES_DEM_ENABLED=false` yoki ichki ko'zgu `GES_DEM_TILE_URL`; firewall default Z3 → internet yopiq |
| **C6 MQTT** (ixtiyoriy) | Z2 → Z3 (broker Z3 da) yoki Z2 | broker ↔ Sath | MQTTS 8883 | parol + CA pinning, mTLS | SL 2 | `mqtts://` majburiy (loopback dan tashqari `mqtt://` faqat `GES_MQTT_ALLOW_INSECURE`), obuna filtri |
| **C7 DB/CFD** | Z3 ichida | ges/cfd → Postgres | 5432 (compose tarmog'i) | parol | SL 1 | Host portga chiqarilmaydi; TLS — L8 (replikatsiya) bilan |
| **C8 boshqaruv** | Z4 → Z3 | admin → Docker host | SSH 22 | kalit + MFA (host siyosati) | SL 3 | Faqat admin VLAN dan; `sudo` jurnali |

Xulosa: **Sath hech qachon Z2 ga ulanmaydi** — barcha SCADA-tomon oqim gateway tomonidan chiquvchi HTTPS
bilan olib chiqiladi (L3 → L3.5 ning to'g'ri yo'nalishi). Buyruqlar ham gateway tomonidan *olinadi*
(`claim`), Sath tomonidan itarilmaydi — Z3 buzilsa ham Z2 ga faol ulanish yo'li paydo bo'lmaydi.

## 3. Gateway qayerga o'rnatiladi (va qayerga o'rnatilmaydi)

- **O'rnatiladi:** Z2 dagi alohida host (Linux VM yoki Windows xizmati, NSSM/Task Scheduler) — SCADA
  serveriga o'qish uchun ruxsat, Sath ga faqat HTTPS 443 chiquvchi. Ikkinchi variant: SCADA serverining
  o'zida xizmat sifatida (vendor ruxsati bilan; `commands: false` bo'lsa xavf minimal).
- **O'rnatilmaydi:** Z1 (PLC tarmog'i) — gateway PLC ga bevosita ulanmaydi, faqat SCADA/OPC UA serveriga;
  Z3/Z4 (korporativ yoki Sath hosti) — u holda Z3 dan Z2 ga kiruvchi kanal ochiladi, bu modelni buzadi.
- Gateway hostida: faqat kerakli portlar, avtomatik yangilanish o'chiq (o'zgarish nazorati), spool diski
  shifrlangan (o'lchovlar), `ingest_key`/`command_key` muhitda (faylga emas) yoki OS sirlar do'konida,
  vaqt NTP (soat farqi `GW.clock_offset_s` bilan kuzatiladi).
- IEC 104 (`c104`, GPLv3) — faqat gateway jarayonida (N2 talabi, litsenziya ajratilgan).

## 4. Tarmoq segmentatsiyasi va firewall namunalari

Z2 chegara firewall (Z2 → Z3 chiquvchi, faqat gateway):
```
# nftables (Z2 chiqish, gateway 10.20.2.15 → Sath 10.30.1.10)
table inet z2_egress {
  chain forward { type filter hook forward priority 0; policy drop;
    ip saddr 10.20.2.15 ip daddr 10.30.1.10 tcp dport 443 accept
    ct state established,related accept
  }
}
```
Z3 (Sath hosti) — kiruvchi faqat 443 (va admin VLAN dan 22), chiquvchi faqat SMTP va (ruxsat etilsa) DEM:
```
# ufw (Docker hostida; Docker o'z zanjirlarini qo'shadi — DOCKER-USER zanjirini ham cheklang)
ufw default deny incoming; ufw default deny outgoing
ufw allow from 10.20.2.15 to any port 443 proto tcp     # gateway (C2)
ufw allow from 10.40.0.0/16 to any port 443 proto tcp   # korporativ (C3)
ufw allow from 10.40.9.0/24 to any port 22 proto tcp    # admin (C8)
ufw allow out to 10.40.1.25 port 587 proto tcp          # SMTP (C4)
# ufw allow out to any port 443 proto tcp               # DEM/Let's Encrypt (C5) — faqat kerak bo'lsa
```
Windows gateway hosti: `New-NetFirewallRule -Direction Outbound -RemoteAddress 10.30.1.10 -RemotePort 443
-Protocol TCP -Action Allow` va qolgan chiquvchi — Block. Docker `ges` servisi 8000 portni faqat
`127.0.0.1` ga bog'laydi (`GES_BIND`), Caddy 443 ni ochadi.

## 5. Xavf bahosi (qisqacha, IEC 62443-3-2 ZCR 5)

| Tahdid | Kanal | Oqibat | Nazorat | Qoldiq xavf |
|---|---|---|---|---|
| Ingest kaliti sizib chiqdi | C2 | Soxta o'lchov, noto'g'ri alarm | Validatsiya, sifat bayrog'i, tezlik cheklovi, kalit muddati/almashtirish (audit), buyruq kanaliga yaramaydi | Past |
| Buyruq kaliti sizib chiqdi | C2c/C1w | Noto'g'ri setpoint | Default o'chiq; chegara/tezlik/interlock/SBO/ikki tasdiq/readback; gateway `commands` ro'yxati; SCADA o'z himoyasi | O'rta → gateway hostini qattiqlashtirish |
| Brauzer XSS / sessiya o'g'irlash | C3 | Foydalanuvchi nomidan amal | Token xotirada, HttpOnly refresh, CSP, qisqa muddat, MFA, sessiyalar ro'yxati | Past |
| Zararli IFC/CAD fayl | C3 | Server RCE/DoS | Sandbox (bwrap/rlimit), root siz, hajm chegarasi, vaqt chegarasi | Past–o'rta |
| Sath hosti buzildi | Z3 | Ma'lumot sizishi; Z2 ga hujum? | Z3 → Z2 ulanish yo'q (faqat gateway chiquvchi), Postgres ichki, zaxira shifrlangan | O'rta (ma'lumot), past (jarayon) |
| Ob'ekt joylashuvi oshkor | C5 | Maxfiylik | DEM o'chirish/ko'zgu | Sozlamaga bog'liq |

## 6. O'zbekiston KAI talablari (tekshirish ro'yxati)

GES — kritik axborot infratuzilmasi (KAI) ob'ekti bo'lishi mumkin («Kiberxavfsizlik to'g'risida»gi Qonun,
2022; KAI ob'ektlari va ularning xavfsizligi bo'yicha Hukumat qarorlari). Sath egasi/operatori uchun
tekshirish ro'yxati — **aniq muddatlar, shakllar va vakolatli organ yuridik xizmat bilan tasdiqlanadi**:
1. **Ro'yxatga olish:** stansiya axborot tizimlari (SCADA, Sath) ni KAI ob'ektlari reestriga kiritish
   (vakolatli organ — kiberxavfsizlik bo'yicha davlat organi); Sath uchun bu hujjat + `docs/admin.md`
   tizim pasportining texnik qismi.
2. **Muvofiqlikni baholash:** davriy xavfsizlik auditi/sertifikatlash; Sath tomonidan tayyor dalillar —
   audit zanjiri (`/api/audit/verify`), imzolangan kunlik eksport, sessiya/MFA siyosati, zaxira sinovi
   jurnali, bu zonalar modeli.
3. **Hodisa haqida xabar berish:** kiberxavfsizlik hodisasi (masalan, `auth.session_reuse`,
   `auth.account_locked` to'lqini, buyruq `mismatch`, noma'lum ingest manbasi) aniqlanganda ichki
   javob tartibi va vakolatli organga belgilangan muddatda xabar; Sath auditidan eksport (JSONL + HMAC)
   dalil sifatida.
4. **Ma'lumot joylashuvi:** ma'lumotlar (o'lchovlar, modellar) O'zbekiston hududidagi serverlarda
   (Z3 on-prem); tashqi kanallar (C5 DEM, Let's Encrypt) — yopiq yoki ko'zgu; SMTP — korporativ.
5. **Kriptografiya:** TLS (Caddy), AES-256 zaxira, Argon2 parol, HMAC audit — milliy talablar bo'yicha
   sertifikatlangan vositalar talab qilinsa, Caddy/openssl o'rniga sertifikatlangan shlyuz qo'yiladi
   (Z3 chegarasida), Sath o'zgarmaydi.

## 7. Deploy ushbu modelni qanday aks ettiradi

- `deploy/docker-compose.yml`: `ges` porti `GES_BIND` (https profilida 127.0.0.1), Caddy 443, Postgres
  portsiz, konteynerlar imtiyozsiz; `sim-gateway`/`simulator` faqat sinov profili.
- `deploy/Caddyfile`: TLS, HSTS/CSP; `GES_RATE_TRUST_FORWARDED=true`.
- `deploy/gateway/`: SCADA tomonida, chiquvchi HTTPS, kalitlar muhitda, `commands` default o'chiq.
- `.env`: `GES_DEM_ENABLED`, `GES_DEM_TILE_URL`, `GES_MQTT_*` (TLS), `GES_MFA_REQUIRED_FOR_ADMINS=true`.
- O'zgarish tartibi: yangi kanal (masalan Telegram — P5) avval shu jadvalga SL-T bilan kiritiladi, keyin
  deploy/firewall.
