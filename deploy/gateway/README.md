# Sath gateway

SCADA tarmog'ida ishlaydigan kichik Python skript: Modbus TCP, OPC UA, IEC 60870-5-104 yoki CSV dan o'qib,
Sath serverga HTTP orqali yuboradi. Serverga faqat HTTP kirish kifoya.

```
pip install requests "pymodbus>=3.8,<3.10" asyncua   # pymodbus 3.10+ API o'zgargan (device_id, SimDevice)
pip install c104                                      # faqat IEC 104 kerak bo'lsa (GPLv3 — pastga qarang)
cp gateway_config.example.json config.json   # server manzili, project_id, ingest_key, teglar
python ges_gateway.py config.json
```

- `ingest_key` — webda Monitoring → «Ulanish kalitlari» → ingest (tasdiqlovchi); muhitdan `GES_GATEWAY_INGEST_KEY`.
- Buyruq kanali default o'chiq: `"commands": true` + `command_key` (Ulanish kalitlari → command, yoki
  `GES_GATEWAY_COMMAND_KEY`) — ingest kaliti buyruq kanaliga yaramaydi.
- Fayl majburiy emas: `GES_GATEWAY_SERVER`, `GES_GATEWAY_PROJECT_ID`, `GES_GATEWAY_INGEST_KEY` (+ `..._COMMAND_KEY`,
  `..._COMMANDS=true`) bilan `python ges_gateway.py` (manbalar hozircha faqat faylda).
- Har teg `key` serverdagi sensor kaliti bilan bir xil bo'lishi kerak (Monitoring → Sensor qo'shish).
- Tarmoq uzilsa o'lchovlar diskdagi spool da (`spool_path`, default `gateway_spool.db`, SQLite) saqlanadi
  va qayta ulanganda eng eskisidan boshlab yuboriladi (restartda yo'qolmaydi); xatoda eksponensial
  kechikish 2…300 s. To'lganda (`spool_max_rows`, default 1 000 000): `spool_overflow: "drop_oldest"`
  (default, ogohlantirish) yoki `"stop"` (yangi yozuv qabul qilinmaydi). `diag: true` — serverga
  `GW.spool_rows`, `GW.spool_oldest_age_s`, `GW.spool_dropped`, `GW.clock_offset_s` diagnostika teglari
  (serverda shu kalitli sensorlar yarating; `diag_prefix` bilan nom o'zgartiriladi).
- Sifat va manba vaqti: OPC UA `read_data_value` — StatusCode → `quality` (good/uncertain/bad),
  SourceTimestamp → `src_ts`; Modbus — o'qish vaqti `src_ts`, o'qish xatosi → `quality=bad` (teg bo'yicha
  bir marta); aloqa uzilganda har teg uchun bitta `bad` yozuv, oxirgi qiymat takrorlanmaydi.
- OPC UA `mode: "subscribe"` — MonitoredItems obunasi (`publishing_interval_ms`, teg bo'yicha absolyut
  `deadband`): o'zgarish poll davridan tez keladi, o'zgarmasa hech narsa yuborilmaydi; sessiya uzilsa
  `quality=bad` (bir marta) va obuna qayta tiklanadi. `mode: "poll"` (default) — har siklda o'qish.
- IEC 60870-5-104 (`type: "iec104"`, `c104` kutubxonasi): `host`, `port` (2404), `common_address`,
  `interrogation_s` (ulanishda va davriy umumiy so'rov, default 300 s), `tick_ms`, `originator`; teg —
  `{key, ioa, type, scale}`; `type` ASDU nomi: `M_ME_NC_1` (float), `M_ME_NB_1` (skalyar, `scale`),
  `M_SP_NA_1`/`M_DP_NA_1` (bit), vaqt tamg'ali `M_ME_TF_1`, `M_SP_TB_1` — ulardan `src_ts` olinadi va bit
  o'zgarishlari SOE ro'yxatiga (ms tamg'a) yoziladi. QDS bitlari: IV → `bad`, SB → `substituted`,
  NT/BL/OV → `uncertain`. Spontan (COT=3) o'zgarishlar poll davrini kutmaydi; aloqa uzilsa har teg bir marta
  `bad`. Buyruqlar `commands: [{key, ioa, type}]` (`C_SE_NC_1` float setpoint, `C_SE_NB_1` skalyar,
  `C_SC_NA_1` bitta buyruq) — ro'yxat bo'lmasa yozish rad etiladi (default o'chiq; serverdagi B qoidalari
  — SBO, tasdiq, readback — o'z kuchida).
  **Litsenziya:** `c104` (lib60870 ustida) GPLv3 — shuning uchun u faqat shu alohida gateway jarayonida
  ishlatiladi, Sath serveri/web bilan bog'lanmaydi va server paketiga qo'shilmaydi (N2 talabi).
- SOE: vaqt tamg'ali diskret hodisalar (IEC 104 `M_SP_TB_1`/`M_DP_TB_1`) manbaning `soe` buferiga tushadi va
  spool orqali `POST /api/projects/{id}/soe` ga (ms aniqlik; takror serverda tashlanadi) yuboriladi.
- Soat: server `Date` sarlavhasi bilan farq `clock_warn_s` (5 s) dan oshsa ogohlantirish — NTP ni tekshiring.
- `sim` manbasi — sinov uchun (haqiqiy qurilma kerak emas).

Windows da doimiy ishlashi uchun Task Scheduler («At startup», «Run whether user is logged on») yoki NSSM.

## Buyruqlar (supervisory control)

Serverda `writable` belgilangan sensor (setpoint/rele) uchun dispetcher **Dispetcher paneli → Buyruq**
yuboradi (select-before-operate: tanlash → 30 s ichida bajarish; `requires_dual_approval` nuqtalarda ikkinchi
operator tasdig'i). Gateway har siklda `POST /api/projects/{id}/commands/claim` (X-Ingest-Key) bilan navbatni
oladi va teg konfiguratsiyasi bo'yicha yozadi: Modbus — `write_registers` (address/type/scale), OPC UA —
`write_value`, IEC 104 — `C_SE_NC_1` (`commands` ro'yxatidagi IOA ga), sim — simulyator qiymati. Natija `POST /api/commands/{id}/ack` (`acked`/`failed` + matn), so'ng
gateway tegni qayta o'qib `POST /api/commands/{id}/readback` ga yuboradi — server kutilgan qiymat bilan
solishtiradi (`readback_tolerance`), farq bo'lsa buyruq `mismatch` va dispetcherlarga bildirishnoma.
Buyruq TTL (`command_ttl_s`) ichida olinmasa `expired`; `sent` da javob kelmasa watchdog `failed` qiladi.
O'chirish: konfiguratsiyada `"commands": false`.


## OPC UA teglarini avtomatik topish (browse)

```
pip install asyncua
python ges_gateway.py browse opc.tcp://scada-host:4840 tags.csv 4 [user] [parol]
```

`tags.csv` — Sath «Monitoring → CSV import» formati (`key;name;kind;unit;protocol;address;element;low;high`):
`kind` nomdan taxmin qilinadi (sath/sarf/quvvat/bosim/harorat/tebranish/holat/ochilish), `address` — OPC UA
node id. Faylni ochib `element` ustuniga IFC element nomini (yoki GUID) yozing — import 3D ga avtomatik bog'laydi;
`gateway_config.json` ning `tags` ro'yxatiga ham xuddi shu `key`/`node_id` lar kiradi.
