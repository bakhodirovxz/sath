# Sath — BIM SCADA darajasiga yetish yo'l xaritasi

Bu hujjat Claude Code bilan bosqichma-bosqich bajarish uchun yozilgan. Har vazifa mustaqil
berilishi mumkin: muammo, tegiladigan fayllar, qabul mezoni va bog'liqligi ko'rsatilgan.
Vaqt baholari ataylab yo'q — tartib va bog'liqlik muhim.

Holat: 2026-09-21 dagi to'liq audit asosida (server 13.2k, web 11.5k, sim 8.3k, desktop 13k LOC).

Holat belgilari: har vazifa sarlavhasi oxirida — ✅ bajarildi (`commit`), 🔄 jarayonda, belgisiz — boshlanmagan.
Bajarish tartibi: A → J → B → E → C → D → F → L → G → H → I → K, M davomiy, P — M dan keyin yoki tegishli
blok bilan.

---

## 0. Maqsad va pozitsiya

### 0.1 Nimaga erishamiz

Sath — GES uchun BIM modeli, muhandislik hisoblari va real vaqt telemetriyasi bitta
platformada birlashgan raqamli egizak. Yakuniy holat:

- Telemetriya sifat bayrog'i va manbadagi vaqt tamg'asi bilan keladi, ishonchli.
- Alarm tizimi ISA-18.2 ga mos: ko'p bosqichli chegaralar, o'lik zona, shelving, KPI.
- Dispetcher interfeysi ISA-101 bo'yicha, muhandis interfeysi hozirgi Blender uslubida.
- Boshqaruv yo'li sanoat talabiga mos: chegaralar, select-before-operate, watchdog, audit.
- BIM tomoni tekshiriladigan: IFC4.3, IDS validatsiya, georeferensiya, KKS kodlash.
- Muhandislik hisoblari normaga havola qilinadigan va tashqi benchmark bilan sinalgan.

### 0.2 Nima emas

Sath stansiya boshqaruv tizimi (DCS/PLC) o'rnini bosmaydi. U Purdue modelida Level 3/3.5 —
zavod axborot va raqamli egizak qatlami. Buni hujjatlarda aniq yozish kerak, aks holda
dispetcher unga boshqaruv tizimi sifatida tayanib qolishi mumkin.

### 0.3 Vazifa V0 — pozitsiyani to'g'rilash ✅ (`1dd1618`)

Muammo: `README.md:37` va `docs/plan.md` da "SCADA" darajasidagi da'vo bor; `docs/admin.md` da
"Ingest kaliti faqat o'lchov yuboradi; boshqa hech narsaga ruxsat bermaydi" degan gap bor va u
noto'g'ri — o'sha kalit `GET /projects/{id}/commands/pending` (holatni o'zgartiradi) va
`POST /commands/{id}/ack` ni ham avtorizatsiya qiladi.

Ish:
- README va plan.md da "SCADA tengligi" o'rniga: "SCADA dan ma'lumot oluvchi zavod axborot va
  raqamli egizak qatlami; stansiya boshqaruv tizimi o'rnini bosmaydi".
- ISO 19650 da'vosini "jarayon bo'yicha moslashtirilgan, to'liq muvofiq emas" deb belgilash
  (G4 bajarilgach qayta ko'riladi).
- admin.md dagi ingest kaliti haqidagi noto'g'ri gapni tuzatish.

Fayllar: `README.md`, `docs/plan.md`, `docs/admin.md`
Qabul mezoni: hujjatlarda tekshirib bo'lmaydigan da'vo qolmaydi.
Bog'liqlik: yo'q.

---

## 1. Bosqichlar va bog'liqlik grafigi

```
A. Ma'lumotlar poydevori ──┬─> B. Boshqaruv xavfsizligi
                           ├─> C. Alarm tizimi (ISA-18.2)
                           ├─> D. Historian va masshtab
                           └─> E. Gateway, protokollar, simulyator

C + D + E ──> F. Interfeys (ISA-101 dispetcher + Blender muhandis)

G. BIM tomoni (IFC4.3, IDS, CRS)   — mustaqil
H. Aktivlar, KKS, CMMS             — A dan keyin
I. Egizak yetukligi                — A, D, E dan keyin
J. Muhandislik hisoblari           — mustaqil, lekin shoshilinch
K. Desktop konsolidatsiya          — mustaqil
L. Ishonchlilik, xavfsizlik, deploy — A, B dan keyin
M. Sifat infratuzilmasi            — parallel, doimiy
```

Tavsiya etilgan tartib: A → J → B → E → C → D → F → L → G → H → I → K, M davomiy.

J (muhandislik hisoblari) erta turadi, chunki u hozir noto'g'ri natija beradi va u natijalar
xavfsizlik qarorlariga ta'sir qiladi.

---

## A. Ma'lumotlar poydevori

Butun tizimning eng past qatlami. Bu bosqich tugamaguncha yuqoridagi hech narsa ishonchli emas.

### A1 — Reading ga sifat bayrog'i va manbadagi vaqt tamg'asi ✅ (`2e4fb09`)

Muammo: `server/ges_server/orm.py:419` — `Reading` faqat `(sensor_id, ts, value)`. Sifat tushunchasi
yo'q. OPC UA `StatusCode`, IEC 61850 quality bitlari, qo'lda kiritilgan qiymat, o'rnini bosuvchi
qiymat va haqiqiy o'lchov — hammasi bir xil ko'rinadi. Historian, `twin.py`, `health.py` va kunlik
energiya hisoboti ularni farqsiz iste'mol qiladi.

Ikkinchi muammo: vaqt tamg'asi manbada emas, HTTP yuborish paytida qo'yiladi
(`deploy/gateway/ges_gateway.py` `Pusher.push()`). 10 soniyalik poll da har qiymat aytgan
vaqtidan ~10 soniya eski bo'lishi mumkin.

Ish:
- `Reading` ga ikki ustun: `quality` (enum: `good | uncertain | bad | substituted | manual`) va
  `src_ts` (manbadagi vaqt, nullable — yo'q bo'lsa `ts` ishlatiladi).
- `ReadingIn` (`monitoring/router.py:104`) ga shu maydonlar, default `good`.
- `ReadingHourly` ga `pct_good` (butun soat ichidagi good foizi) va `n_bad`.
- `live.ingest` (`monitoring/live.py:161`) — `bad` sifatli qiymat `last_value` ni yangilamaydi va
  alarm baholamaydi; `uncertain` yangilaydi lekin alarm bosqichi bir daraja pasayadi.
- `historian.rollup` — faqat `good` va `uncertain` ni agregatga kiritadi.
- `twin.py`, `health.py` — `bad` qiymatli sensorga tayanadigan hisobni `null` qaytaradi,
  "ma'lumot yo'q" deb belgilaydi (jim nol emas).
- WebSocket snapshot va reading xabarlariga `quality` qo'shiladi.

Fayllar: `server/ges_server/orm.py`, `monitoring/router.py`, `monitoring/live.py`,
`monitoring/historian.py`, `monitoring/twin.py`, `monitoring/health.py`, `web/src/api/client.ts`

Qabul mezoni:
- `bad` sifatli qiymat yuborilganda sensor `last_value` o'zgarmaydi va alarm ochilmaydi (test).
- `pct_good < 100` bo'lgan soat hisobotda belgilanadi.
- Web da sifat bayrog'i tip darajasida mavjud (`Reading.quality`).

Bog'liqlik: A2 (migratsiya mexanizmi) bilan birga bajarilishi kerak.

### A2 — Alembic migratsiyalari ✅ (`246da9e`)

Muammo: `server/ges_server/db.py:44` dagi `ensure_columns()` faqat `ADD COLUMN` qila oladi.
Tur o'zgarishi, o'chirish, qayta nomlash, backfill, downgrade, versiya jadvali — hech biri yo'q.
Startda avtomatik ishlaydi (`main.py:42`). Auditga tortiladigan tizim uchun migratsiya tarixining
yo'qligi jiddiy kamchilik.

Ish:
- `alembic` ni `server/pyproject.toml` ga qo'shish, `server/migrations/` yaratish.
- Hozirgi sxemadan boshlang'ich revision (baseline) generatsiya qilish.
- `ensure_columns()` ni olib tashlash; startda `alembic upgrade head` (konfiguratsiya bilan
  o'chirilishi mumkin — ishlab chiqarishda qo'lda bajarish uchun).
- SQLite uchun `render_as_batch=True` (ALTER cheklovlari sababli).
- A1 dagi ustunlar birinchi haqiqiy migratsiya bo'ladi, backfill bilan (`quality='good'`).

Fayllar: `server/pyproject.toml`, `server/migrations/`, `server/ges_server/db.py`,
`server/ges_server/main.py`

Qabul mezoni:
- Eski sxemali DB ustida `alembic upgrade head` ishlaydi va testda tekshiriladi.
- `ensure_columns` kodda qolmaydi.

Bog'liqlik: yo'q. Eng birinchi bajarilishi kerak.

### A3 — Kiruvchi qiymat va vaqt tamg'asi validatsiyasi ✅ (`186a4b3`)

Muammo: `monitoring/router.py:103` — `value: Any`, `live.py:171` — yalang'och `float()`.
`"nan"`, `"inf"`, `"1e400"` o'tadi. NaN kelsa `evaluate_alarm` (`live.py:60`) dagi barcha
taqqoslashlar `False` bo'ladi va o'sha sensor alarmi boshqa hech qachon ishlamaydi.
`_parse_ts` (`live.py:221`) chegarasiz — 9999-yildagi `ts` kelsa `sensor.last_ts` qotadi va
`ts >= last_ts` qo'riqchisi (`live.py:177`) barcha haqiqiy o'lchovlarni rad etadi.

Ish:
- `ReadingIn.value` → `float` bilan validator: `math.isfinite()` majburiy, aks holda 422.
- `ts` chegarasi: `now - 30 kun` dan `now + 5 daqiqa` gacha; tashqarida — rad etiladi va
  `quality=bad` bilan hisobga olinadi yoki xato.
- Sensor bo'yicha `min_raw`/`max_raw` (fizik diapazon) — tashqarida `quality=bad`.
- `last_ts` monotonlik qo'riqchisiga vaqt chegarasi: kelajakdagi tamg'a `last_ts` ni qotirmaydi.

Fayllar: `server/ges_server/monitoring/router.py`, `monitoring/live.py`, `orm.py`

Qabul mezoni: NaN, inf, 9999-yil va 1970-yil tamg'alari uchun negativ testlar bor va o'tadi.
Bog'liqlik: A1.

### A4 — Audit jurnali yaxlitligi ✅ (`421fcc8`)

Muammo: `orm.py:657` — `AuditLog` oddiy o'zgaruvchan jadval. Hash zanjiri, imzo, append-only
yo'q. `audit.py:16` commit ni chaqiruvchiga qoldiradi va so'rov tranzaksiyasini baham ko'radi —
rollback bo'lsa audit yozuvi ham yo'qoladi. Yozilmaydigan hodisalar: kirish xatolari
(`auth/router.py:55` audit dan oldin xato tashlaydi), parol o'zgarishi, reading ingest,
`ack-all`, WebSocket ulanishlari, eksportlar.

Ish:
- `AuditLog` ga `prev_hash`, `row_hash` (SHA-256 ustida: id, ts, user_id, action, target,
  detail, prev_hash).
- `audit.log()` ni alohida tranzaksiyaga chiqarish (asosiy rollback audit ni o'chirmasin).
- Yetishmayotgan hodisalarni qo'shish: `auth.login_failed`, `auth.password_changed`,
  `ws.connect`, `ws.disconnect`, `readings.ingest` (jamlangan — batch bo'yicha bitta yozuv),
  `alarm.ack_all`, `export.csv`, `export.report`, `ingest_key.read`.
- `GET /api/audit/verify` — zanjirni tekshiradi va birinchi buzilgan yozuvni qaytaradi.
- Davriy imzolangan eksport: kunlik JSONL + imzo (dastlab HMAC, keyin kalit juftligi).

Fayllar: `server/ges_server/orm.py`, `audit.py`, `auth/router.py`,
`system/audit_router.py`, `monitoring/router.py`, `monitoring/live.py`

Qabul mezoni:
- Qo'lda o'zgartirilgan yozuv `verify` da aniqlanadi (test).
- Kirish xatosi audit da ko'rinadi.

Bog'liqlik: A2.

### A5 — Versiya raqami poygasi va indekslar ✅ (`2de7aeb`)

Muammo: `models/router.py:220` — `SELECT max(number)+1` keyin INSERT, `UniqueConstraint`
ustiga. Parallel commit da ushlanmagan `IntegrityError` → 500.

Indeks kamchiliklari:
- `alarm_events` da `sensor_id` bo'yicha indeks yo'q, lekin har alarm o'tishida
  `filter_by(sensor_id=..., ended_at=None)` bajariladi (`live.py:96`).
- `audit_log` da `user_id` indeksi yo'q, `system/audit_router.py:52` esa shu bo'yicha filtrlaydi.
- `commands` da sensor bo'yicha ochiq buyruq uchun partial unique indeks yo'q (B1 ga kerak).

Ish:
- Versiya raqamini retry bilan (3 urinish) yoki `SELECT ... FOR UPDATE` bilan (Postgres) olish;
  konflikt bo'lsa 409.
- Yuqoridagi indekslarni qo'shish.

Fayllar: `server/ges_server/models/router.py`, `orm.py`, migratsiya
Qabul mezoni: parallel commit testi 500 bermaydi.
Bog'liqlik: A2.

---

## B. Boshqaruv xavfsizligi

Hozir bu eng zaif joy. `POST /commands` amalda Modbus holding registeriga yozadigan REST
endpoint, hech qanday sanoat qo'riqchisisiz.

### B1 — Buyruq xavfsizlik konverti

Muammo (`server/ges_server/monitoring/control.py:104`):
- `CommandIn.value: float` cheksiz. Sensorda min/max maydoni umuman yo'q (`orm.py:384`) —
  faqat `low_alarm`/`high_alarm` bor, ular maslahat xarakterida.
- `inf`/`nan` o'tadi va gateway da `int(round(raw))` ni buzadi (OverflowError) yoki float32
  registerga ±inf yozadi.
- `control.py:117` — "bitta sensorga bitta ochiq buyruq" tekshiruvi TOCTOU: SELECT keyin INSERT,
  qator qulfi yo'q, unique indeks yo'q. Ikki parallel so'rov ikkita qarama-qarshi setpoint qo'yadi.
- TTL yo'q: `pending` buyruq cheksiz kutadi. Gateway ikki kun o'chib qolsa, qayta ulanganda
  eskirgan setpointlarni bajaradi.
- `sent` holatida qotgan buyruqni to'xtatish yo'li yo'q (`cancel_command` faqat `pending` ni
  qabul qiladi, `control.py:165`), va u sensorni abadiy bloklaydi.

Ish:
- `Sensor` ga: `min_setpoint`, `max_setpoint`, `max_rate_per_min`, `requires_dual_approval`.
- `create_command` da: diapazon tekshiruvi, `isfinite`, oxirgi buyruqdan tezlik cheklovi.
- `Command` ga `expires_at` (default 5 daqiqa, sensor bo'yicha sozlanadi). Muddati o'tgan
  `pending` buyruq `pending_commands` da berilmaydi va `expired` ga o'tadi.
- `sent` uchun watchdog: `sent_at + timeout` dan keyin `failed` ga o'tadi, sensor bloki ochiladi;
  fon vazifasi (`monitoring/background.py`) da tekshiriladi.
- Partial unique indeks: `commands(sensor_id) WHERE status IN ('pending','sent')` — TOCTOU ni
  DB darajasida yopadi; `IntegrityError` → 409.

Fayllar: `server/ges_server/orm.py`, `monitoring/control.py`, `monitoring/background.py`,
migratsiya

Qabul mezoni:
- Diapazondan tashqari qiymat 400 beradi (test).
- Parallel ikki buyruq — biri 409 (test).
- Muddati o'tgan buyruq gateway ga berilmaydi (test).
- `sent` da qotgan buyruq watchdog dan keyin sensorni bloklamaydi (test).

Bog'liqlik: A2.

### B2 — Select-before-operate va readback

Muammo: buyruq bitta POST bilan yuboriladi. `ack` (`control.py:238`) gateway ning o'z so'zini
yozadi — PLC qiymatni qabul qilgani tekshirilmaydi.

Ish:
- Ikki bosqich: `POST /commands/select` → server qisqa muddatli `select_token` qaytaradi
  (qiymat, sensor, muddat bilan bog'langan); `POST /commands/execute` faqat shu token bilan.
  Token muddati (30 s) o'tsa bekor.
- `requires_dual_approval=true` sensorlar uchun: `execute` boshqa foydalanuvchining
  `POST /commands/{id}/approve` ini talab qiladi. Buyruq yaratuvchisi o'zini tasdiqlay olmaydi.
- Readback: buyruq bajarilgandan keyin gateway o'sha sensorning haqiqiy qiymatini o'qib
  `POST /commands/{id}/readback` ga yuboradi. Server kutilgan va haqiqiy qiymatni solishtiradi,
  farq bo'lsa `mismatch` holati va alarm.
- `pending_commands` ni GET dan POST `/commands/claim` ga o'zgartirish (holat o'zgartiradigan GET
  proksi qayta urinishida navbatni jimgina bo'shatadi — `control.py:195`).

Fayllar: `server/ges_server/monitoring/control.py`, `deploy/gateway/ges_gateway.py`, `orm.py`

Qabul mezoni:
- Token siz `execute` rad etiladi (test).
- Muallif o'z buyrug'ini tasdiqlay olmaydi (test).
- Readback farqi `mismatch` va alarm beradi (test).

Bog'liqlik: B1.

### B3 — Kalitlarni ajratish va default read-only

Muammo:
- Bitta statik `Project.ingest_key` ham telemetriyani, ham buyruq olish/ack ni avtorizatsiya
  qiladi. Kalit sizib chiqsa, hujumchi operator buyruqlarini yutib yuborishi yoki bajarilgan
  deb soxta ack qilishi mumkin.
- `deploy/gateway/ges_gateway.py:262` — `cfg.get("commands", True)`, ya'ni minimal konfiguratsiya
  bilan o'rnatgan odam ikki tomonlama boshqaruv kanalini oladi.
- Kalit `gateway_config.example.json` da ochiq matnda, muddati yo'q, rotatsiya qo'lda.

Ish:
- `Project` ga ikki kalit: `ingest_key` (faqat `POST /readings`) va `command_key`
  (`/commands/claim`, `/ack`, `/readback`). Alohida rotatsiya, alohida audit.
- Gateway da `commands` default `False`; yoqish uchun konfiguratsiyada aniq `true` va
  `command_key` bo'lishi shart.
- Kalitga `expires_at` va `last_used_at`; muddati yaqinlashganda adminlarga bildirishnoma.
- Gateway kaliti muhit o'zgaruvchisidan ham o'qilsin (fayl majburiy bo'lmasin).

Fayllar: `server/ges_server/orm.py`, `monitoring/router.py`, `monitoring/control.py`,
`deploy/gateway/ges_gateway.py`, `deploy/gateway/gateway_config.example.json`,
`deploy/gateway/README.md`, `docs/admin.md`

Qabul mezoni:
- Ingest kaliti bilan `/commands/claim` ga kirish 403 (test).
- `commands` yoqilmagan gateway buyruq so'ramaydi.

Bog'liqlik: A4 (audit), B1.

### B4 — Blokirovkalar (interlock)

Muammo: buyruqda texnologik blokirovka tushunchasi yo'q. Masalan, zatvorni ochish agregat
to'xtaganda yoki sath ma'lum chegaradan pastda bo'lsa taqiqlanishi kerak.

Ish:
- `Interlock` modeli: sensor (boshqariladigan), shart ifodasi (mavjud `sim/ges_sim/custom.py`
  dagi xavfsiz hisoblagich asosida, faqat sensor qiymatlari ustida), izoh, faol/nofaol.
- `create_command` va `execute` da barcha tegishli blokirovkalar baholanadi; bajarilmasa 409
  va sabab matni.
- Blokirovkani chetlab o'tish (`override`) faqat `approver` roli uchun, majburiy izoh bilan,
  alohida audit yozuvi va alarm.

Fayllar: `server/ges_server/orm.py`, `monitoring/control.py`, yangi `monitoring/interlock.py`
Qabul mezoni: blokirovka bajarilmaganda buyruq rad etiladi va sabab ko'rsatiladi (test).
Bog'liqlik: B1, A1 (sifat — `bad` sifatli sensor blokirovkani baholay olmaydi, u holda taqiq).

---

## C. Alarm tizimi (ISA-18.2)

### C1 — Ko'p bosqichli chegaralar va o'lik zona

Muammo: `orm.py:405` — sensorda faqat bitta `low_alarm` va bitta `high_alarm`.
`evaluate_alarm` (`live.py:60`) yalang'och taqqoslash: gisterezis yo'q, kechikish yo'q.
Chegarada turgan signal cheksiz chatter qiladi va har kesishishda `AlarmEvent` qatori yaratadi.

Ish:
- `Sensor` ga: `ll_alarm`, `l_alarm`, `h_alarm`, `hh_alarm`, `deadband`, `on_delay_s`,
  `off_delay_s`, `roc_limit_per_min` (o'zgarish tezligi alarmi).
- `evaluate_alarm` ni holat mashinasiga aylantirish: chegaradan chiqish `on_delay_s` davomida
  saqlanishi kerak; qaytish `deadband` va `off_delay_s` bilan.
- Deviatsiya alarmi: `twin.py` dagi kutilgan qiymatdan og'ish uchun alohida tur.
- Eski `low_alarm`/`high_alarm` ni `l_alarm`/`h_alarm` ga migratsiya qilish.

Fayllar: `server/ges_server/orm.py`, `monitoring/live.py`, migratsiya
Qabul mezoni: chegarada tebranayotgan signal bitta `AlarmEvent` yaratadi (test).
Bog'liqlik: A1, A2.

### C2 — Shelving, suppression, out-of-service

Muammo: ISA-18.2 ning asosiy holat mashinasi yo'q. Operatorning yagona harakati — ack.

Ish:
- `AlarmEvent` va `Sensor` ga holatlar: `normal`, `unack`, `acked`, `rtn_unack`, `shelved`,
  `suppressed_by_design`, `out_of_service`.
- Shelving: muddat bilan (default 8 soat, maksimum sozlanadi), sabab majburiy, avtomatik
  qaytish, audit yozuvi. Shelved alarm KPI da alohida hisoblanadi.
- Suppression-by-design: shart ifodasi (masalan, agregat to'xtaganda uning vibratsiya alarmi
  bostiriladi). B4 dagi ifoda mexanizmi qayta ishlatiladi.
- Out-of-service: texnik xizmat uchun, faqat `engineer`+ roli.

Fayllar: `server/ges_server/orm.py`, `monitoring/live.py`, `monitoring/router.py`
Qabul mezoni: shelved alarm muddat tugagach avtomatik qaytadi (test); har harakat auditda.
Bog'liqlik: C1.

### C3 — Ratsionalizatsiya maydonlari

Muammo: ISA-18.2 har alarmdan sabab, harakatsizlik oqibati, tuzatuvchi harakat, ruxsat etilgan
javob vaqti va ustuvorlik asosini talab qiladi. Bu maydonlar umuman yo'q.

Ish:
- `Sensor` (yoki alohida `AlarmDefinition`) ga: `cause`, `consequence`, `corrective_action`,
  `response_time_s`, `priority_basis`, `rationalized_by`, `rationalized_at`.
- Interfeysda alarm qatorini ochganda shu ma'lumot ko'rinadi (F bosqichida).
- Ratsionalizatsiya qilinmagan alarmlar ro'yxati (admin sahifasida).

Fayllar: `server/ges_server/orm.py`, `monitoring/router.py`
Qabul mezoni: ratsionalizatsiya qilinmagan alarmlar hisoboti mavjud.
Bog'liqlik: C1.

### C4 — Alarm toshqini aniqlash va EEMUA-191 KPI

Muammo: `historian.alarm_stats` faqat `{count, by_state, unacked}` qaytaradi. Toshqin aniqlash,
chattering indeksi, turg'un alarmlar, eng yomon 10 talik — hech biri hisoblanmaydi.

Ish:
- KPI hisoblovchi: 10 daqiqada alarm soni, o'rtacha soatlik yuk, turg'un alarmlar (24 soatdan
  ortiq faol), chattering indeksi (soatiga 3+ marta takrorlangan), ustuvorlik taqsimoti,
  eng yomon 10 ta manba, ack gacha o'rtacha vaqt.
- EEMUA-191 mezonlari bilan baho: 10 daqiqada 1 tadan kam — maqbul, daqiqada 1 tadan ko'p —
  qabul qilib bo'lmaydi; avariya boshlangan birinchi 10 daqiqada 10 tadan kam.
- Toshqin rejimi: qisqa vaqtda chegaradan ko'p alarm kelsa, tizim `flood` holatini belgilaydi
  va interfeysda ustuvorlik bo'yicha filtrlash taklif qilinadi.
- `GET /projects/{id}/alarms/kpi` endpoint.

Fayllar: `server/ges_server/monitoring/historian.py`, `monitoring/router.py`
Qabul mezoni: KPI endpoint EEMUA-191 mezonlariga nisbatan baho qaytaradi.
Bog'liqlik: C1, D1.

### C5 — Alarmga bog'liq nosozliklarni tuzatish

Muammo:
- `monitoring/router.py:845` — har WebSocket ulanishida `live.mark_stale(db, project_id)`
  chaqiriladi, u alarm yozadi va `announce()` → email fan-out qiladi (`live.py:212`, `:138`).
  Klient qayta ulanish sikliga tushsa — email bo'roni; har email cheksiz daemon thread yaratadi
  (`notify.py:51`).
- `monitoring/background.py:74` — kunlik hisobot `last_hour` xotira o'zgaruvchisiga tayanadi,
  u restartda `None` bo'ladi. Crash-loop da hisobot har restartda qayta yuboriladi.

Ish:
- `mark_stale` ni WebSocket ulanishidan ajratish; u faqat fon vazifasida ishlaydi.
- `last_hour` ni DB ga ko'chirish (`SystemState` yoki shunga o'xshash jadval).
- Email yuborishni cheklangan o'lchamli navbat + ishchi pul ga ko'chirish; alarm toshqinida
  jamlangan bitta xabar.

Fayllar: `server/ges_server/monitoring/router.py`, `monitoring/live.py`,
`monitoring/background.py`, `notify.py`
Qabul mezoni: 50 ta ketma-ket WebSocket ulanishi 0 ta email yuboradi (test).
Bog'liqlik: yo'q.

---

## D. Historian va masshtab

### D1 — Postgres + TimescaleDB ni ishlab chiqarish defaulti qilish

Muammo: `config.py:26` va `deploy/Dockerfile:21` — SQLite default. SCADA historian yozuv yuki
ostida bitta yozuvchili DB. Hozirgi dizayn realistik 10 soniyada bir necha yuz teg ko'taradi;
haqiqiy GES da 5000–50000 teg bo'ladi.

Ish:
- `deploy/docker-compose.yml` da Postgres+TimescaleDB ni asosiy profil qilish, SQLite faqat
  ishlab chiqish uchun.
- `readings` ni hypertable ga aylantirish (`ts` bo'yicha), `sensor_id` bo'yicha space partition.
- Ingest ni partiyali `COPY` ga o'tkazish (`live.py:176` hozir qator-qator INSERT).
- `live.ingest` har partiyada butun sensor jadvalini yuklaydi (`live.py:161`) — keshlangan
  sensor xaritasi (TTL bilan, o'zgarishda invalidatsiya).

Fayllar: `deploy/docker-compose.yml`, `deploy/Dockerfile`, `server/ges_server/config.py`,
`server/ges_server/db.py`, `monitoring/live.py`, migratsiya, `docs/admin.md`

Qabul mezoni: 10 000 qator/soniya ingest yuk testi o'tadi.
Bog'liqlik: A2.

### D2 — Ko'p qatlamli saqlash va siqish

Muammo: `historian.py` faqat soatlik agregat qiladi. Raw va soat orasida hech narsa yo'q, ya'ni
raw 90 kundan keyin o'chgach, avariyadan keyingi tahlil imkonsiz.

Ish:
- Qatlamlar: raw → 1 daqiqa → 10 daqiqa → 1 soat. Har birining alohida saqlash muddati.
- O'lik zonali siqish (swinging door yoki oddiy deadband) — raw yozishda sensor bo'yicha
  `archive_deadband` dan kichik o'zgarish yozilmaydi (lekin vaqt chegarasi bilan majburiy yozuv).
- Agregatni SQL `GROUP BY` ga ko'chirish. Hozir `historian.py:30` har sensor uchun 2-3 so'rov
  qiladi va Python da agregat qiladi; birinchi rollup butun tarixni RAM ga yuklaydi (`:35`).
- `purge` (`historian.py:73`) ni partiyali qilish.
- Muhim hodisa atrofida raw ni saqlab qolish (`AlarmEvent` dan ±1 soat o'chirilmaydi).

Fayllar: `server/ges_server/monitoring/historian.py`, `orm.py`, migratsiya
Qabul mezoni: 1 mln qatorli sensorda rollup xotirani bosmaydi (test); qatlamlar hisobotda
ishlatiladi.
Bog'liqlik: D1.

### D3 — SOE (hodisalar ketma-ketligi)

Muammo: hodisalar faqat analog tegdan olingan alarm sifatida mavjud. Agregat trip bo'lganda
sabab-oqibatni ajratish uchun millisekundli SOE kerak, u alohida yo'l bilan keladi va
agregatlanmaydi.

Ish:
- `SequenceEvent` modeli: `(project_id, source, point, state, ts_ms, quality, raw)`.
- `POST /projects/{id}/soe` — command key emas, ingest key bilan; partiyali.
- Hech qachon rollup qilinmaydi, alohida saqlash muddati (uzoqroq).
- SOE ko'rish interfeysi: vaqt bo'yicha saralangan, filtrli, alarm jurnali bilan birlashtirilgan
  ko'rinish (F5).
- Simulyator SOE generatsiya qiladi (E4).

Fayllar: `server/ges_server/orm.py`, `monitoring/router.py`, yangi `monitoring/soe.py`
Qabul mezoni: 1 ms aniqlikdagi hodisalar tartibi saqlanadi va ko'rinadi.
Bog'liqlik: A2, D1.

### D4 — Sahifalash va N+1 so'rovlarni tuzatish

Muammo:
- `projects/router.py:63` — har loyiha uchun `get_project_role` (bitta so'rov) va
  `project.models` lazy-load (`len()` uchun) — loyihaga 2 qo'shimcha so'rov.
- `auth/router.py:78` (`list_users`), `projects/router.py:134` (`list_members`),
  `monitoring/router.py:116` (`list_sensors`) — limit/offset umuman yo'q.
- `list_commands`/`list_journal` da kursor yo'q, izchil sahifalash imkonsiz.
- `historian.sensor_stats` (`:124`) va `/sensors/{id}/readings` (`monitoring/router.py:454`)
  butun diapazonni xotiraga yuklab, Python da siyraklashtiradi.

Ish:
- Barcha ro'yxat endpointlariga kursorli sahifalash (`limit` + `after_id`/`after_ts`).
- N+1 larni `selectinload` va agregat so'rov bilan almashtirish.
- Siyraklashtirishni DB tomonga (`time_bucket`) ko'chirish.

Fayllar: `server/ges_server/projects/router.py`, `auth/router.py`, `monitoring/router.py`,
`monitoring/historian.py`, `web/src/api/client.ts`
Qabul mezoni: 1000 loyihali hisobda `list_projects` so'rovlar soni doimiy (test).
Bog'liqlik: D1.

---

## E. Gateway, protokollar va simulyator

Haqiqiy SCADA hozir yo'q, shuning uchun bu bosqich simulyator ustida quriladi va protokol
klientlari simulyator bilan sinaladi.

### E1 — Gateway da diskka yoziladigan store-and-forward

Muammo: `deploy/gateway/ges_gateway.py` — `Pusher.buffer` xotiradagi Python ro'yxati, 50 000 da
eng eskisini jimgina kesadi. Jarayon restart bo'lsa hammasi yo'qoladi.

Ish:
- Buferni lokal SQLite spool ga ko'chirish (`(ts, payload, attempts)`).
- Yuborilgach o'chiriladi; muvaffaqiyatsizlikda eksponensial kechikish bilan qayta urinish.
- Spool hajmi va eng eski yozuv yoshi — diagnostika tegi sifatida serverga yuboriladi.
- To'lib ketganda: eng eskisini o'chirish o'rniga ogohlantirish va yozuvni to'xtatish varianti
  (konfiguratsiyada).

Fayllar: `deploy/gateway/ges_gateway.py`, `deploy/gateway/README.md`
Qabul mezoni: gateway restartidan keyin yuborilmagan o'lchovlar yo'qolmaydi (test).
Bog'liqlik: yo'q.

### E2 — Sifat va manbadagi vaqt tamg'asini gateway da to'ldirish

Muammo: Modbus va OPC UA o'qishlari vaqt tamg'asi bermaydi; OPC UA `StatusCode` o'qilmaydi
(`ges_gateway.py` `OpcUaSource` faqat `node.read_value()`).

Ish:
- OPC UA da `read_data_value()` ga o'tish: `SourceTimestamp`, `ServerTimestamp`, `StatusCode`
  olinadi. `StatusCode` → `quality` xaritasi (Good/Uncertain/Bad).
- Modbus da o'qish paytidagi lokal vaqt `src_ts` sifatida (poll siklidan keyin emas);
  o'qish xatosi → `quality=bad`.
- Aloqa uzilganda: oxirgi qiymatni takrorlamaslik, `quality=bad` bilan bitta yozuv.
- Gateway hostida NTP tekshiruvi: soat farqi diagnostika tegi sifatida
  (`GW.clock_offset_s`), chegaradan oshsa alarm.

Fayllar: `deploy/gateway/ges_gateway.py`
Qabul mezoni: OPC UA dan kelgan `Bad` StatusCode serverda `quality=bad` bo'lib saqlanadi (test).
Bog'liqlik: A1.

### E3 — OPC UA obuna rejimi

Muammo: hozir sinxron polling. Obuna (MonitoredItems) yo'q, ya'ni o'zgarishga reaksiya poll
davriga bog'liq va tarmoq yuki keraksiz katta.

Ish:
- `OpcUaSource` ga obuna rejimi: `create_subscription` + `subscribe_data_change`,
  `publishing_interval`, `deadband`.
- Polling rejimi fallback sifatida qoladi (konfiguratsiyada tanlanadi).
- Qayta ulanish: obunani tiklash, uzilish davrida `quality=bad`.

Fayllar: `deploy/gateway/ges_gateway.py`
Qabul mezoni: obuna rejimida qiymat o'zgarishi poll davridan tez keladi (simulyator testi).
Bog'liqlik: E2.

### E4 — GES simulyatori (sinov stendi)

Muammo: `ges_gateway.py` dagi `SimSource` — sinus + shovqin. U bilan alarm mantig'ini, toshqinni,
sifat bayrog'ini, SOE ni yoki egizakni sinab bo'lmaydi.

Ish: alohida `deploy/simulator/` xizmati — haqiqiy stansiyaga o'xshash dinamik model:
- Mavjud `sim/ges_sim` modullaridan foydalanadi (ombor balansi, turbina, regulyator) —
  ikkinchi fizika dvigateli yozilmaydi.
- Modbus TCP server va OPC UA server sifatida ishlaydi (gateway haqiqiy protokol bilan ulanadi).
- Stsenariylar: normal ish, yuk tashlash, agregat trip, zatvor nosozligi, toshqin, aloqa uzilishi,
  sensor qotishi, shovqinli sensor, chatter qiluvchi chegara.
- Sifat bayrog'ini ataylab buzish (Bad/Uncertain) — A1 ni sinash uchun.
- SOE hodisalarini millisekundli tamg'a bilan generatsiya qilish (D3).
- Yozib olingan stsenariyni qayta ijro etish (operator mashqi uchun, F8).

Fayllar: yangi `deploy/simulator/`, `deploy/docker-compose.yml`
Qabul mezoni: har stsenariy e2e testda ishga tushadi va kutilgan alarm ketma-ketligini beradi.
Bog'liqlik: A1, C1, D3.

### E5 — IEC 60870-5-104 klienti

Muammo: mintaqadagi dispetcher markazlari va RTU lar aynan shu protokolda gapiradi; hozir
umuman yo'q.

Ish:
- Gateway ga `Iec104Source`: `c104` (lib60870 ustida) kutubxonasi bilan.
- ASDU turlari: M_ME_NC_1 (float), M_SP_NA_1 (bitta bit), M_DP_NA_1, M_ME_NB_1 (skalyar),
  vaqt tamg'ali variantlari (M_ME_TF_1, M_SP_TB_1) — SOE uchun.
- Quality descriptor bitlari (IV, NT, SB, BL) → `quality` xaritasi.
- Interrogation (umumiy so'rov) ulanishda va davriy.
- Simulyator tomonda 104 server — sinov uchun.
- Boshqaruv (C_SE_NC_1 setpoint) — alohida, B bosqichi qoidalariga bo'ysunadi, default o'chiq.

Fayllar: `deploy/gateway/ges_gateway.py`, `deploy/simulator/`, `deploy/gateway/README.md`
Qabul mezoni: simulyatordagi 104 serverdan vaqt tamg'ali o'lchov va SOE olinadi (test).
Bog'liqlik: E1, E2, E4.

### E6 — MQTT ko'prigini mustahkamlash

Muammo (`server/ges_server/monitoring/mqtt_bridge.py`):
- `GES_MQTT_URL=mqtt://user:pass@host:1883` — parol muhit o'zgaruvchisida va loglanadigan URL da;
  ochiq matnli `mqtt://` hujjatlashtirilgan default.
- TLS faqat `mqtts` uchun, yalang'och `client.tls_set()` (`:81`) — CA pinning yo'q, klient
  sertifikati yo'q.
- `_on_message` (`:58`) har xabar uchun yangi DB sessiyasi ochadi; `live.ingest` har xabarda
  butun sensor jadvalini qayta o'qiydi.
- `on_disconnect` ishlovchisi yo'q; obunalar faqat ulanishda yangilanadi.
- Topic → sensor xaritasi shartsiz ishoniladi.

Ish:
- Parolni alohida maydon/sirdan olish, URL da qoldirmaslik.
- `mqtts` va klient sertifikati (mTLS) ni qo'llab-quvvatlash, CA ko'rsatish majburiy.
- Xabarlarni partiyalash (buferlab, vaqt yoki hajm bo'yicha flush).
- `on_disconnect` + qayta obuna; uzilish davrida tegishli sensorlarga `quality=bad`.
- Topic bo'yicha ruxsat: qaysi klient qaysi topikka yozishi mumkinligi konfiguratsiyada.

Fayllar: `server/ges_server/monitoring/mqtt_bridge.py`, `config.py`, `deploy/.env.example`
Qabul mezoni: TLS siz `mqtt://` ishlab chiqarish rejimida ogohlantirish beradi yoki rad etiladi.
Bog'liqlik: A1.

---

## F. Interfeys — ikki rejim

Qaror: dispetcher sahifalari ISA-101 bo'yicha qayta yoziladi; model va muhandislik sahifalari
hozirgi Blender uslubida qoladi. Ikkalasi bitta dizayn tokenlari to'plamidan rang oladi.

### F1 — Yagona dizayn tokenlari va rejim almashtirish

Muammo:
- `Mimic.tsx:7` da `low → var(--warn)` (sariq), `MonitoringPanel.tsx:30` da `low → "#e0656a"`
  (qizil, `high` bilan bir xil). Bir xil holat ikki sahifada ikki xil rang.
- Ustuvorlik (`Sensor.priority`) rangga umuman ta'sir qilmaydi — past va kritik bir xil qizil.
- Kontrast: `--danger #d95c5c` panel ustida 3.54:1 (matn uchun 4.5:1 kerak), 3D kanvas ustida
  2.92:1 (matnsiz element uchun ham 3:1 dan past). `--text-dim` 2.59:1. Faol alarm qatori
  `#3a2426` vs `#303030` — 1.09:1, amalda ko'rinmaydi.

Ish:
- `web/src/ui/tokens.ts` — yagona manba: alarm holati × ustuvorlik → rang, shakl, ikonka, matn
  kodi. Rang yagona kanal bo'lmasligi kerak (ISA-101 va rang ko'rishi buzilgan operatorlar uchun).
- Ikki tema: `engineer` (hozirgi qora Blender uslubi) va `operator` (ISA-101: neytral kulrang
  asos, past to'yinganlik, rang faqat anomaliya uchun).
- Tema tanlovi foydalanuvchi sozlamasida saqlanadi; dispetcher sahifalari default `operator`.
- Barcha kontrastlar WCAG AA (matn 4.5:1, grafik 3:1) — avtomatik tekshiruvchi test.

Fayllar: yangi `web/src/ui/tokens.ts`, `web/src/ui/theme.css`,
`web/src/pages/dashboard/Mimic.tsx`, `web/src/pages/model/MonitoringPanel.tsx`
Qabul mezoni: rang qiymatlari faqat tokenlardan keladi (lint qoidasi yoki test); kontrast testi
o'tadi.
Bog'liqlik: C1.

### F2 — Ekranlar ierarxiyasi (ISA-101 Level 1–4)

Muammo: hozir bitta qo'lda chizilgan SVG mimika (`Mimic.tsx`) — taxminan bitta Level 2 ekran.
Level 1 umumiy ko'rinish, Level 3 faceplate lar, Level 4 diagnostika yo'q; navigatsiya modeli yo'q.

Ish:
- Level 1 — stansiya umumiy ko'rinishi: bitta ekranda barcha agregatlar, ombor, tashlama,
  chiqish quvvati, faol alarmlar soni ustuvorlik bo'yicha. Operator bir qarashda normal/anomaliya
  ni ajratishi kerak.
- Level 2 — texnologik uchastka: gidrotexnik qism, mashina zali, elektr qismi (alohida ekranlar).
- Level 3 — faceplate: agregat, transformator, zatvor uchun. Ichida: joriy qiymatlar, chegaralar,
  trend sparkline, boshqaruv (ruxsat bo'lsa), alarm ratsionalizatsiyasi (C3), bog'liq ish
  buyruqlari.
- Level 4 — diagnostika: sensor xom qiymati, sifat tarixi, aloqa holati, gateway diagnostikasi.
- Navigatsiya: har darajadan pastga o'tish, "ota" ekranga qaytish, tezkor tugmalar.

Fayllar: yangi `web/src/pages/operator/` (L1Overview, L2Area, L3Faceplate, L4Diagnostics),
`web/src/App.tsx`
Qabul mezoni: har darajadan boshqasiga o'tish yo'li bor; e2e testda Level 1 → faceplate yo'li
sinaladi.
Bog'liqlik: F1.

### F3 — Mimikani konfiguratsiyalanadigan qilish

Muammo: `Mimic.tsx:10` — `POS` 12 ta qat'iy piksel koordinatasi, uchta generator qat'iy kodlangan
(`:16-18`, `:57`). Ikki yoki olti agregatli stansiyani chizib bo'lmaydi. `:90` bog'lanmagan
slotlarni yashiradi — texnologik sxemaning bir qismi jimgina yo'qoladi.

Ish:
- Mimika sxemasi ma'lumot sifatida (JSON): elementlar, koordinatalar, turlar, sensor bog'lanishi.
- Agregatlar soni loyiha konfiguratsiyasidan.
- Muharrir: elementni surish, sensor bog'lash, saqlash (admin/engineer).
- Bog'lanmagan element yashirilmaydi — "ma'lumot yo'q" holatida ko'rsatiladi.
- Yetishmayotgan elementlar: vikluchatel/shina holati, zatvor ochilish grafikasi, ventil
  belgilari, generator uzgich.

Fayllar: `web/src/pages/dashboard/Mimic.tsx` → `web/src/pages/operator/Mimic.tsx`,
server tomonda sxema saqlash
Qabul mezoni: 2 va 6 agregatli konfiguratsiyalar to'g'ri chiziladi (test).
Bog'liqlik: F1, F2.

### F4 — Sifat, eskirish va aloqa holatini to'g'ri ko'rsatish

Muammo:
- `client.ts:233` — `AlarmState` sifat va alarm holatini bitta enum ga qo'shgan. Yuqori alarmdagi
  sensor aloqani yo'qotsa `stale` bo'ladi va faol alarm butunlay yashirinadi.
- `Mimic.tsx:96` — eskirgan qiymat `--text-dim` bilan, kontrast 2.59:1, 12px. Oxirgi ma'lum
  qiymat o'sha joyda, o'sha qutida qoladi — klassik "muzlagan qiymat" xavfi.
- `useLive.ts:16` va uning nusxasi `MonitoringPanel.tsx:61` — heartbeat yo'q. Yarim ochiq TCP da
  `onclose` ishlamaydi, `DashboardPage.tsx:202` yashil "JONLI" belgisini ko'rsatishda davom etadi.

Ish:
- Sifatni alarm holatidan ajratish: har qiymat `{value, quality, alarm_state, age_s}`.
- Sifat ko'rsatilishi: shtrix naqsh yoki `?` belgisi + vaqt tamg'asi, faqat rang emas.
- Klient tomonda heartbeat: server davriy ping yuboradi; xabar yoshi chegaradan oshsa holat
  `LIVE` → `STALE` → `OFFLINE`. Har uchtasi vizual jihatdan aniq farq qiladi.
- `useLive` va `MonitoringPanel` dagi nusxa kodni bitta hook ga birlashtirish.
- Qayta ulanish: eksponensial kechikish + jitter + chegara; 401/403 yopilishida takrorlamaslik
  (hozir `useLive.ts:32` da qat'iy 3 soniya, cheksiz — server o'lganda barcha ekranlar bir vaqtda
  uradi).

Fayllar: `web/src/hooks/useLive.ts`, `web/src/pages/model/MonitoringPanel.tsx`,
`web/src/pages/dashboard/*`, `web/src/api/client.ts`, server tomonda WebSocket ping
Qabul mezoni: WebSocket jimgina uzilganda 30 soniya ichida `OFFLINE` ko'rinadi (test).
Bog'liqlik: A1, F1.

### F5 — Alarm sahifasi

Muammo: alarm ro'yxati kelish tartibida (`DashboardPage.tsx:104`), ustuvorlik bo'yicha
saralanmaydi. Ack `prompt()` bilan (`:172`) — asosiy oqimni bloklaydi. "Hammasini kvitlash"
(`:236`) tasdiqlashsiz. `setFlash` (`:112`) shartsiz almashtiradi — toshqinda faqat oxirgisi
ko'rinadi. `:235` tarixni yuklaganda `events` ni butunlay almashtiradi, lekin `:156` faol alarm
hisoblagichlari o'sha massivdan hisoblanadi — tarix rejimida dispetcherning faol alarm soni
jimgina tarixiy songa aylanadi.

Ish:
- Alohida alarm sahifasi: saralash (ustuvorlik → vaqt), filtr (ustuvorlik, uchastka, holat),
  guruhlash, qidiruv.
- Ack — `Dialog` bilan (loyihada allaqachon bor: `ui/Dialog.tsx`), `prompt()` emas.
- "Hammasini kvitlash" — tasdiqlash dialogi, nechta alarm ack qilinishi ko'rsatiladi,
  faqat filtrlangan to'plam uchun.
- Toshqin rejimi (C4): ustuvorlik bo'yicha avtomatik filtr taklifi.
- Shelving, suppression, out-of-service boshqaruvi (C2) shu sahifada.
- Ratsionalizatsiya ma'lumoti (C3) qator ochilganda.
- Faol alarm hisoblagichlari tarix ko'rinishidan mustaqil holatda.

Fayllar: yangi `web/src/pages/operator/Alarms.tsx`, `web/src/pages/DashboardPage.tsx`
Qabul mezoni: 200 ta alarm toshqinida sahifa ishlaydi va kritiklar birinchi turadi (test).
Bog'liqlik: C1, C2, C3, C4, F1.

### F6 — Ovozli signal (annunciator)

Muammo: `DashboardPage.tsx:37` — har alarmda yangi `AudioContext`. Chrome hujjatga ~6 tadan
ortiq `AudioContext` ga ruxsat bermaydi; undan keyin konstruktor xato tashlaydi va u
`catch { }` (`:48`) da yutiladi. Ya'ni ovozli signal aynan alarm toshqinida jim bo'ladi.
`ctx.state === "suspended"` tekshiruvi yo'q — foydalanuvchi harakati bo'lmagan kiosk ekranda
ovoz umuman chiqmaydi va buni hech narsa bildirmaydi.

Ish:
- Bitta doimiy `AudioContext`, ilova ishga tushganda yaratiladi.
- `suspended` holatini aniqlash va interfeysda "ovoz o'chiq — bosing" ko'rsatkichi.
- Annunciator sog'ligi ko'rsatkichi (ishlayapti / bloklangan / o'chirilgan).
- Ustuvorlik bo'yicha turli signal; kritik uchun takrorlanuvchi, ack gacha.
- Signalni vaqtincha o'chirish (silence) — muddat bilan, auditga yoziladi.

Fayllar: yangi `web/src/ui/annunciator.ts`, `web/src/pages/operator/*`
Qabul mezoni: 20 ta ketma-ket alarmda ovoz ishlashda davom etadi (test).
Bog'liqlik: F1.

### F7 — Trend server

Muammo: `LineChart.tsx:35` — barcha seriyalar uchun bitta Y o'qi. `DashboardPage.tsx:266`
operatorga 5 ta istalgan sensorni tanlashga ruxsat beradi, `:273` esa `unit=""` uzatadi. Ombor
sathi (~900 m) va quvvat (~50 MW) birga chizilsa, quvvat pastda tekis chiziqqa aylanadi.
Zoom va pan yo'q. `:62` `ResizeObserver` siz — oyna o'lchami o'zgarsa grafik moslashmaydi.
`:105` uzunlik tekshiruvisiz `s.values[idx]` — seriyalar uzunligi farq qilsa `NaN` aylana chiqadi.
`DashboardPage.tsx:191` — har nuqta uchun chiziqli qidiruv, har seriya uchun; `useMemo` bog'liqligida
`sensors` bor, u esa har xabarda yangi massiv bo'ladi — to'liq qayta hisoblash sensor yangilanish
tezligida ishlaydi.

Ish:
- Ko'p o'qli grafik: har birlik uchun alohida o'q yoki normallashtirilgan rejim.
- Zoom, pan, kursor bilan qiymat o'qish, ikki kursor orasidagi farq.
- Pen guruhlari: saqlanadigan to'plamlar, nom bilan.
- Sifat ko'rsatilishi grafikada (bad nuqtalar uzilish sifatida, jim interpolyatsiya emas).
- Ma'lumotni serverdan siyraklashtirilgan holda olish (D4), klientda qayta hisoblamaslik.
- `ResizeObserver`, uzunlik qo'riqchisi.

Fayllar: `web/src/ui/LineChart.tsx` → yangi `web/src/ui/Trend.tsx`,
`web/src/pages/operator/Trends.tsx`
Qabul mezoni: turli birlikdagi 5 seriya o'qilarli ko'rinadi; 10 000 nuqtada interfeys qotmaydi.
Bog'liqlik: D2, D4, F1.

### F8 — Boshqaruv interfeysi

Muammo: `TwinPanels.tsx:124` va `MonitoringPanel.tsx:272` — `confirm()` bilan tasdiqlash.
Kiritish `type="number" step="any"` (`TwinPanels.tsx:122`), sensordan min/max olinmaydi —
zatvor uchun 5000 % yoki manfiy qiymat qabul qilinadi. Qayta autentifikatsiya yo'q, select
muddati yo'q, `acked` holati tekshirilmaydi; muvaffaqiyat `setError` orqali, ya'ni xato kanali
bilan xabar qilinadi.

Ish:
- Faceplate ichida boshqaruv bloki: joriy qiymat, ruxsat etilgan diapazon, kiritish
  validatsiyasi (B1 chegaralari), sabab maydoni.
- Select → Execute ikki bosqichi (B2), qolgan vaqt taymeri bilan.
- Ikkinchi kishi tasdig'i kerak bo'lsa — kutish holati va bildirishnoma.
- Blokirovkalar (B4) natijasi oldindan ko'rsatiladi: qaysi shart bajarilmayapti.
- Buyruq holati kuzatiladi: pending → sent → acked → readback tasdig'i yoki mismatch.
- `confirm()`/`prompt()`/`alert()` — butun ilovada 24 joyda ishlatilgan; hammasini `Dialog` ga
  ko'chirish.

Fayllar: `web/src/pages/operator/L3Faceplate.tsx`, `web/src/pages/dashboard/TwinPanels.tsx`,
`web/src/pages/model/MonitoringPanel.tsx`, `web/src/ui/Dialog.tsx`
Qabul mezoni: diapazondan tashqari qiymat klientda ham, serverda ham rad etiladi (test).
Bog'liqlik: B1, B2, B4, F2.

### F9 — Smena jurnali va navbat topshirish

Muammo: `JournalEntry` faqat erkin matn. Tuzilgan topshirish ro'yxati, ikki tomonlama imzo yo'q.

Ish:
- Tuzilgan topshirish: faol alarmlar, ochiq ish buyruqlari, blokirovka chetlab o'tishlari,
  o'chirilgan/shelved nuqtalar, kutilayotgan buyruqlar — avtomatik to'ldiriladi.
- Topshiruvchi va qabul qiluvchining imzosi (audit yozuvi bilan).
- Smena davomidagi hodisalar tasmasi (alarm, buyruq, izoh, SOE) bitta xronologiyada.

Fayllar: `server/ges_server/monitoring/router.py`, yangi `web/src/pages/operator/Shift.tsx`
Qabul mezoni: topshirish yakunlanmasa ogohlantiriladi; imzolar auditda.
Bog'liqlik: C2, D3, F2.

### F10 — Front-end sifat infratuzilmasi

Muammo:
- `grep -c eslint-disable src/` = 39, deyarli hammasi `react-hooks/exhaustive-deps`
  (`ModelPage.tsx:99,105,106,115,123,125,170,279,354,492` va boshqalar). ESLint umuman
  o'rnatilmagan, konfiguratsiya yo'q, CI da lint qadami yo'q. Ya'ni bostirilgan qoida hech
  qachon ishlamagan.
- `tsconfig.json` da `noUnusedLocals`, `noUnusedParameters`, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes` yo'q.
- Bitta 7.5 MB JS to'plami, kod bo'linishi yo'q: `App.tsx:4-10` barcha yettita sahifani statik
  import qiladi, shuning uchun login ekrani Three.js, ThatOpen va web-ifc ni yuklaydi.
  `vite.config.ts:10` `chunkSizeWarningLimit: 4000` — ogohlantirishni ko'taradi, muammoni emas.
- Unit testlar 13 ta, ikkita toza mantiq moduli ustida. `Mimic`, `LineChart`, alarm ack,
  `useLive`, `MonitoringPanel`, `Viewer`, `api/client` — hech biri sinalmagan.
  `@testing-library/react` bog'liqliklarda yo'q.

Ish:
- ESLint + `eslint-plugin-react-hooks` o'rnatish, CI ga lint qadami, 39 ta bostirishni
  o'chirish (qoidani emas — muammolarni tuzatish).
- `tsconfig` ni qattiqlashtirish.
- `React.lazy` + `Suspense` sahifa darajasida; `manualChunks` bilan three/thatopen alohida.
- `@testing-library/react` va alarm mantig'i, `useLive` qayta ulanishi, sifat ko'rsatilishi
  uchun testlar.

Fayllar: `web/package.json`, `web/eslint.config.js`, `web/tsconfig.json`, `web/vite.config.ts`,
`web/src/App.tsx`, `.github/workflows/ci.yml`
Qabul mezoni: lint CI da o'tadi, bostirish qolmaydi; login sahifasi to'plami 500 KB dan kichik.
Bog'liqlik: yo'q.

### F11 — 3D viewer nosozliklari

Muammo:
- `Viewer.ts:206,207,234,242` — `keydown`, `keyup`, `pointermove`, `pointerup` anonim
  funksiyalar `window` ga bog'lanadi va `this` ni ushlab turadi. `dispose()` (`:1872`) ularning
  birortasini ham olib tashlamaydi. Har `ModelPage` ochilishida bitta `Viewer`, uning sahnasi,
  fragment modeli va GPU buferlari xotirada qoladi. `main.tsx:8` dagi `StrictMode` buni
  ishlab chiqishda ikkilantiradi. To'g'ri namuna `drafts.ts:72-79` da bor.
- `MonitoringPanel.tsx:102` — `view` memoizatsiya qilinmagan, har renderda yangi massiv.
  U uchta effektning bog'liqligi (`:124`, `:136`, `:151`), shuning uchun har WebSocket xabarida
  `colorByGuids` ishga tushadi. `Viewer.ts:1530` esa `resetHighlight()` chaqiradi, u
  `"select"` qatlamini ham tozalaydi — operatorning 3D tanlovi har qiymat kelganda yo'qoladi.
- `Viewer.ts:1544` (`clearModel`) — jonli bog'lanish obyektlari sahnadan olinadi, lekin
  `geometry.dispose()`/`material.dispose()` chaqirilmaydi (`dropLive` (`:1465`) da to'g'ri
  qilingan). Har versiya almashtirishda GPU xotirasi oqadi.

Ish:
- Listenerlarni `this` da saqlash va `dispose()` da olib tashlash.
- `view` ni `useMemo` ga olish; `colorByGuids` faqat o'z qatlamini tozalaydi.
- `clearModel` da resurslarni bo'shatish.
- Xotira oqishini aniqlaydigan test (N marta mount/unmount dan keyin listener soni doimiy).

Fayllar: `web/src/viewer/Viewer.ts`, `web/src/pages/model/MonitoringPanel.tsx`
Qabul mezoni: 20 marta model ochib-yopishdan keyin listener soni o'smaydi (test).
Bog'liqlik: yo'q.

### F12 — Xatolar chegarasi va uzilish holati

Muammo: `ErrorBoundary` butun kod bazasida yo'q. `Mimic`, `LineChart` yoki biror paneldagi
render xatosi butun dispetcher sahifasini oq ekranga aylantiradi. `DashboardPage.tsx:197`
butun sahifani `!project || !dash` ga bog'laydi — `/dashboard` so'rovi yiqilsa, operator jonli
WebSocket ma'lumoti hali kelib turganiga qaramay faqat xato matnini ko'radi.
`navigator.onLine` ishlovchisi yo'q. To'rtta panel (`TwinPanels.tsx:18`, `HealthPanels.tsx:18`
va sim panellari) `document.hidden` ni tekshirmaydi va xatoda orqaga chekinmaydi.

Ish:
- Har panel atrofida `ErrorBoundary`; bitta panel yiqilsa qolgani ishlaydi.
- Qisman ishlash: `/dashboard` yiqilsa ham jonli ma'lumot ko'rsatiladi.
- Offline holati ko'rsatkichi.
- Pollinglar `document.hidden` da to'xtaydi va xatoda eksponensial orqaga chekinadi.

Fayllar: yangi `web/src/ui/ErrorBoundary.tsx`, `web/src/pages/**`
Qabul mezoni: bitta panel ataylab xato tashlaganda qolgan sahifa ishlaydi (test).
Bog'liqlik: yo'q.

---

## G. BIM tomoni

### G1 — IFC4.3 ga o'tish

Muammo: `models/drafts.py:44` va `docs/samples/make_sample_ges.py:66` — `version="IFC4"` qat'iy
kodlangan; testlar `meta["schema"] == "IFC4"` ni tekshiradi. IFC4 da infratuzilma entitylari yo'q,
shuning uchun to'g'on, suv qabul qilgich, suv tashlagich va quyi byef tessellatsiya qilingan mesh
sifatida, `Pset_GES_*` xususiyatlari bilan eksport qilinadi. Bu — IFC kengaytmasi kiygan xususiy
semantika; boshqa hech bir dastur suv tashlagichni tushunmaydi.

Ish:
- IFC4.3 (ISO 16739-1:2024) ni qo'llab-quvvatlash; sxema versiyasi konfiguratsiyadan.
- GES obyektlarini IFC4.3 entitylariga xaritalash: `IfcFacility`/`IfcFacilityPart`,
  `IfcEarthworksFill`, `IfcAlignment` (kanal va yo'l uchun), `IfcDistributionFlowElement`
  (quvur, zatvor), `IfcGeographicElement`.
- Xaritalanmaydigan obyektlar uchun `Pset_GES_*` saqlanib qoladi, lekin sxema turi to'g'ri.
- Migratsiya: mavjud IFC4 modellar o'qilishda davom etadi.
- `fc_engine.ifc_class()` (`desktop/blender/sath/fc_engine.py:126`) — hozir
  `"Ifc" + type.replace(" ", "")` satr birikmasi, validatsiya yo'q. Sxemadagi sinflar ro'yxatiga
  nisbatan tekshiriladigan qilish.

Fayllar: `server/ges_server/models/drafts.py`, `models/ifc_meta.py`,
`desktop/blender/sath/ifc.py`, `fc_engine.py`, `docs/samples/make_sample_ges.py`
Qabul mezoni: IFC4.3 model yuklanadi, tur xaritalash testi o'tadi, noto'g'ri sinf nomi xato beradi.
Bog'liqlik: yo'q. Bu sezilarli ish — alohida loyiha sifatida rejalashtirilsin.

### G2 — IDS validatsiya

Muammo: model tekshiruvi spetsifikatsiyasi yo'q. "Soddalashtirilgan ISO 19650" da'vosi
tekshirilmaydigan.

Ish:
- `docs/ids/sath-ges.ids` — Sath GES modeli nimani o'z ichiga olishi kerakligi: majburiy
  `Pset_GES_*` maydonlari, georeferensiya mavjudligi, klassifikatsiya, nomlash qoidalari.
- Har yuklashda `ifctester` bilan tekshirish; natija versiyaga biriktiriladi.
- Tasdiqlash so'rovida (change request) IDS natijasi ko'rsatiladi; yiqilgan bo'lsa tasdiqlash
  bloklanadi (sozlanadigan).
- Web da natija ko'rinishi: qaysi element, qaysi talab bajarilmadi.

Fayllar: yangi `docs/ids/`, `server/ges_server/models/` da validator, `review/router.py`,
`web/src/pages/model/ChecksPanel.tsx`
Qabul mezoni: majburiy maydonsiz model IDS tekshiruvidan o'tmaydi (test).
Bog'liqlik: yo'q. Eng arzon va eng ishonchli BIM yutug'i.

### G3 — Georeferensiya

Muammo: `IfcMapConversion`, `IfcProjectedCRS`, EPSG — kod bazasida umuman yo'q.
`models/dem.py` lat/lon markazdan AWS relief plitalarini oladi va lokal mesh quradi, lekin
lat/lon loyiha CRS sifatida saqlanmaydi. O'zbekiston uchun Pulkovo 1942 / Gauss-Krüger zonalari
yoki UTM 41N/42N kerak. Georeferensiyasiz toshqin chegaralari, geodeziya bilan solishtirish va
GIS ga uzatish ishonchsiz.

Ish:
- `Project` ga `epsg_code`, `origin_e`, `origin_n`, `origin_h`, `rotation`.
- Model yaratish va yuklashda `IfcProjectedCRS` + `IfcMapConversion` yozish; mavjud modellarga
  qo'shish imkoni.
- Yuklashda tekshirish: CRS yo'q bo'lsa ogohlantirish (IDS talabi sifatida).
- DEM importini loyiha CRS siga qayta proyeksiyalash.
- Web da koordinatalarni ham lokal, ham global ko'rsatish.

Fayllar: `server/ges_server/orm.py`, `models/drafts.py`, `models/dem.py`, `models/ifc_meta.py`,
`web/src/pages/model/PropertiesPanel.tsx`
Qabul mezoni: model ichidagi nuqta global koordinatada to'g'ri chiqadi (ma'lum nuqta bilan test).
Bog'liqlik: G2 (IDS talabi sifatida kiritiladi).

### G4 — ISO 19650 to'liqroq muvofiqlik

Muammo: to'rtta holat (`VersionState`) to'g'ri xaritalanган, tasdiqlash oqimi va audit haqiqiy.
Lekin yo'q: yaroqlilik kodlari (S0–S7, A1–AN, B1–BN, CR, PR), reviziya kodlari (P01/C01),
konteyner nomlash konvensiyasi, EIR/BEP, TIDP/MIDP, buyurtmachi/ijrochi tuzilmasi.
Hozir `Version.tag: String(64)` erkin matn — yaroqlilik va reviziya kodlari o'rnida.

Ish:
- `Version` ga `suitability_code` va `revision_code` (erkin `tag` dan ajratilgan).
- Konteyner nomlash qoidasi (loyiha sozlamasida shablon) va yuklashda tekshirish.
- Holat o'tishlari yaroqlilik kodlari bilan bog'lanadi (WIP → S0, Shared → S1-S4 va h.k.).
- EIR/BEP hujjatlarini loyihaga biriktirish imkoni.

Fayllar: `server/ges_server/orm.py`, `models/router.py`, `review/router.py`,
`web/src/pages/model/VersionsPanel.tsx`
Qabul mezoni: noto'g'ri yaroqlilik kodi bilan holat o'tishi rad etiladi (test).
Bog'liqlik: A2.

### G5 — Klassifikatsiya va model federatsiyasi

Muammo: `IfcClassification` yo'q; faqat uy qurilishi `kind` satri va `Pset_GES_*`.
Modellar mustaqil; bir necha bo'lim modelini bitta koordinata fazosida birlashtiradigan
federatsiya konteyneri yo'q. Clash detection bitta model ichida ishlaydi va 1500 elementdan
keyin bbox ga tushadi.

Ish:
- `IfcClassification` va `IfcClassificationReference` qo'llab-quvvatlash; klassifikator tanlash
  (Uniclass yoki mahalliy KSI).
- Federatsiya: `Federation` modeli — bir nechta model versiyasini bitta ko'rinishga yig'adi
  (G3 dagi CRS asosida joylashtiriladi).
- Clash detection federatsiya ustida ishlaydi; BVH indeksi bilan katta modellarda ham aniq.

Fayllar: `server/ges_server/orm.py`, `models/`, `web/src/viewer/Viewer.ts`,
`web/src/pages/model/ChecksPanel.tsx`
Qabul mezoni: ikki modeldagi to'qnashuv aniqlanadi (test).
Bog'liqlik: G3.

### G6 — Aktiv topshiruvi (COBie yoki unga o'xshash)

Muammo: model dan ekspluatatsiyaga aktiv ma'lumotini topshirish yo'li yo'q. Aktivlar (`Asset`)
qo'lda yaratiladi va `element_guid` bilan bog'lanadi.

Ish:
- IFC dan aktiv registrini generatsiya qilish: tur, joylashuv, ishlab chiqaruvchi, model,
  seriya raqami, kafolat, texnik xizmat davri.
- COBie eksport (yoki kelishilgan CSV/XLSX shakl) — qurilishdan ekspluatatsiyaga topshirish uchun.
- Aktivga hujjat biriktirish: qo'llanma, pasport, zavod sinov protokoli, ishga tushirish akti.

Fayllar: `server/ges_server/monitoring/parts.py`, yangi eksport moduli,
`web/src/pages/dashboard/*`
Qabul mezoni: IFC dan aktiv registri generatsiya qilinadi va aktivlar bilan bog'lanadi.
Bog'liqlik: G1, H1.

---

## H. Aktivlar, kodlash, CMMS

### H1 — Uskuna kodlash va ierarxiya (KKS / RDS-PP)

Muammo: `orm.py:598` — `Asset` tekis: nom, `element_guid`, `power_sensor_id`, hisoblagichlar,
JSON `config`. `parent_id` yo'q, funksional joylashuv yo'q, taksonomiya darajasi yo'q, KKS yoki
RDS-PP maydoni yo'q. `Sensor.key` erkin matn (`^[A-Za-z0-9_.\-/:]+$`) — "AGG1.P" kimningdir
boshidagi konvensiya. Haqiqiy GES boshdan oyoq KKS (yoki IEC 81346 asosidagi RDS-PP) bilan
belgilanadi va har O&M hujjati, chizma, ehtiyot qism shu kodga murojaat qiladi.

Ish:
- `Asset` ga: `parent_id`, `kks_code` (yoki `rds_pp_code`), `taxonomy_level` (ISO 14224:
  stansiya → tizim → uskuna → komponent → qism).
- `Sensor` ga ham `kks_code`.
- Kod formatini tekshiruvchi (KKS grammatikasi bo'yicha).
- Ierarxiya bo'yicha navigatsiya va agregatsiya (uskuna sog'ligi komponentlardan).
- Mavjud aktivlarni migratsiya qilish uchun yordamchi (kodlarni CSV dan import).

Fayllar: `server/ges_server/orm.py`, `monitoring/parts.py`, `monitoring/health.py`,
`web/src/pages/dashboard/*`, migratsiya
Qabul mezoni: ierarxiya bo'yicha aktiv daraxti ko'rinadi; noto'g'ri KKS kodi rad etiladi (test).
Bog'liqlik: A2. Bu aktiv registri o'sishidan oldin qilinishi kerak — keyinroq qimmat.

### H2 — CMMS chuqurligi

Muammo: `WorkOrder` (`orm.py:506`) yaxshi boshlanish, lekin yo'q: profilaktik xizmat rejalari
(faqat bitta `Asset.maintenance_interval_hours` hisoblagichi), ish rejalari/vazifalar ro'yxati,
mehnat va brigada vaqtini yozish, ruxsatnoma/LOTO, nosozlik kodlari, ish buyrug'i → ehtiyot qism
bandlash, aktiv bo'yicha xarajat jamlash, xizmat tarixi hisoboti.

Ish:
- `MaintenancePlan`: davriylik (vaqt yoki ish soati bo'yicha), vazifalar ro'yxati, avtomatik
  ish buyrug'i yaratish.
- `WorkOrder` ga ISO 14224 nosozlik kodlari: nosozlik rejimi, sabab, aniqlash usuli.
- Mehnat yozuvi: kim, qancha vaqt, qanday ish.
- Ehtiyot qism bandlash va sarflash ish buyrug'i orqali.
- Ruxsatnoma (permit-to-work) va LOTO holati — boshqaruv blokirovkasi bilan bog'lanadi (B4).
- Aktiv bo'yicha xizmat tarixi va xarajat hisoboti.

Fayllar: `server/ges_server/orm.py`, `monitoring/workorders.py`, `monitoring/parts.py`,
`web/src/pages/dashboard/*`
Qabul mezoni: profilaktik reja avtomatik ish buyrug'i yaratadi (test); LOTO faol bo'lganda
boshqaruv buyrug'i rad etiladi (test).
Bog'liqlik: B4, H1.

### H3 — Holat monitoringi arxitekturasi (ISO 13374)

Muammo: `health.asset_health` — 190 qatorli bitta funksiya, unda ma'lumot yig'ish, holat
aniqlash, sog'liq bahosi, prognoz va tavsiya birlashib ketgan. OSA-CBM ning oltita funksional
bloki va ular orasidagi interfeyslar yo'q, shuning uchun uchinchi tomon holat monitoringi tizimi
(Bently Nevada, Voith OnCare, SKF) ulanmaydi.

Ikkinchi muammo: aktivga bitta keng polosali vibratsiya skalyari
(`cfg["vibration_sensor_id"]`). Spektr/FFT yo'q, envelope/podshipnik nuqsoni chastotalari yo'q,
val nisbiy tebranishi/orbita yo'q, havo oralig'i yo'q, qisman razryad yo'q, moy tahlili yo'q.
Bu holat monitoringi emas, holat ko'rsatkichi.

Ish:
- `health.py` ni ISO 13374 bloklariga ajratish: DA → DM → SD → HA → PA → AG, har biri alohida
  modul va aniq interfeys bilan.
- Tashqi holat monitoringi tizimidan natija qabul qiladigan endpoint (SD/HA darajasida).
- Spektr ma'lumotini saqlash uchun model (vaqt qatori emas, alohida jadval).
- ISO 20816-5 zonalarini saqlab qolish, lekin `Asset` ning mashina guruhini H1 ierarxiyasidan
  olish.

Fayllar: `server/ges_server/monitoring/health.py` → `monitoring/cm/` paketi, `orm.py`
Qabul mezoni: tashqi tizim natijasi qabul qilinadi va sog'liq indeksiga qo'shiladi (test).
Bog'liqlik: H1.

---

## I. Raqamli egizak yetukligi

Hozirgi holat: tavsifiy va informativ, tor bashoratli bo'laklar bilan. Yuqoriga ko'tarilish
uchun quyidagilar kerak.

### I1 — Model kalibrovkasi

Muammo: `monitoring/twin.py` model parametrlarini berilgan holda ishlatadi. Quvur g'adir-budurligi,
turbina FIK egri chizig'i, ombor hajm-sath egri chizig'i — hech biri o'lchangan ma'lumotga
moslashtirilmaydi, qoldiq kuzatilmaydi, drift tuzatilmaydi. Shuning uchun "og'ish %" haqiqiy
degradatsiyani va kalibrovkalanmagan modelni bir-biriga qo'shib yuboradi.

Ish:
- Kalibrovka vazifasi: tarixiy ma'lumotdan parametrlarni moslashtirish (eng kichik kvadratlar
  yoki shunga o'xshash), natija `CalibrationRun` sifatida saqlanadi.
- Qoldiq kuzatuvi: kalibrovkadan keyingi qoldiq trendi; drift chegarasidan oshsa qayta
  kalibrovka taklifi.
- Kalibrovka tarixi va qaysi parametr qachon o'zgargani ko'rinadi.
- Kalibrovkalanmagan model bilan hisoblangan natija shunday belgilanadi.

Fayllar: `server/ges_server/monitoring/twin.py`, yangi `monitoring/calibration.py`, `orm.py`
Qabul mezoni: sintetik ma'lumotda kalibrovka ma'lum parametrni tiklaydi (test).
Bog'liqlik: A1, D2.

### I2 — Holat baholash va ortiqcha o'lchovlarni solishtirish

Muammo: o'lchovlar orasidagi fizik bog'liqlik ishlatilmaydi. Sarfni sath + zatvor holatidan
baholab, sarf o'lchagichi bilan solishtirish mumkin — bu ham yomon ma'lumotni aniqlaydi, ham
sensor yo'qolganda o'rnini bosadi.

Ish:
- Ortiqchalikni tekshiruvchi: bitta kattalik uchun bir nechta manba (o'lchangan, hisoblangan,
  modeldan) — kelishmovchilik alarmi.
- Oddiy holat baholash (masalan, ombor sathi va sarf uchun Kalman filtri) — bahoni virtual
  sensor sifatida `TWIN.*` ga chiqarish.
- Yomon ma'lumotni aniqlash sensor bo'yicha z-score dan chuqurroq: qoldiq asosida.

Fayllar: yangi `server/ges_server/monitoring/estimator.py`, `monitoring/twin.py`
Qabul mezoni: bitta sensor "qotganda" holat baholovchi uni aniqlaydi va o'rnini bosadi (test).
Bog'liqlik: A1, I1.

### I3 — Model validatsiya yozuvlari

Muammo: saqlangan validatsiya hisoboti yo'q (model va o'lchov, qabul mezonlari, amal qilish
muddati, imzo). Bunday yozuvsiz gidrotexnik xavfsizlik muhandisi egizak natijasiga tayanmaydi.

Ish:
- `ValidationRecord`: qaysi model, qaysi davr, qanday mezon, natija, kim tasdiqladi, amal qilish
  muddati.
- Natija ko'rsatilganda validatsiya holati ham ko'rsatiladi (validatsiyalangan / muddati o'tgan /
  validatsiyalanmagan).
- Muddati o'tganda ogohlantirish.

Fayllar: `server/ges_server/orm.py`, `monitoring/twin.py`, `web/src/pages/dashboard/TwinPanels.tsx`
Qabul mezoni: validatsiyalanmagan model natijasi shunday belgilanadi.
Bog'liqlik: I1.

### I4 — Egizak va model versiyasining sinxronligi

Muammo: `Sensor.element_guid` — oddiy `String(32)`. Hech narsa GUID hali joriy nashr etilgan
versiyada mavjudligini tekshirmaydi; model qayta ko'rilganda qayta bog'lash yo'q; as-built teskari
aloqasi yo'q. Yangi versiyada GUID lar qayta generatsiya qilinsa, egizak jimgina uziladi.

Ish:
- Nashr etishda: barcha sensor bog'lanishlari tekshiriladi; yo'qolgan GUID lar ro'yxati.
- Qayta bog'lash yordamchisi: nom, joylashuv yoki Pset bo'yicha taklif.
- Uzilgan bog'lanish — alarm, jim emas.
- Desktop tomonda GUID barqarorligi (K2 bilan bog'liq).

Fayllar: `server/ges_server/models/router.py`, `monitoring/router.py`,
`web/src/pages/model/MonitoringPanel.tsx`
Qabul mezoni: yo'qolgan GUID bilan nashr etish ogohlantirish beradi (test).
Bog'liqlik: G1, K2.

### I5 — ML integratsiyasini haqiqiy qilish

Muammo: `monitoring/parts.py:275` — `POST /ml/predictions` tashqarida hisoblangan bashoratni
qabul qiladi va `ML.*` sensorlariga yozadi. Xususiyat quvuri, belgilangan nosozlik tarixi
(`WorkOrder` da nosozlik kodlari yo'q), o'qitish, model registri, drift kuzatuvi — hech biri yo'q.

Ish:
- H2 dagi nosozlik kodlari o'qitish uchun belgilangan ma'lumot beradi.
- Xususiyat eksporti: aktiv bo'yicha vaqt oynalarida statistik xususiyatlar.
- Model registri: qaysi model, qaysi ma'lumotda o'qitilgan, sifat ko'rsatkichlari, qachon
  joriy etilgan.
- Drift kuzatuvi: bashorat taqsimoti o'zgarsa ogohlantirish.

Fayllar: `server/ges_server/monitoring/parts.py`, yangi `monitoring/ml/`
Qabul mezoni: model registri orqali joriy etilgan model bashoratlari kuzatiladi.
Bog'liqlik: H2, I1.

---

## J. Muhandislik hisoblarini tuzatish

Bu bosqich shoshilinch, chunki hozirgi natijalar xavfsizlik qarorlariga ta'sir qiladi va
ba'zilari noto'g'ri tomonga xato qiladi. Har vazifada tekshirilgan raqamlar keltirilgan.

### J1 — Xavfsizlik bahosini tuzatish ✅ (`a1f911e`)

Muammo (`server/ges_server/sim/safety.py`):
- `_stab_judge` (`:48`) faqat `fs_sliding` ni o'qiydi, ya'ni ilashish (cohesion) bilan.
  `fs_sliding_friction_only` hisoblanadi (`dam_stability.py:295`, `:390` da qaytariladi) lekin
  hech qachon tekshirilmaydi. Tekshirilgan: seysmik stsenariyda (bosh suv 912 m, k_h 0.15,
  talab 1.1) `fs_sliding = 1.10` — o'tadi, `fs_sliding_friction_only = 0.81` — to'g'on sirpanadi.
  Standart amaliyot (USACE EM 1110-2-2200) ilashish ishlatilganda 2.0 / 1.7 / 1.3 talab qiladi;
  kod esa 1.5 / 1.3 / 1.1 ni ilashishli qiymatga qo'llaydi. `c` default 200 kPa — beton-qoya
  kontakti uchun maydon sinovisiz himoya qilib bo'lmaydigan qiymat.
- `_seismic_judge` (`:63`) shartsiz `"ok"` qaytaradi. Tekshirilgan:
  `_seismic_judge({"pga_g":2.0,"kh":0.9},{})` → `('ok', ...)`. Bu stsenariy hech qachon yiqilmaydi.
- `:256` keng `except` → `status = "skip"`, `:287` esa skip larni maxrajdan chiqaradi
  (`score = 100*(n_ok + 0.5*n_warn)/n_done`). Sizib o'tish, ikkala barqarorlik va gidrozarba
  hisoblanmasa, qolgan 8 tadan 100 ball va "Xavfsiz — barcha mezonlar bajarildi" chiqadi.

Ish:
- `_stab_judge` ikkala koeffitsientni ham tekshiradi; ilashishsiz qiymat uchun alohida (yuqoriroq)
  talab. Talablar manbasi ko'rsatiladi.
- `_seismic_judge` haqiqiy mezon bilan (J3 dan keyin).
- `skip` — `fail` deb hisoblanadi yoki umumiy baho berilmaydi. 0–100 ball turli chegaraviy
  holatlar ustida noto'g'ri asbob — uni olib tashlash yoki konyunktiv qilish (bitta fail → fail).
- Har `skip` sababi foydalanuvchiga ko'rinadi.

Fayllar: `server/ges_server/sim/safety.py`
Qabul mezoni: yuqoridagi uchta holat uchun testlar; sirpanadigan to'g'on `fail` beradi.
Bog'liqlik: yo'q. Eng birinchi.

### J2 — Yorilgan poydevor tahlili ✅

Muammo: `dam_stability.py:265-278`, `:294`, `:331` — σ_heel manfiy bo'lganda kod buni belgilaydi
(seysmik holatda hatto belgilamaydi, `:331`), lekin (a) yoriq uzunligi bo'ylab ko'tarish bosimini
to'liq bosh suvgacha qayta hisoblamaydi va (b) `c·B` ni yorilmagan uzunlikka qisqartirmaydi.
Ikkalasi ham USACE/USBR/ICOLD amaliyotida majburiy. Yuqoridagi holat (σ_heel = −0.086 MPa)
butun poydevor ustida va to'liq `c·B` bilan baholanadi.

Ish:
- Yoriq uzunligini iterativ aniqlash; ko'tarish epyurasini yoriq bo'ylab bosh suv bosimiga
  o'zgartirish; ilashish maydonini qisqartirish; qayta hisoblash konvergensiyagacha.
- Natijada yoriq uzunligi alohida ko'rsatiladi.

Fayllar: `sim/ges_sim/dam_stability.py`
Qabul mezoni: qo'lda hisoblangan misol bilan solishtiriladigan test.
Bog'liqlik: J1.

### J3 — Seysmik koeffitsientni tuzatish

Muammo: `seismic.py:57`, `:207` — `beta = S_e/a_g` allaqachon EC8 grunt faktorini o'z ichiga
oladi, keyin `seismic_coefficient` `beta` ni 2.5 ga qirqadi va S yo'qoladi. Tekshirilgan,
a_g = 0.2 g da barcha grunt sinflari uchun `kh = 0.1250` — qoya va yumshoq gil bir xil.

Ikkinchi muammo: `k_h = A·β·K₁` EC8 elastik ordinatasini SNiP II-7-81 ning K₁ = 0.25 zarar
koeffitsienti bilan birlashtiradi. Buni hech bir norma sanksiyalamaydi. Ustiga SNiP II-7-81 —
binolar normasi; gidrotexnik inshootlar SNiP 2.06.15 / SP 358 ga kiradi, ular hech qayerda
keltirilmagan.

Uchinchi muammo: bir ishda ikki qarama-qarshi kuch ko'rsatiladi —
`structures[0].force_kn = S_e·g·m = 36 151 kN/m` (`:222`) va quyi oqimda ishlatiladigan
`k_h·W = 0.125 × 76 800 = 9 600 kN/m`. Nisbat 3.77×, ikkalasi ham izohsiz ko'rsatiladi.

Ish:
- Bitta norma yo'lini tanlash: yo EC8 (q koeffitsienti bilan), yo SNiP/SP (o'z β si bilan).
  Tanlov va bandi natijada ko'rsatiladi.
- Grunt sinfi natijaga ta'sir qilishi kerak — qirqishni olib tashlash yoki to'g'ri joyda qo'llash.
- Ikki kuch qiymatining kelishmovchiligini bartaraf qilish.
- Gidrotexnik inshootlar normasiga havola.

Fayllar: `sim/ges_sim/seismic.py`, `server/ges_server/sim/safety.py`
Qabul mezoni: grunt sinfi o'zgarganda `kh` o'zgaradi (test); ko'rsatilgan kuchlar izchil.
Bog'liqlik: J1.

### J4 — Gidrozarbada quvur profili va kavitatsiya

Muammo: `water_hammer.py:262` — `cav = hmin + 10.3 < 0.3`. `hmin` pyezometrik napor, quvur
balandligi z(x) ayirilmaydi, ya'ni butun quvur zatvor balandligida yotadi deb faraz qilinadi.
Ustun uzilishi aynan yuqori nuqtalarda bo'ladi — bu tekshiruv aynan shu uchun mavjud.
Tekshirilgan: `valve_elev_m` maydon sifatida e'lon qilingan, izohi "Kavitatsiya tekshiruvi
uchun", lekin `'valve_elev_m' in inspect.getsource(run)` → `False`. Maydon interfeysda
ko'rinadi va jimgina e'tiborsiz qoldiriladi.

Yana: manfiy ichki bosimda tashqi siqilish/buklanish tekshiruvi yo'q — yupqa devorli quvur uchun
aynan shu nosozlik rejimi.

Ish:
- Quvur balandligi profili kiritish (nuqtalar ro'yxati yoki boshi/oxiri + oraliq nuqtalar).
- Kavitatsiyani har tugunda `H(x) - z(x)` bo'yicha tekshirish; eng xavfli nuqtani ko'rsatish.
- Tashqi bosim ostida buklanish tekshiruvi.
- `valve_elev_m` ni ishlatish yoki maydonni olib tashlash.

Fayllar: `sim/ges_sim/water_hammer.py`
Qabul mezoni: yuqori nuqtali profil kiritilganda kavitatsiya aniqlanadi (test).
Bog'liqlik: yo'q.

### J5 — Regulyator modelini barqarorlashtirish

Muammo: `governor.py:262` — `hq = (q/max(g,1e-3))**2`, oldinga Eyler, dt = 0.01 s qat'iy.
To'liq yuk tashlashda o'lchangan: `h = (q/g)²` maksimumda 44.44 (nominal naporning 4444 %),
qirqishdan oldin `q` = −0.2830 pu (8 qadamda jimgina 0 ga qirqiladi), `P_mech` minimumda
−4.267 pu (`series.p_mech` da chiziladi). Anti-windup yo'q: `xi` (`:256`) zatvor to'yinganda
cheksiz integrallaydi, −0.6346 ga yetadi va `g == 0` bo'lgan t = 6.36 s dan keyin ham siljiydi.
Xabar qilinadigan ortiqcha tezlik (24.21 %) tasodifan ishonarli, lekin uni bergan model 44×
napor va −4.3 pu quvvat orqali o'tgan.

Yana: `:291` — cheksiz shina rejimi shartsiz "barqaror" deb e'lon qilinadi; uning xato signali
(`:250`) `(p_ref − pl_est)·R·5` — asossiz `R*5` koeffitsienti.

Ish:
- `xi` ga anti-windup (zatvor to'yinganda integratsiyani to'xtatish yoki qayta hisoblash).
- `gmin` qo'yish va `h = (q/g)²` uchun qattiqlikka moslashuvchan qadam yoki implitsit sxema.
- `q < 0` holatini fizik jihatdan to'g'ri ishlash (jim qirqish emas).
- Cheksiz shina barqarorligini haqiqiy mezon bilan.
- IEEE/IEC benchmark holati bilan test.

Fayllar: `sim/ges_sim/governor.py`
Qabul mezoni: yuk tashlash testida `h`, `q`, `P_mech` fizik chegaralarda qoladi.
Bog'liqlik: yo'q.

### J6 — To'g'on yorilishi va pastki oqim

Muammo: `flood.py:369-395`, `:398` — yorilish gidrografi marshrutlash siklidan keyin quriladi va
hech qachon teskari uzatilmaydi. Tekshirilgan: yorilish 595.79 Mm³ ni chiqaradi, Qp = 37 941 m³/s,
davomiyligi 8.7 soat — lekin ombor sathi qatori (385 qadam) o'zgarmay 906.29 m da tugaydi.
Pastki oqim to'lqini Froehlich uchburchagi bo'lib, Muskingum bilan marshrutlanadi — bu asta
o'zgaruvchi toshqin uchun chiziqli gidrologik usul, yorilish fronti uchun yaroqsiz.
`downstream_max_depth_m` esa Manning normal chuqurligi sifatida, cheksiz trapetsiya ustida
(qayir yo'q) hisoblanadi va 2 kasr bilan beriladi. Bu favqulodda rejalashtirish organi
ishlatadigan suv bosish raqami.

Ish:
- Yorilishni ombor balansiga ulash (teskari aloqa).
- Yorilish to'lqini uchun dinamik marshrutlash (Sen-Venan) yoki natijani aniq "faqat indikativ"
  deb belgilash va aniqlik da'vosini olib tashlash.
- Ko'ndalang kesimga qayir qo'shish.
- Froehlich amal qilish diapazoni tekshiruvi (V_w 0.0139–660 Mm³, h_w 3.66–77 m) va
  noaniqlik oralig'i (regressiya sochilishi taxminan 2 barobar).

Fayllar: `sim/ges_sim/flood.py`
Qabul mezoni: yorilishda ombor sathi tushadi (test); diapazondan tashqarida ogohlantirish.
Bog'liqlik: yo'q.

### J7 — Sizib o'tish modulini qayta ko'rib chiqish

Muammo (`sim/ges_sim/seepage.py`):
- `:236` — `i_exit = (h_ld − h2)/ld` bu Dyupyui parabolasining 30 m dagi o'rtacha gorizontal
  qiyaligi; `:237` uni `i_cr = (G_s−1)/(1+e)` bilan, ya'ni ko'tarilish uchun kritik vertikal
  gradient bilan solishtiradi. Noto'g'ri taqqoslash, suffoziyani tizimli ravishda kam baholaydi.
  Default qiymatlarda `i_exit = 0.599`, `i_cr = 0.971`, FS = 1.62 → "xavfsiz".
  Standart usul (Terzagi, USACE EM 1110-2-1901) amalga oshirilmagan.
- `:25` — `"rock": (..., 1.8, 0.4)` izohda "USBR amaliyoti", lekin yorilgan qoya uchun ruxsat
  etilgan chiqish gradienti 0.4 USBR ning nashr etilgan qiymati emas. Xavfsizlikka oid
  tekshiruvda o'ylab topilgan mezon.
- `:191` — `q = k·H·N_f/N_d`, `N_f = 4` va `N_d = 12` erkin foydalanuvchi kiritmasi sifatida.
  Oqim to'ri qurilmaydi, ya'ni sizib o'tish sarfi kiritilgan parda chuqurligi, apron uzunligi va
  poydevor kengligiga umuman bog'liq emas. `q_l_s_m` 3 kasr bilan beriladi.
- `:18` — Leyn talabi 8.5 "mayda qum" deb belgilangan; Leynda 8.5 — juda mayda qum yoki loyqa,
  mayda qum 7.0.
- `:196` — Xosla G_E faqat gorizontal poydevor ostidagi quyi oqim pardasi uchun amal qiladi;
  maydon esa umumiy "shpunt/parda chuqurligi", yuqori/quyi farqi yo'q.
- Modulning raqamli testi umuman yo'q — butun test to'plamida `seepage` bir marta,
  `test_catalog.py:17` da ID ro'yxatida uchraydi.

Ish:
- Chiqish gradientini to'g'ri usul bilan (toe da d/2 bo'yicha Terzagi ko'tarilishi).
- "rock" mezonini haqiqiy manbaga asoslash yoki olib tashlash.
- Oqim to'rini geometriyadan qurish yoki N_f/N_d ni kiritma sifatida olib tashlab, natijani
  "taxminiy" deb belgilash.
- Leyn jadvalini tuzatish.
- Xosla ni faqat amal qiladigan holatda qo'llash.
- Filtr/granulometriya mezonlari (Terzagi, USBR/NRCS) — suffoziyaga qarshi asosiy himoya.
- Raqamli testlar.

Fayllar: `sim/ges_sim/seepage.py`, `sim/tests/`
Qabul mezoni: qo'lda hisoblangan misollar bilan testlar; noto'g'ri mezonlar olib tashlangan.
Bog'liqlik: yo'q.

### J8 — Transformator issiqlik modelini tiklash

Muammo: `transformer.py:178`, `:205` — `k21` va `k22` `_k21, _k22` sifatida ochiladi va tashlanadi;
`:205` IEC 60076-7 band 8.2.2 dagi ikki shoxli model o'rniga bitta birinchi tartibli kechikish
qo'yadi. Izoh buni tan oladi. Tashlangan shoxlar aynan yuk sakrashida issiq nuqtaning oshib
ketishini beradi — 120 °C / 140 °C chegaralariga nisbatan tekshiriladigan kattalik.
O'lchangan (ONAF, 0.6 → 1.5 pu sakrash, 30 °C atrof): kod 151.0 °C, IEC ikki shoxli 157.2 °C —
6.2 K kam, eskirish tezligi 44.1 va 73.4 (resurs sarfi 40 % kam ko'rsatiladi).

Yana: `:216` — kraft uchun `life_hours = 150000` IEC qiymati emas; kraft nisbiy eskirish
tenglamasi 98 °C ga, yaxshilangani 110 °C ga normallashtirilgan — ikkalasini bitta konstantaga
bo'lish ikki qog'oz turini solishtirib bo'lmaydigan qiladi. `:217` — `lol_days` ikki nomostiq
birlikdagi kalit ostida qaytariladi (`aging_relative` o'lchamsiz, `loss_of_life_days` kun).

Ish:
- Ikki shoxli modelni tiklash (`COOLING` da konstantalar allaqachon bor).
- `life_hours` ni IEC manbasiga moslashtirish yoki manbani ko'rsatish.
- Ikki qog'oz turi uchun normallashtirishni to'g'ri qilish.
- Kalitlar va birliklarni tartibga solish.
- IEC 60076-7 ilovasidagi yuklanish misoli bilan test.

Fayllar: `sim/ges_sim/transformer.py`, `sim/tests/`
Qabul mezoni: IEC ilova misoli bilan mos keladi (test).
Bog'liqlik: yo'q.

### J9 — Amal qilish diapazonlari va ogohlantirishlar ✅ (`fb4b3ff`)

Muammo: regressiya va empirik usullar o'z ma'lumotlar to'plamidan tashqarida jimgina
ekstrapolyatsiya qilinadi:
- `rainfall.py:292` — Kirpich oltita Tennessi havzasida (0.4–45 ga) kalibrovkalangan; default
  havza 1200 km² — to'rt tartib tashqarida. TR-55 taxminan 25 km² gacha.
- `rainfall.py:334` — `dt = 1.0` soat qat'iy, NRCS esa Δt ≤ 0.133·t_c talab qiladi.
  O'lchangan: L=60 km S=0.02 → t_c=7.00 soat, kerak ≤0.93 — buziladi; L=2 km S=0.10 →
  t_c=0.275 soat, kerak ≤0.037 — 27 barobar buziladi. Har realistik havza kam ruxsatli.
- `rainfall.py:302` — `w = [1/(i+1)**0.6 ...]` "almashinuvchi blok" deb atalgan, lekin haqiqiy
  usul IDF egri chizig'idan blok oladi; bu esa manbasiz darajali qonun. U gidrograf cho'qqisini
  bevosita belgilaydi. IDF kiritmasi umuman yo'q.
- `rainfall.py:372-387` — GLOF uchburchak gidrografi 1 soatlik binlarga o'rtachalanadi, hodisa
  esa 1 soatdan qisqa. O'lchangan (V = 5 Mm³, h = 30 m): xulosada `glof.peak_m3s = 3900`,
  haqiqiy maksimal kiruvchi 1391 — cho'qqining 64 % marshrutlashga kirmaydi. Bitta ishda ikki
  xil cho'qqi xabar qilinadi.
- `landslide.py:193` — faqat P tekshiriladi; Heller-Hager ning F (0.86–6.83), S (0.09–1.64),
  M (0.11–10.02), α (30–90°) tekshirilmaydi. `slope_deg` 10° ga ruxsat beradi.
- `flood.py:302-310` — Muskingum ning faqat quyi chegarasi (2KX ≤ Δt) tekshiriladi, yuqorisi
  (Δt ≤ 2K(1−X)) yo'q. O'lchangan: 0.5 km uchastka, 20 ta, dt 15 daq → C0,C1,C2 =
  (0.9818, 0.9891, −0.9708), hisob ogohlantirishsiz yakunlanadi va 1197.9 m³/s natija beradi.
  `:309` dagi `max(..., 0.0)` manfiy sarflarni qirqadi va massani yo'qotib, beqarorlikni yashiradi.
  `:404` da `x` foydalanuvchi kiritmasidan jimgina o'zgartiriladi.
- `surge_tank.py:166` — Toma nisbati to'liq naporda hisoblanadi (net kerak) va minimal emas,
  nominal napor ishlatiladi.
- `penstock.py:36` — Swamee-Jain 2300 < Re < 4000 da qo'llanadi, amal qilish chegarasi esa
  5000–1e8; Re = 2300 da uzilish bor.

Ish:
- Har modulda kiritma diapazon tekshiruvi; tashqarida tuzilgan ogohlantirish (`summary.warnings`
  massivi), faqat `verdict` matnida emas.
- Vaqt qadamini usul talabidan kelib chiqib avtomatik tanlash (yomg'ir-oqim, GLOF).
- Yomg'ir taqsimotini IDF kiritmasiga asoslash yoki uni "shartli shakl" deb belgilash.
- Muskingum ning ikkala chegarasi; buzilganda uchastka sonini avtomatik moslashtirish yoki xato.
- Ikki xil cho'qqi xabar qilinmaydi — marshrutlangan qiymat asosiy.

Fayllar: `sim/ges_sim/rainfall.py`, `landslide.py`, `flood.py`, `surge_tank.py`, `penstock.py`
Qabul mezoni: har usul uchun diapazondan tashqari kiritmada ogohlantirish chiqishini
tekshiradigan test.
Bog'liqlik: yo'q.

### J10 — Ombor balansi va suv tashlagich

Muammo:
- `reservoir.py:125-129` — `q_spill` qadam boshidagi sathdan hisoblanadi va to'liq `dt` uchun
  ayiriladi, lekin `available` (`:125`) ga kiritilmaydi. `v_next = max(v_next, 0.0)` (`:129`)
  yo'qdan hajm yaratadi, ogohlantirishsiz va qoldiq xabar qilinmasdan. Q ∝ H^1.5 bilan oshkora
  Eyler sutkalik qadamda toshqin uchun noaniq — o'sha paketdagi `flood.py` ning Puls iteratsiyasi
  bilan izchil emas.
- `reservoir.py:77-81`, `flood.py:330` — `Q = m·b·√(2g)·H^1.5` to'g'ri Kriger-Ofitserov shakli,
  lekin normadagi to'liq ko'rinish `Q = ε·σ_s·m·b·√(2g)·H₀^1.5`. Yo'q: yon siqilish ε
  (bykalar/qirg'oq, odatda 5–15 % kamaytiradi), bostirish σ_s (past naporda 20–40 %), kelish
  tezligi napori H₀ da. Barcha tushib qolganlar suv tashlagich o'tkazuvchanligi uchun xavfli
  tomonga xato qiladi.
- `gate_opening` erkin qirralik oqimga chiziqli ko'paytuvchi sifatida qo'llanadi; qisman
  ko'tarilgan zatvor esa teshik oqimi `Q = μ·b·a·√(2gH)` (∝ H^0.5).

Ish:
- Massa balansini yopiq qilish; qoldiqni natijada xabar qilish; manfiy hajm holatini xato qilish.
- ε, σ_s, H₀ ni qo'shish (yoki ularning yo'qligini aniq belgilash).
- Zatvor oqimini teshik formulasi bilan.
- `reservoir` va `flood` ni bitta yechim sxemasiga keltirish.

Fayllar: `sim/ges_sim/reservoir.py`, `flood.py`
Qabul mezoni: massa balansi qoldig'i natijada bor va chegaradan kichik (test).
Bog'liqlik: yo'q.

### J11 — Kuchlanish tekshiruvlarini izchil qilish ✅

Muammo:
- `dam_stability.py:298`, `:335` — `s_toe` vertikal poydevor kuchlanishi σ_z. Og'ma quyi oqim
  qirrasida gravitatsion usul uchun hal qiluvchi kattalik bosh kuchlanish
  σ_p = σ_z(1+m_d²) − p₂·m_d². O'lchangan (m_d = 0.75): xabar qilingan σ_toe = 0.861 MPa,
  gravitatsion usul bosh kuchlanishi 1.290 MPa (+50 %, hech qachon hisoblanmaydi).
  `cracking.py:302` esa quyi oqim qirrasi uchun σ_p ni to'g'ri hisoblaydi — ikki modul bitta
  to'g'on haqida kelishmaydi. Yuqori oqim bosh kuchlanishi hech qayerda hisoblanmaydi;
  yoriq mezoni (`cracking.py:313`) σ_z ga qo'llanadi.
- `dam_stability.py:265-267` va `cracking.py:284` — bir xil to'g'on uchun ko'tarish bosimini
  har xil hisoblaydi (birinchisi foydalanuvchi `drain_x_m` bilan USACE uch nuqtali epyura,
  ikkinchisi drenajni `0.1·B` da qat'iy kodlaydi). Kesishtirish yo'q.
- `dam_stability.py:138` — maydon izohi "Drenaj masofasi tovondan", lekin `:267` `x` ni
  `_profile` (`:213`) da poshna deb belgilangan `x = 0` dan o'lchaydi. Galereya joyini
  tovondan kiritgan foydalanuvchi ko'zguga aylangan epyura oladi.
- `cracking.py:394-418` — `_risk_field` 1D balandlik profiliga o'ylab topilgan konstantalar
  qo'shadi (`abutment_extra = 0.25`, `crest_extra = 0.35`, `thermal*(0.5+0.5*edge)`). Manbasiz.
  Natija 3D da "Yoriq xavfi: ko'k — past, qizil — yuqori" legendasi bilan hech qanday izohsiz
  ko'rsatiladi.
- `cracking.py:334-343` — JCI yoriqlanish indeksi → ehtimollik xaritasi 5/30/60/85 % beradi;
  JCI ning nashr etilgan munosabati `P = 1 − exp(−(I/0.92)^−4.29)` esa 11/26/50 %. 2 barobargacha
  farq, manba esa "JCI Guidelines 2016" deb ko'rsatilgan.

Ish:
- Bosh kuchlanishni ikkala qirrada hisoblash va tekshirish; ikki modulni kelishtirish.
- Ko'tarish bosimini bitta funksiyaga chiqarish, ikkala modul shuni chaqiradi.
- Maydon izohini va o'lchash boshlanishini kelishtirish.
- `_risk_field` ni olib tashlash yoki "illyustrativ interpolyatsiya, tahlil natijasi emas" deb
  aniq belgilash.
- JCI munosabatini haqiqiy formula bilan almashtirish.

Fayllar: `sim/ges_sim/dam_stability.py`, `cracking.py`
Qabul mezoni: ikki modul bir xil to'g'on uchun bir xil ko'tarish bosimi va kuchlanish beradi.
Bog'liqlik: J2.

### J12 — Hisoblash resursi chegarasi

Muammo: `water_hammer.py:214` — `steps = int(sim_s/dt) + 1`, `dt = (L/N)/a`. `sim_s` ning
maksimumi yo'q (shuningdek `surge_tank.sim_s`, `flood.duration_h`). Maydon chegaralari ichidagi
so'rov: `water_hammer(length_m=20, reaches=200, sim_s=120)` — 120 soniya CPU da tugamadi.
`N=200, L=5m, sim=60s` → sof Python da 4.4e8 ichki amal.
`server/ges_server/sim/router.py:218` — `Role.viewer` ham ishga tushira oladi; `:305` — CFD dan
boshqa turlar `BackgroundTasks` orqali, ya'ni API jarayonining o'z thread pool ida, GIL ushlab.
Faqat CFD da `cfd_timeout_s` bor.

Ish:
- Har modulda qadam byudjeti: `steps` chegaradan oshsa xato va kerakli parametrni ko'rsatish.
- Analitik ishlar uchun ham server tomonda timeout.
- Ish navbatini API jarayonidan ajratish (L3).
- Foydalanuvchi bo'yicha bir vaqtda ishlayotgan ishlar soni chegarasi.

Fayllar: `sim/ges_sim/*`, `server/ges_server/sim/router.py`, `sim/worker.py`
Qabul mezoni: chegaradan oshgan parametr 400 beradi (test).
Bog'liqlik: L3.

### J13 — Tashqi benchmark testlari

Muammo: mavjud testlar yaxshi, lekin deyarli hammasi modulni o'zi amalga oshirgan formula bilan
tekshiradi (Joukovskiy, ishqalanishsiz surge, Korteveg) — bu o'z-o'ziga izchillik.
Butun to'plamda ikkita haqiqiy tashqi manba bor: FAO-56 Ra va Mudi ishqalanish koeffitsienti.

Testsiz yuqori xavfli modullar: `seepage.py` (faqat smoke), `governor.py` (44× napor testdan
o'tadi), `transformer.py` (issiqlik ODE lari tekshirilmagan), `landslide.py` (faqat monotonlik),
`cracking.py` (absolyut kuchlanish tekshirilmaydi, `_risk_field` umuman testsiz),
`sediment.py` (Brune koeffitsientlari tekshirilmagan), `advisor.py` (hech bir test import
qilmaydi), Muskingum barqarorlik chegaralari, diapazon ogohlantirishlari (birorta test
ogohlantirish chiqishini tekshirmaydi).

Ish: quyidagi tashqi benchmarklar bo'yicha testlar:
- Wylie & Streeter dagi ishlangan MOC masalasi (jadvalli bosimlar bilan).
- USBR yoki USACE gravitatsion to'g'on misoli.
- IEC 60076-7 ilovasidagi yuklanish holati.
- NRCS TR-55 ishlangan misoli.
- Froehlich va Heller-Hager uchun nashr etilgan holat tadqiqoti.
- Har diapazon ogohlantirishi uchun test.

Fayllar: `sim/tests/`
Qabul mezoni: yuqoridagi har biri uchun kamida bitta test; `advisor.py` qamrab olinadi.
Bog'liqlik: J1–J12.

---

## K. Desktop konsolidatsiya

### K1 — Blender ni yagona trek qilish

Muammo: `desktop/GesWorkbench/ges_workbench` va `desktop/blender/sath` orasida 1538 qator
bir xil (o'lchangan: `ges_objects.py` 753 qator 100 %, `server_client.py` 273 qator 100 %,
`dxf_prepare.py` 309 qator 100 %, `assimp_load.py` 115 qator 100 %). Lekin bu muammo emas —
`desktop/build/sync_blender.py` ularni avtomatik sinxronlaydi, CI da `--check` bilan tekshiriladi
(`ci.yml:14`) va `desktop/tests/test_sath_pure.py:13` da assert qilinadi. Bu to'g'ri yondashuv.

Haqiqiy to'siq boshqa joyda: `desktop/blender/sath/fc_engine.py:61-79` — Blender addoni
FreeCAD ni `sys.path` va `os.add_dll_directory` orqali o'z jarayoniga yuklaydi va
`sath/wb/ges_objects.py` dagi FreeCAD sinflarini geometriya yadrosi sifatida ishlatadi
(`fc_engine.py:198-230` — `shape.tessellate()`). `ges_objects.SATH_OT_add_object.poll()`
(`:180`) `fc_engine.available()` ga qaytadi, ya'ni FreeCAD o'rnatilmagan bo'lsa butun GES obyekt
tizimi ishlamaydi. `prefs.py:10` da `~/Tools/fc-py313` qat'iy kodlangan — Blender ning Python
3.13 iga aniq mos keladigan qo'lda qurilgan FreeCAD.

Ya'ni hozir "ikki klient" emas, "bitta klient + `sys.path` orqali biriktirilgan 300 MB CAD yadrosi".

Ish:
- 11 ta parametrik obyekt quruvchisini FreeCAD/OCC dan `bmesh` ga ko'chirish.
- `fc_engine.py` va `sath/wb/` ni olib tashlash.
- `desktop/GesWorkbench/` (4938 LOC), NSIS/fork quvuri va FreeCAD bog'liqligini arxivlash.
- Uchinchi sinxronlanmagan nusxa: `server/ges_server/models/assimp_load.py` ikkala desktop
  nusxasi bilan bayt-bayt bir xil, lekin `sync_blender.py:20` da faqat bitta manzil bor.
  Uchalasini haqiqiy o'rnatiladigan umumiy paketga chiqarish.

Fayllar: `desktop/blender/sath/ges_objects.py`, `fc_engine.py`, `wb/`, `prefs.py`,
`desktop/build/sync_blender.py`, `desktop/GesWorkbench/`
Qabul mezoni: FreeCAD o'rnatilmagan mashinada barcha GES obyektlari yaratiladi (test).
Bog'liqlik: yo'q. Katta ish, lekin ikkinchi trekni yopadigan yagona yo'l.

### K2 — Round-trip da obyekt ma'lumotini saqlash

Muammo: `props.py:175` — `snapshot(s)` faqat `Scene.ges` xususiyatlari bo'yicha yuradi.
`ops_server.py:184` esa `ifc.load()` dan keyin faqat `props.restore(bpy.context.scene.ges, snap)`
chaqiradi. `Object.ges` — `kind`, `role` va butun `params` kolleksiyasi (`ges_objects.py:72-76`) —
snapshot ga olinmaydi va tiklanmaydi.

Natija: serverdan istalgan versiyani ochganda har GES obyekti oddiy Bonsai mesh ga aylanadi.
`ges_objects.by_role()` (`:111`) hamma narsa uchun `None` qaytaradi va `sim_anim.animate_hydro`
`if o is not None` (`sim_anim.py:170-172`, `:186`, `:189`, `:191`) qo'riqchilari tufayli egizak
animatsiyasi jimgina hech narsa qilmaydigan holatga tushadi — xato yo'q, ogohlantirish yo'q.
Xuddi shu `animate_seismic` (`:339`) va `animate_transformer` (`:311`) uchun.

Pset larning o'zi IFC da saqlanadi va server ularni qayta o'qiy oladi
(`server_client.py:207` `/ges-params`), lekin Blender klienti o'z parametrik obyektlarini
tiklamaydi — `ifc.py:81` dagi yagona `get_psets` chaqiruvi faqat yozish yo'lida.

Ish:
- `ifc.load()` dan keyin `bpy.data.objects` bo'ylab yurib, har entitydan `Pset_GES_*` o'qib
  `obj.ges.kind` va `obj.ges.params` ni tiklash.
- `role` ni `Pset_GES_Object` ichida xususiyat sifatida saqlash (`wb/ges_objects.py:48`), shunda
  u ham round-trip dan o'tadi.
- Tiklanmagan obyekt bo'lsa — aniq ogohlantirish, jim degradatsiya emas.

Fayllar: `desktop/blender/sath/props.py`, `ops_server.py`, `ifc.py`, `ges_objects.py`
Qabul mezoni: yuklab → serverga → qaytib olgandan keyin egizak animatsiyasi ishlaydi (headless test).
Bog'liqlik: yo'q. Eng shoshilinch desktop nosozligi.

### K3 — Bloklovchi tarmoq chaqiruvlarini olib tashlash

Muammo: addonda threading va modal operator umuman yo'q. `guard()` (`ops_server.py:15`) —
oddiy try/except, `fn()` ni `execute()` ichida sinxron chaqiradi. `server_client.py:51` —
bloklovchi `urllib.request.urlopen`, quyidagi timeoutlar bilan:
- `diff()` — `timeout=900` (`server_client.py:235`), `ops_review.py:235` dan chaqiriladi.
- `safety_check()` — `timeout=600` (`:230`), `ops_sim.py:337` dan.
- `download_version()` — default 60 s, chegarasiz tana o'qish (`:110`), `ops_server.py:178` dan.

Katta IFC da "Ota bilan farq" bosilsa Blender oynasi 15 daqiqagacha qotadi — qayta chizish yo'q,
ESC yo'q, OS "Not Responding".

To'g'ri namuna loyihada bor: `ops_sim._poll_factory` (`ops_sim.py:139-165`) uzoq sim ishini
`bpy.app.timers` bilan bloklamasdan so'raydi.

Ish:
- `diff`, `safety_check`, `download_version` ni yuborish + timer bilan so'rash sxemasiga o'tkazish
  (yoki ishchi thread + timer orqali natijani qaytarish).
- Progress ko'rsatish va bekor qilish imkoni.

Fayllar: `desktop/blender/sath/server_client.py`, `ops_server.py`, `ops_review.py`, `ops_sim.py`
Qabul mezoni: uzoq operatsiya davomida interfeys javob beradi (qo'lda tekshiriladi + headless test).
Bog'liqlik: yo'q.

### K4 — Undo/redo va IFC izchilligi

Muammo: 45 ta operatordan faqat ikkitasi undo e'lon qiladi (`ges_objects.py:175`,
`demo_plant.py:201`). Bundan ham yomoni — aynan shu ikkitasi xavfli.
`SATH_OT_add_object.execute` → `add()` (`:159`) → `ifc.ensure_project()` →
`bpy.ops.bim.create_project()` va `ifc.assign_class()` → `bpy.ops.bim.assign_class()`.
Bular xotiradagi IfcOpenShell faylini o'zgartiradi, u esa Blender ning undo stekida emas.
Ctrl+Z Blender obyektini o'chiradi va faylda tirik `GlobalId` li yetim IFC entityni qoldiradi,
u keyingi `save_project` da serverga commit qilinadi. Sensor bog'lanishlari va versiya farqlari
GUID barqarorligiga tayangani uchun bu bevosita to'g'rilik muammosi.

Yana: `ges_objects.py:50-59` — `_changed` `flush_pending` ni `bpy.app.timers` ga ro'yxatdan
o'tkazadi, u esa `rebuild()` → `bpy.ops.bim.update_representation` chaqiradi. Timer callback dan
`bpy.ops.*` chaqirish to'g'ri operator konteksti va undo steki tashqarisida bajariladi; Blender
buni ochiq taqiqlaydi. Xatolar `print()` ga yutiladi (`:45-46`).

Ish:
- IFC o'zgarishlarini undo bilan izchil qilish (o'z undo bosqichi yoki IFC o'zgarishini
  operator kontekstiga ko'chirish).
- Yetim entity larni aniqlaydigan va tozalaydigan tekshiruv (commit oldidan).
- `rebuild()` ni timer dan operator kontekstiga ko'chirish.
- Xatolarni foydalanuvchiga ko'rsatish.

Fayllar: `desktop/blender/sath/ges_objects.py`, `ifc.py`, `ops_*.py`
Qabul mezoni: Ctrl+Z dan keyin IFC da yetim entity qolmaydi (headless test).
Bog'liqlik: K2.

### K5 — Paket manifesti va platformalar

Muammo: `blender_manifest.toml:11-16` — to'rtta wheel dan ikkitasi faqat Windows x64
(`ezdxf-1.4.4-cp313-cp313-win_amd64.whl`, `assimp_py-1.2.0-cp313-cp313-win_amd64.whl`).
Manifestda `platforms` kaliti yo'q, shuning uchun Blender kengaytmani universal deb e'lon qiladi
va Linux/macOS da wheel yechishda yiqiladi. Kod `ImportError` ni ushlaydi
(`dxf_prepare.py:46`, `assimp_load.py:57`), shuning uchun addon o'rnatiladi va DXF/DWG hamda mesh
importi jimgina yo'qoladi — foydalanuvchiga sababi ko'rinmaydi.

`permissions` bloki ham yo'q, holbuki addon tashqi HTTP qiladi (`server_client.py`), fayl yozadi
va `subprocess.run` chaqiradi (`converters.py:56-76`). Blender 4.2+ kengaytmalaridan `network`,
`files` e'lon qilish kutiladi; extensions.blender.org bunday paketni rad etadi.

`blender_version_max` yo'q; wheel lar `cp313` — Blender Python 3.14 ga o'tsa jimgina buziladi.

Ish:
- `platforms = ["windows-x64"]` yoki manylinux/macos wheel lar qo'shish.
- `permissions` blokini to'ldirish.
- `blender_version_max` qo'yish.
- Bog'liqlik yo'q bo'lganda aniq xabar (jim degradatsiya emas).
- `prefs.py:15` — default server `http://localhost:8000`; loopback bo'lmagan hostga `http://`
  ni rad etish (Bearer token ochiq ketmasligi uchun).

Fayllar: `desktop/blender/sath/blender_manifest.toml`, `prefs.py`, `dxf_prepare.py`,
`assimp_load.py`
Qabul mezoni: Linux da o'rnatilganda aniq sabab ko'rsatiladi.
Bog'liqlik: yo'q.

### K6 — Build, imzo va yangilanish xavfsizligi

Muammo:
- Hech qayerda kod imzolash yo'q (`signtool`/`codesign` CI da uchramaydi).
  `build_portable.py` NSIS installerini imzosiz yasaydi; `blender-fork.yml:72` fork zip ini
  imzosiz.
- `server/ges_server/system/router.py:61-72` — `/api/desktop/latest` faqat `{version, kind, url,
  size, files}` qaytaradi, hash yo'q. `flows.download_url` (`flows.py:111`) 5 daqiqalik token
  beradi va brauzer URL ini qaytaradi; kelgan narsani hech narsa tekshirmaydi.
  `publish_desktop.py:50` yuklashda digest yozmaydi.
  Zanjir: imzosiz installer → admin sozlagan sxema bo'yicha uzatiladi → hash e'lon qilinmaydi →
  tekshiriladigan imzo yo'q.
- `blender-fork.yml:43` — `git clone --depth 1 --branch ${{ inputs.blender_tag }}`, ya'ni
  o'zgaruvchan teg, commit SHA emas. `:45` submodule pin qilinmagan. `runs-on: windows-2022`
  yangilanib turadi. `:72` `Compress-Archive` vaqt tamg'alarini kiritadi. SBOM yo'q.
  Ikki xil ish bir xil `blender_tag` da har xil binar berishi mumkin.
- `:80` `retention-days: 30` — 2-3 soatlik build natijasi 30 kunda yo'qoladi va Release ga
  ko'tarilmaydi.

Ish:
- `/api/desktop/latest` ga SHA-256; klient yuklab olgach tekshiradi.
- Windows artefaktlarini Authenticode bilan imzolash.
- Fork build ni commit SHA ga pin qilish, submodule ni pin qilish, SBOM chiqarish.
- Artefaktni GitHub Release ga ko'tarish.

Fayllar: `server/ges_server/system/router.py`, `desktop/blender/sath/flows.py`,
`desktop/build/publish_desktop.py`, `.github/workflows/blender-fork.yml`
Qabul mezoni: hash mos kelmasa yangilanish rad etiladi (test).
Bog'liqlik: yo'q.

### K7 — Desktop ni CI ga kiritish

Muammo: `ci.yml` da to'rtta ish bor (`server`, `web`, `docker`, `e2e`) — Blender addoni
qurilmaydi ham, sinalmaydi ham. `blender-fork.yml` Blender ni kompilyatsiya qiladi va bitta
smoke tekshiruvi qiladi (`:70` `import bpy`), lekin kengaytma zipini qurmaydi, o'rnatmaydi,
test ishlatmaydi. `desktop/build/build_blender_addon.py:24` lokal `blender.exe` talab qiladi
(`:17` default `~/Tools/blender-5.2/blender.exe`), ya'ni jo'natiladigan artefakt faqat
dasturchining Windows mashinasida qo'lda yasaladi.

`desktop/tests/sath_tests/` dagi 612 qator (13 modul: obyektlar, IFC ko'prigi, sim ops, monitor
ops, review ops, demo plant, twin, GUI) `blender -b --python desktop/tests/blender_headless.py`
talab qiladi va hech bir workflow da chaqirilmaydi. Natijada Blender ga bog'liq butun kod —
`ops_*.py` (~1400), `ui.py` (395), `ifc.py` (173), `sim_anim.py` (377), `ges_objects.py` (263),
`fc_engine.py` (230), `water.py` (71), `demo_plant.py` (226) — taxminan 3100 LOC CI qamrovisiz.
K2, K3, K4 dagi nosozliklar aynan shu himoyalanmagan zonada.

Ish:
- CI ga Blender ish: Blender ni yuklab olish (kesh bilan), kengaytma zipini qurish, o'rnatish,
  `blender_headless.py` ni ishlatish.
- `sath_tests` ni CI da ishlatish.
- Addon zipini artefakt sifatida chiqarish.

Fayllar: `.github/workflows/ci.yml`, `desktop/build/build_blender_addon.py`
Qabul mezoni: CI Blender testlarini ishlatadi va yiqilganda ish yiqiladi.
Bog'liqlik: yo'q. Eng arzon desktop tuzatishi — qolgan hammasini himoya qiladi.

---

## L. Ishonchlilik, xavfsizlik, deploy

### L1 — Tarmoq chegarasi va TLS

Muammo:
- `deploy/docker-compose.yml:17` — `"${GES_PORT:-8000}:8000"` shartsiz e'lon qilinadi, ya'ni
  `https` profili ishlayotganda ham Caddy TLS chegarasini aylanib o'tish mumkin.
- `Caddyfile` da HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy yo'q.
- Hech qanday tezlik cheklovi yo'q: `main.py:81-131` da middleware umuman o'rnatilmaydi,
  `pyproject.toml` da limiter yo'q, `Caddyfile` da direktiv yo'q. Ochiq qoladi: login brute force
  (`auth/router.py:52`) va autentifikatsiyasiz Argon2 CPU sarfi, buyruq spami, sim ish spami,
  ingest toshqini.

Ish:
- `https` profilida to'g'ridan-to'g'ri portni yopish (faqat ichki tarmoqqa).
- Xavfsizlik sarlavhalarini Caddyfile ga.
- Tezlik cheklovi: login (IP va hisob bo'yicha), ingest, buyruq, sim ishlari uchun alohida
  chegaralar.
- Hisobni bloklash (lockout) va MFA (kamida adminlar uchun).

Fayllar: `deploy/docker-compose.yml`, `deploy/Caddyfile`, `server/ges_server/main.py`,
`server/pyproject.toml`
Qabul mezoni: 20 ta noto'g'ri login urinishi bloklanadi (test).
Bog'liqlik: yo'q.

### L2 — Sessiya boshqaruvi

Muammo (`auth/security.py:24-45`, `config.py:25`):
- `access_token_minutes = 60*12` — 12 soatlik token, bekor qilish yo'q, refresh yo'q, logout
  yo'q, `jti` yo'q, `User` da `token_version` yo'q. Sizib chiqqan token 12 soat amal qiladi.
- `change_password` (`auth/router.py:67`) mavjud sessiyalarni bekor qilmaydi.
- `is_active` har so'rovda tekshiriladi (`auth/deps.py:25`) — bu to'g'ri, lekin rol o'zgarishi
  tekshirilmaydi: loyiha a'zoligini bekor qilish ochiq WebSocket ni to'xtatmaydi.
- `decode_access_token` (`:40`) `aud`/`iss` ni tekshirmaydi.
- `client.ts:342` — token `localStorage` da (XSS bilan o'qiladi); `client.ts:655` — WebSocket
  URL query string ida, ya'ni proksi va server loglariga tushadi.
- Parol siyosati: `min_length=4` (`auth/router.py:33`, `:42`, `:49`). Murakkablik, tarix, muddat,
  bloklash, MFA yo'q. Boshlang'ich admin paroli `data/initial-admin-password.txt` ga ochiq
  matnda yoziladi (`main.py:49`) va birinchi kirishda majburiy almashtirilmaydi.

Ish:
- Qisqa umrli access token + refresh token; `jti` va bekor qilish ro'yxati.
- Parol o'zgarishida va rol o'zgarishida barcha sessiyalarni bekor qilish (`token_version`).
- WebSocket da har N daqiqada qayta avtorizatsiya.
- Token ni query string dan olib tashlash (subprotocol yoki qisqa umrli ticket).
- Parol siyosati: uzunlik, murakkablik, boshlang'ich parolni majburiy almashtirish.

Fayllar: `server/ges_server/auth/`, `orm.py`, `monitoring/router.py`, `web/src/api/client.ts`,
`web/src/store/auth.ts`
Qabul mezoni: parol o'zgargandan keyin eski token ishlamaydi (test).
Bog'liqlik: A2.

### L3 — Ish navbati va restartga chidamlilik

Muammo: `BackgroundTasks` barcha geometriya/fragment/sim ishini olib yuradi
(`models/router.py:253`, `:257`; `drafts_router.py:292`, `:296`, `:406`, `:410`;
`twin_router.py:147`, `:151`; `sim/router.py:305`). Restartda bajarilayotgan ish yo'qoladi va
`SimJob.status` abadiy `running` bo'lib qoladi — startda yarashtirish (reconciliation) yo'q.
CFD ishchisining `next_job()` (`sim/worker.py:19`) atomik bo'lmagan SELECT, claim yoki lease yo'q
— ikki ishchi bir ishni ikki marta bajaradi.

`sim/router.py:218` — `Role.viewer` ham CFD ishini navbatga qo'ya oladi; har ish `cfd_cpus`
(default 2.0) ni `cfd_timeout_s` (3 soat) gacha egallaydi, kvota yo'q.

Ish:
- Haqiqiy navbat (Redis + arq yoki DB asosidagi navbat lease bilan).
- Ishni atomik claim qilish (`UPDATE ... WHERE status='queued' RETURNING`).
- Startda yarashtirish: egasiz `running` ishlar `failed` ga.
- Foydalanuvchi va loyiha bo'yicha kvota; CFD uchun `engineer`+ roli.
- Idempotentlik kalitlari.

Fayllar: `server/ges_server/sim/router.py`, `sim/worker.py`, `models/router.py`,
`models/drafts_router.py`, `models/twin_router.py`, `deploy/docker-compose.yml`
Qabul mezoni: restartdan keyin ishlar to'g'ri holatda; ikki ishchi bir ishni bajarmaydi (test).
Bog'liqlik: yo'q.

### L4 — WebSocket ni ko'p jarayonga tayyorlash

Muammo (`monitoring/live.py:26-51`, `monitoring/router.py:830-855`):
- `Hub` holati jarayon ichida. Ko'p ishchi yoki ko'p replikali deploy da jonli tasma, buyruq va
  jurnal tarqatish jimgina buziladi. Pub/sub backplane yo'q.
- `Hub.broadcast` (`:38`) har obunachiga ketma-ket `await ws.send_json`, timeout yo'q, navbat
  yo'q, tashlash siyosati yo'q. Bitta qotgan HMI barcha klientlar uchun tarqatishni to'xtatadi.
- `while True: await ws.receive_text()` — bo'sh turish timeout i yo'q, ping/pong muddati yo'q,
  foydalanuvchi bo'yicha ulanish chegarasi yo'q. Yarim ochiq soketlar `hub._subs` da to'planadi.

Ish:
- Redis pub/sub (yoki Postgres LISTEN/NOTIFY) backplane.
- Har klientga chegaralangan navbat, to'lganda eng eski xabarni tashlash + "sekin klient"
  diagnostikasi.
- Ping/pong va bo'sh turish timeout i.
- Foydalanuvchi bo'yicha ulanish chegarasi.

Fayllar: `server/ges_server/monitoring/live.py`, `monitoring/router.py`,
`deploy/docker-compose.yml`
Qabul mezoni: ikki replikali deployda jonli tasma ishlaydi (test).
Bog'liqlik: D1.

### L5 — Yuklash cheklovlari va parser sandbox

Muammo:
- `monitoring/router.py:392` (`import_csv`) — `await file.read()` hajm chegarasisiz, keyin
  chegarasiz `items` ro'yxati bitta tranzaksiyada. `:381` dagi 10 000 qator chegarasi faqat
  `push_readings` ga tegishli.
- `review/router.py:576` (`import_bcf`) — butun tana `bcf.py:211` dagi 50 MB tekshiruvidan
  oldin xotiraga olinadi.
- `system/router.py:125` (`desktop_upload`) — diskka oqim, chegara umuman yo'q, `max_upload_mb`
  e'tiborsiz.
- `models/mesh_import.py:111` (LibreDWG `dwg2dxf`), `:126` (ODA), `:152`
  (`blender -b <ishonchsiz.blend> --python`), `:179` (assimp), `models/fragments.py:55`
  (Node/web-ifc) — ishonchsiz CAD fayllari root sifatida, sandbox siz ishlanadi.
  `deploy/Dockerfile` da `USER` direktivi yo'q, `Dockerfile.cfd:3` ochiq `USER root`.
  `docker-compose.yml` da `cap_drop`, `no-new-privileges`, `read_only`, seccomp yo'q.
  (Aniqlik uchun: barcha argumentlar ro'yxat sifatida, `shell=True` yo'q — klassik command
  injection yo'q. Xavf parser xotira xavfsizligi va ishonchsiz faylda `blender --python`.)
- `async def` endpointlarda bloklovchi ish: `import_csv` (`monitoring/router.py:389`),
  `import_bcf` (`review/router.py:573`), `desktop_upload` (`system/router.py:117`) — har biri
  butun serverni, jumladan WebSocket tarqatishni bloklaydi.

Ish:
- Barcha yuklashlarga oqimli hajm chegarasi (o'qish paytida, keyin emas).
- CAD/mesh konvertatsiyani alohida konteynerda, root siz, tarmoqsiz, CPU/xotira chegarasi bilan.
- `USER` direktivi, `cap_drop: ALL`, `no-new-privileges`, `read_only` root fayl tizimi.
- Bloklovchi ishni `run_in_threadpool` ga yoki ishchiga ko'chirish.

Fayllar: `server/ges_server/monitoring/router.py`, `review/router.py`, `system/router.py`,
`models/mesh_import.py`, `deploy/Dockerfile`, `deploy/Dockerfile.cfd`, `deploy/docker-compose.yml`
Qabul mezoni: hajmi oshgan yuklash 413 beradi va xotirani bosmaydi (test).
Bog'liqlik: yo'q.

### L6 — Zaxira, tiklash, RTO/RPO

Muammo: `deploy/backup.sh` Docker hajmini so'rovga ko'ra tar qiladi. Jadval yo'q, shifrlash yo'q,
tashqi nusxa yo'q, tiklash tekshiruvi yo'q. Arxivda DB bilan birga `secret.key` ham ochiq
saqlanadi. RTO va RPO hech qayerda yozilmagan.

Ish:
- Jadvalli zaxira, shifrlangan, tashqi joyga nusxa.
- Tiklashni davriy tekshirish (avtomatik test tiklash).
- RTO/RPO ni hujjatlashtirish va ularga mos texnik yechim.
- Sirlarni zaxiradan ajratish yoki alohida shifrlash.

Fayllar: `deploy/backup.sh`, yangi `deploy/restore.sh`, `docs/admin.md`
Qabul mezoni: tiklash protsedurasi hujjatlashtirilgan va sinalgan.
Bog'liqlik: yo'q.

### L7 — IEC 62443 zonalari va hujjatlashtirish

Muammo: amaldagi topologiya aslida mantiqiy — gateway SCADA tarmog'ida turadi va Sath ga
chiquvchi HTTPS qiladi, bu to'g'ri L3→L3.5 kanali. Lekin bu tasodifiy, hujjatlashtirilmagan;
zona/kanal modeli, xavf bahosi, SL-T tayinlashi yo'q.

Ish:
- Zona va kanal diagrammasi: qaysi komponent qaysi zonada, qaysi kanal orqali, qanday protokol,
  qaysi yo'nalishda.
- Har kanal uchun xavfsizlik darajasi maqsadi (SL-T).
- Gateway qayerga o'rnatilishi va o'rnatilmasligi bo'yicha aniq ko'rsatma.
- Tarmoq segmentatsiyasi va firewall qoidalari namunasi.
- O'zbekiston KAI (kritik axborot infratuzilmasi) talablari bo'yicha ro'yxatga olish,
  muvofiqlikni baholash va hodisa haqida xabar berish tartibi — hozir hech biri ko'rib
  chiqilmagan. `models/dem.py` tashqi AWS endpointiga murojaat qiladi — ma'lumot joylashuvi
  nuqtai nazaridan tekshirilishi kerak.

Fayllar: yangi `docs/security-zones.md`, `deploy/README.md`, `docs/admin.md`
Qabul mezoni: hujjat mavjud va deploy uni aks ettiradi.
Bog'liqlik: L1.

### L8 — Yuqori ishonchlilik

Muammo: bitta `ges` xizmati, SQLite default, fon sikli jarayon ichida
(`monitoring/background.py:61`), `Hub` jarayon xotirasida. Ikki replikani load balancer ortida
ishga tushirib bo'lmaydi.

Ish:
- Fon vazifalarini alohida xizmatga ajratish (bitta nusxa, leader election yoki alohida
  konteyner).
- Ko'p replikali API (L4 backplane bilan).
- Postgres replikatsiyasi va failover (D1 dan keyin).
- Sog'liq va tayyorlik (health/readiness) endpointlari.

Fayllar: `deploy/docker-compose.yml`, `server/ges_server/main.py`,
`server/ges_server/monitoring/background.py`
Qabul mezoni: bitta replika o'chirilganda xizmat uzilmaydi.
Bog'liqlik: D1, L4.

---

## M. Sifat infratuzilmasi (davomiy)

### M1 — API sifati

Muammo: API versiyalash yo'q (tekis `/api/...`, `main.py:85-101`), global exception handler yo'q,
izchil xato konverti yo'q (yalang'och `{"detail": ...}`), `operation_id` lar yo'q, sahifalash
kontrakti hujjatlashtirilmagan. `pending_commands` (`control.py:195`) `response_model` siz, ya'ni
OpenAPI da turi yo'q. `Content-Disposition` foydalanuvchi kiritmasidan quriladi
(`drafts_router.py:617`, `review/router.py:568`, `models/router.py:376`, `:451`) — qo'shtirnoq
sarlavhani buzadi, CRLF esa h11 da 500 beradi.

Ish:
- `/api/v1/` prefiksi.
- Global exception handler va izchil xato konverti (kod, xabar, tafsilot).
- Barcha endpointlarga `response_model` va `operation_id`.
- `Content-Disposition` uchun RFC 5987 `filename*` va tozalash.
- Sahifalash kontrakti hujjatlashtirilgan.

Fayllar: `server/ges_server/main.py`, barcha routerlar, `web/src/api/client.ts`
Qabul mezoni: OpenAPI sxemasi to'liq turlangan.
Bog'liqlik: D4.

### M2 — Yetishmayotgan testlar

Qamrovi yaxshi, lekin quyidagilar yo'q:
- Autentifikatsiyasiz yoki begona loyiha WebSocket ulanishi rad etilishi
  (`test_monitoring.py:223` faqat muvaffaqiyatli yo'lni sinaydi).
- Noto'g'ri yoki yo'q `X-Ingest-Key` (`/readings` va ikkala gateway endpointi uchun);
  `test_scada.py:90` faqat muvaffaqiyatni sinaydi.
- Buyruq qiymati chegaralari, takroriy ochiq buyruq poygasi, `sent` buyruqni bekor qilish.
- Token muddati, parol o'zgarishidan keyin token ishlatish, rol bekor qilingandan keyin token.
- Yuklashni suiiste'mol qilish: katta CSV/BCF, buzuq IFC/DXF, yuk tashuvchi `.blend`.
- Parallellik: bir vaqtda commit (A5), bir vaqtda buyruq (B1).
- `ensure_columns()` eski sxemani migratsiya qilishi (A2 dan keyin — Alembic testi).

Fayllar: `server/tests/`
Qabul mezoni: yuqoridagi har biri uchun test mavjud.
Bog'liqlik: tegishli vazifalar.

### M3 — e2e qamrovini kengaytirish

Muammo: `web/e2e/flow.spec.ts` (7 test) keng — login, viewer, CR approve/merge, clash/QTO,
alarm ack, sim, 3D draft commit — lekin mavjudlikni tekshiradi, to'g'rilikni emas.
`:120-121` "Kvitlash" ni bosadi va "kvitlangan" matni paydo bo'lishini tekshiradi; ustuvorlik
tartibi, toshqin xatti-harakati, eskirish ko'rsatilishi, qayta ulanish tekshirilmaydi.

Ish (E4 simulyatori ustida):
- Alarm toshqini stsenariysi: ustuvorlik tartibi, toshqin rejimi, ovoz.
- Aloqa uzilishi: LIVE → STALE → OFFLINE o'tishi.
- Sifat: bad sifatli qiymat interfeysda qanday ko'rinadi.
- Boshqaruv: select → execute → readback, chegaradan tashqari qiymat rad etilishi.
- Blokirovka: shart bajarilmaganda buyruq rad etilishi.

Fayllar: `web/e2e/`
Qabul mezoni: har stsenariy CI da ishlaydi.
Bog'liqlik: E4, F bosqichi.

---

## N. Claude Code bilan ishlash tartibi

### N1 — Vazifani berish shakli

Har vazifa alohida sessiyada bajarilsin. Berish shakli:

```
docs/roadmap-bim-scada.md dagi <ID> vazifasini bajar.
Avval tegishli fayllarni o'qi, keyin reja tuz, keyin yoz.
Qabul mezonidagi testlarni ham yoz.
Tugagach: ruff check . && pytest server/tests sim/tests desktop/tests
va cd web && npm run typecheck && npm test
```

### N2 — Har vazifa uchun majburiy shartlar

- Sxema o'zgarsa — Alembic migratsiyasi (A2 dan keyin), backfill bilan.
- Xatti-harakat o'zgarsa — test. Qabul mezonida ko'rsatilgan test majburiy.
- Yangi tashqi bog'liqlik — `pyproject.toml` yoki `package.json` ga, litsenziyasi tekshirilgan.
- Foydalanuvchiga ko'rinadigan matn — o'zbekcha, mavjud uslubga mos.
- Xavfsizlikka oid o'zgarish — audit yozuvi (A4).
- Hisoblash o'zgarishi — manba (norma, bandi, nashr) izohda.

### N3 — Tugallanganlik mezoni

Vazifa tugagan hisoblanadi, agar:
1. Qabul mezoni bajarilgan va tegishli test o'tadi.
2. `ruff check .` toza.
3. `pytest server/tests sim/tests desktop/tests` o'tadi.
4. `npm run typecheck && npm test && npm run lint` o'tadi (F10 dan keyin lint ham).
5. Tegishli hujjat yangilangan (`docs/qollanma.md`, `docs/admin.md`, `README.md`).
6. Yangi cheklov yoki taxmin bo'lsa — shu hujjatda belgilangan.

### N4 — Nima qilinmasin

- Sinalmagan holda muhandislik formulasini o'zgartirish.
- Xatoni `except` bilan yutib, natija o'rniga default qaytarish.
- Xavfsizlikka oid tekshiruvni "vaqtincha" o'chirish.
- Mavjud `sync_blender.py` nazorati ostidagi fayllarni qo'lda tahrirlash.
- Yangi fizika dvigatelini yozish — `sim/ges_sim` yagona manba.

---

## O. Vendorsiz qilinmaydigan ishlar

Bularni ichki kuch bilan qilishga urinmaslik kerak:

- IEC 61850 (MMS klienti, SCL/SCD o'qish, 61850-7-410 gidro mantiqiy tugunlari). Sertifikatlangan
  steklar tijorat; libiec61850 ikki litsenziyali. GOOSE publisher ni umuman qilmaslik — u L2
  tarmoq darajasi va real vaqt xususiyatlarini talab qiladi, Python xizmati bera olmaydi.
- Dispetcher markazi bilan aloqa (ICCP/TASE.2 yoki milliy tarmoq operatorining 104 talabi) —
  bu shartnoma bo'yicha topshiriq, loyihalanadigan funksiya emas.
- Issiq rezervli server jufti, soniyadan kam failover bilan.
- Tijorat/hisob-kitob o'lchovi — sertifikatlangan uskuna va VEE jarayonlari.
- IEC 62443 bo'yicha rasmiy baholash va ZRU-764 bo'yicha xavfsizlik dasturiy ta'minotini
  muvofiqlikka baholash.
- Bir tomonlama shlyuz (data diode), agar qat'iy bir yo'nalishli SCADA→BIM talab qilinsa.
- Operator o'quv simulyatori (to'liq dinamik model bilan) — E4 dan ancha kengroq.
- IFC4.3 da to'g'on modellashtirish uslubiyati — sxemani biladigan mutaxassis kerak.

---

## P. Roadmapdan tashqari — "max" daraja uchun qo'shimchalar

Bular 2026-09-21 auditidan keyin, BIM SCADA maqsadini to'liq yopish uchun qo'shildi. Har biri o'z
bog'liqligidan keyin bajariladi.

### P1 — OPC UA server chiqishi
Sath hisoblagan teglar (`TWIN.*`, `ML.*`, `HEALTH.*`) ni SCADA/HMI o'qishi uchun faqat-o'qish OPC UA
serveri (`asyncua`), L3 → L2 yo'nalishi, sertifikat + foydalanuvchi autentifikatsiyasi, teg bo'yicha
ruxsat. Yozish yo'q (B bosqichi qoidalari buzilmasin).
Fayllar: yangi `server/ges_server/monitoring/opcua_server.py`, `config.py`, `docs/admin.md`
Qabul mezoni: UaExpert bilan teg o'qiladi; yozish urinishi rad etiladi (test).
Bog'liqlik: E, A1.

### P2 — Ekspluatatsiya hisobotlari
IEEE 762 mavjudlik ko'rsatkichlari (EAF, FOR, SOF), sutkalik/oylik ishlab chiqarish, suv sarfi, ombor
rejimi, alarm KPI (C4) — PDF/XLSX; davlat hisobot shakllari uchun shablon.
Fayllar: `server/ges_server/monitoring/historian.py`, yangi `monitoring/reports.py`, web hisobot sahifasi
Qabul mezoni: oylik hisobot generatsiya qilinadi va ko'rsatkichlar ma'lum ma'lumotda qo'lda hisob bilan mos.
Bog'liqlik: D2, C4.

### P3 — To'g'on xavfsizligi asbob-uskunalari
Pyezometr, sizish o'lchagich (weir), inklinometr, cho'kish reperi, seysmograf — `Sensor.kind` turlari;
J natijalaridan (ruxsat etilgan ko'tarish bosimi, sizish sarfi) avtomatik alarm chegarasi (C1 ta'rifi);
ICOLD Bulletin 158 monitoring tavsiyalari.
Fayllar: `orm.py`, `monitoring/live.py`, `sim/safety.py`, web faceplate
Qabul mezoni: pyezometr qiymati hisoblangan chegaradan oshsa alarm (test).
Bog'liqlik: C1, J1, J7.

### P4 — Kiruvchi oqim prognozi
`rainfall.py` + ob-havo prognozi (API yoki qo'lda) → 3–7 kunlik kiruvchi oqim va ombor rejimi tavsiyasi;
`dispatch.py` bilan bog'lanadi; prognoz va haqiqiy oqim solishtiruvi (I3 validatsiya yozuvi).
Fayllar: `sim/ges_sim/rainfall.py`, `dispatch.py`, yangi `monitoring/forecast.py`
Qabul mezoni: prognoz virtual sensor sifatida `TWIN.INFLOW_FC` ga chiqadi; xatolik trendi ko'rinadi.
Bog'liqlik: I1, J9.

### P5 — Bildirishnoma eskalatsiyasi
Navbatchilik jadvali, Telegram/SMS kanali, ack bo'lmasa vaqt bo'yicha eskalatsiya, alarm toshqinida
jamlangan xabar (C5 bilan), yetkazilganlik jurnali.
Fayllar: `server/ges_server/notify.py`, `orm.py`, web sozlamalar
Qabul mezoni: kritik alarm 10 daqiqada ack qilinmasa ikkinchi darajaga eskalatsiya (test).
Bog'liqlik: C2, C5.

### P6 — Ko'p stansiya (fleet) ko'rinishi
Bir necha loyiha uchun umumiy Level 0 ekran; kaskad bog'lanishi (yuqori GES chiqishi = quyi GES
kiruvchi oqimi), umumiy alarm hisoblagichlari.
Fayllar: `web/src/pages/operator/L0Fleet.tsx`, `projects/router.py`
Qabul mezoni: ikki loyiha kaskadda bog'lanadi va quyi loyiha egizagi yuqori chiqishini oladi (test).
Bog'liqlik: F2, I2.

### P7 — Historian tashqi o'qish API
Grafana JSON datasource ga mos REST (`/api/v1/historian/query`), teg bo'yicha ruxsat, sahifalash (D4),
sifat bayrog'i bilan. OPC UA HA — P1 bilan birga.
Fayllar: `monitoring/historian.py`, yangi `monitoring/historian_router.py`
Qabul mezoni: Grafana panel Sath dan trend chizadi (qo'lda) + API testi.
Bog'liqlik: D4, A1.

### P8 — Operator mashqi va replay
E4 yozib olingan stsenariyni interfeysda vaqt boshqaruvi bilan ijro etish; mashq rejimi belgisi (ISA-101
bo'yicha aniq ajratilgan), mashq davomida buyruqlar simulyatorga ketadi.
Fayllar: `deploy/simulator/`, `web/src/pages/operator/Training.tsx`
Qabul mezoni: mashq rejimida haqiqiy gateway ga birorta buyruq ketmaydi (test).
Bog'liqlik: E4, F2, F8.

Oxirgi yangilanish: 2026-09-21
