# Sath — kompaniya ichki BIM platformasi rejasi

## Kontekst

Kompaniya ishchilari uchun (sotilmaydi) GES (gidroelektrostansiya) obyektlarini 3D BIM modellash, simulyatsiya qilish, versiyalash va rol orqali tasdiqlashga mo'ljallangan yengil, o'rnatish oson dastur kerak. Papka bo'sh — loyiha noldan boshlanadi.

Foydalanuvchi qarorlari:
- **Web + desktop**, ikkalasi ham **bitta serverga** ulanadi. Server = fayllar + versiyalar + tasdiqlash (GitHub kabi).
- **To'liq CAD tahrirlash** — noldan emas, **FreeCAD 1.0** yadrosi ustiga o'z dastur.
- Simulyatsiya: **suv ombori rejimi, turbina/quvvat, CFD oqim, real vaqt monitoring** (bosqichma-bosqich).
- Version control **o'zimiz yozamiz** (yengil), Speckle/BIMserver yo'q.
- Oddiy login/parol, ko'lam hali noma'lum → kichikdan boshlab kengaytiriladigan.
- Til: Python (asosiy), C++ faqat FreeCAD kerak bo'lganda.

Litsenziya: ichki foydalanish — GPL/LGPL/AGPL komponentlar bemalol ishlatiladi.

## Holat (2026-09-14, kechqurun)

| Bosqich | Holat | Izoh |
|---|---|---|
| 0 — Skelet | ✅ | monorepo, CI, Docker |
| 1 — "BIM uchun GitHub" MVP | ✅ | auth/rollar, loyihalar, modellar, versiyalar, web viewer, desktop ochish/commit |
| 2 — Taqriz va tasdiqlash | ✅ | CR oqimi, ifcdiff (3D rang), BCF issue lar (IFC fazosidagi viewpoint), BCF 2.1 eksport/import, email bildirishnomalar (SMTP), audit |
| 3 — AutoCAD uslubidagi UX | ✅ | web: buyruqlar qatori, sichqoncha odatlari, qatlamlar, o'lchash, kesim, saqlangan ko'rinishlar (VSAVE/VIEW); desktop (FreeCAD 1.1 da sinalgan): FreeCAD Dark paketi, CAD navigatsiya, metr birliklar, GES obyektlar ikonkalar bilan |
| 4 — Simulyatsiya I | ✅ | ges_sim (suv ombori, quvur, turbina, 5 rejim), server API, web panel (grafiklar, vaqt slayderi, 3D suv sathi) |
| 5 — Monitoring | ✅ | sensorlar, HTTP/CSV/MQTT ingest, WebSocket jonli, 3D rang, gateway (Modbus/OPC UA/CSV); **SCADA darajasi**: dispetcher paneli (mimik sxema, KPI, trendlar), alarm jurnali + kvitlash, historian (soatlik agregat, retention), hisobotlar (CSV), bildirishnomalar (ilova ichi + email), audit ko'rish |
| 6 — CFD | ✅ | OpenFOAM case generatorlar (quvur wedge simpleFoam, suv tashlagich interFoam, **model geometriyasi STL → snappyHexMesh + simpleFoam**), Docker/worker runner, natijalar (grafik, 2D xarita, 3D tekislik, kuchlar). Docker da sinalgan |
| 7 — Sayqal va tarqatish | ✅ | Docker (+ HTTPS Caddy profili), qo'llanmalar; desktop — **FreeCAD 1.1.3 forki** (brending, Mod/Ges, NSIS installer + zip, CI), serverdan tarqatiladi, yangilanish tekshiruvi; **katta IFC — server tomonda fragments** (.frag, Node); Playwright e2e |
| + BIM tekshiruvlar | ✅ | to'qnashuvlarni aniqlash (clash), hajm-miqdor hisobi (QTO) — web paneli, CSV |
| + UI | ✅ | Blender/3ds Max uslubidagi ish maydoni (menyular, ish maydonlari, shading Solid/Wire/X-ray/Rendered, gizmo, kamera rejimlari, kesim qutisi, rang sxemalari, hover, render, outliner qidiruv/ko'z, yo'riqnoma) |
| + SCADA tenglik | ✅ | dispetcher roli, alarm ustuvorligi/ovoz, supervisory control (buyruqlar → gateway), smena jurnali, kunlik hisobot emaili, vaqt mashinasi |
| + Raqamli egizak | ✅ | jonli holat ↔ model (kutilgan quvvat/og'ish/FIK, virtual sensorlar, og'ish alarmlari), 3D jonli suv sathi, simulyatsiya jonli holatdan, aktivlar (ish soatlari, texnik xizmat) |
| + Versiya boshqaruvi | ✅ | qayta tiklash (revert), izoh/yorliq (teg), istalgan ikki versiya farqi |
| + Simulyatsiya katalogi | ✅ | 17 tur (gidravlik zarba, minora, HYGOV, to'g'on barqarorligi, yorilish, filtratsiya, to'g'on turi, zilzila, yog'in→toshqin/GLOF, toshqin/yorilish, ko'chki to'lqini, loyqa, dispatch, maxsus formulalar), maydon pasporti, materiallar katalogi |
| + Web 3D modellash | ✅ | Shift+A element qo'shish (primitiv/GES inshooti), G/R/S, Pset, IFC ga commit (yangi versiya), simulyatsiyaga uzatish |
| + Toshqin prognozi, ish buyruqlari | ✅ | yog'in prognozi + jonli sath → sath/tavsiya; CMMS-lite (KPI MTTR/MTBF, avto buyruq sog'liqdan), 3D sog'liq rangi |
| + Ehtiyot qismlar, elektr, ML nuqtasi | ✅ | ombor (kirim/sarf, min zaxira), transformator IEC 60076-7 (sim + sog'liq), `/ml/predictions` → ML.* sensorlar |
| + Holat monitoringi | ✅ | sog'liq indeksi (ISO 20816-5, harorat, FIK trendi, anomaliya, RUL, kavitatsiya), «nima bo'lsa», optimal rejim |

Ma'lum cheklovlar: desktop FreeCAD 1.1.3 forki (yadro C++ o'zgartirilmagan; paket hozircha rasmiy 1.1.3 binaridan overlay bilan yig'iladi, to'liq kompilyatsiya — fork CI);
katta IFC (>100 MB) — serverdagi fragments konvertatsiya va geometriya tahlili bir necha daqiqa olishi mumkin (fonda);
clash detection 1500 elementdan katta modellarda faqat bbox darajasida;
GES obyektlari IFC ga tessellyatsiya (uchburchak) shaklida chiqadi — fayl hajmi katta bo'lishi mumkin.

---

## Arxitektura (3 qism + 1 umumiy kutubxona)

```
┌──────────────────────┐       ┌──────────────────────┐
│  DESKTOP (FreeCAD)   │       │   WEB (brauzer)      │
│  to'liq CAD, GES     │       │   ko'rish, taqriz,   │
│  obyektlar, commit,  │       │   tasdiqlash,        │
│  simulyatsiya        │       │   simulyatsiya,      │
│                      │       │   monitoring         │
└──────────┬───────────┘       └──────────┬───────────┘
           │  REST + WebSocket (JWT)      │
           └──────────────┬───────────────┘
                          ▼
              ┌──────────────────────────┐
              │  SERVER (Python FastAPI) │
              │  auth/rollar, loyihalar, │
              │  versiyalar, ifcdiff,    │
              │  tasdiqlash oqimi, BCF,  │
              │  simulyatsiya joblari,   │
              │  monitoring ingest       │
              │  SQLite→Postgres, fayllar│
              └──────────────────────────┘
                          │ (ixtiyoriy)
              ┌──────────────────────────┐
              │  CFD WORKER (OpenFOAM,   │
              │  Docker, Linux)          │
              └──────────────────────────┘
```

Server web ilovaning tayyor build'ini o'zi tarqatadi → ishchiga **bitta URL** yetadi. Desktop — portable zip/installer, birinchi ishga tushganda server manzili + login so'raydi.

### Texnologiyalar

| Qism | Tanlov | Sabab |
|---|---|---|
| Server | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic, `uvicorn` | Yengil, OpenAPI hujjat avtomatik, IfcOpenShell bilan bir tilda |
| DB | SQLite (default) → Postgres (env orqali almashadi) | O'rnatish nol sozlash; kengayganda Postgres |
| Fayl xotira | Lokal disk `data/` (content-addressed, sha256) | Yengil; keyin MinIO qo'shsa bo'ladi |
| IFC | IfcOpenShell (`ifcopenshell`, `ifcdiff`, `ifcpatch`) | Sanoat standarti, Python |
| Web | React 18 + TypeScript + Vite, `@thatopen/components` (Three.js), `web-ifc`, Zustand, Tailwind | MIT, IFC brauzerda, UI to'liq bizniki |
| Desktop | FreeCAD 1.0 (portable) + o'z addon (Python) + preset | Tayyor CAD/BIM yadro, Draft buyruqlar qatori, IFC (IfcOpenShell ichida) |
| Simulyatsiya | `ges_sim` Python paketi (numpy, scipy, pandas), OpenFOAM (Docker) | Server va desktopda bir xil kod |
| Monitoring | `paho-mqtt`, `asyncua` (OPC UA), `pymodbus`, CSV import | Umumiy SCADA protokollari |
| Fon vazifalar | FastAPI BackgroundTasks + `jobs` jadvali → kengayganda `arq`/Redis | Boshida qo'shimcha servis kerak emas |
| Tarqatish | Docker Compose (server), Inno Setup / zip (desktop) | Bitta buyruq bilan o'rnatish |

### Repo tuzilmasi (monorepo)

```
BIM/
├── server/            # FastAPI
│   ├── ges_server/
│   │   ├── main.py, config.py, db.py
│   │   ├── auth/       (jwt, users, roles, permissions)
│   │   ├── projects/   (projects, members)
│   │   ├── models/     (models, versions, storage, ifc_diff)
│   │   ├── review/     (change_requests, approvals, state machine, issues/BCF)
│   │   ├── sim/        (job runner, endpoints → ges_sim)
│   │   ├── monitoring/ (sensors, readings, ingest adapters, websocket)
│   │   └── audit.py
│   ├── tests/
│   ├── Dockerfile, pyproject.toml
├── web/               # React + ThatOpen
│   ├── src/
│   │   ├── viewer/     (scene, ifc loader, selection, section, measure, layers, diff coloring)
│   │   ├── ui/         (command line, panels, ribbon, shortcuts, theme)
│   │   ├── pages/      (login, projects, model, versions, review, issues, sim, monitoring, admin)
│   │   └── api/        (openapi-generated client)
│   └── tests/ (vitest, playwright)
├── desktop/           # FreeCAD addon + distributsiya
│   ├── GesWorkbench/   (InitGui.py, commands/, objects/, panels/, server_client.py)
│   ├── preset/         (user.cfg: dark theme, keymap, toolbars)
│   ├── build/          (portable zip yig'ish, Inno Setup skripti)
│   └── tests/          (freecadcmd headless)
├── sim/               # ges_sim paketi (umumiy)
│   ├── ges_sim/ reservoir.py, turbine.py, penstock.py, cfd/, monitoring/
│   └── tests/
├── deploy/            # docker-compose.yml, .env.example, backup.sh
└── docs/              # o'rnatish, foydalanuvchi qo'llanmasi, API
```

### Ma'lumotlar modeli (asosiy jadvallar)

- `users`, `roles` (Admin, Tasdiqlovchi, Muhandis, Ko'ruvchi), `project_members(project, user, role)`
- `projects` (GES obyekt: nom, joylashuv, tavsif)
- `models` (loyihadagi model: "To'g'on", "Mashina zali"…)
- `versions` (model_id, number, parent_id, file_sha256, size, author, message, **state**: `wip | shared | published | archived`, created_at) — o'zgarmas (immutable)
- `change_requests` (model_id, version_id, author, title, status: `open | changes_requested | approved | rejected | merged`, reviewers[]) — GitHub PR analogi
- `reviews` (change_request_id, reviewer, decision, comment)
- `issues` (BCF: title, status, priority, assignee, viewpoint{camera, selected_guids, section}, version_id) + `issue_comments`
- `version_diffs` (from, to, json: added/removed/changed GUID lar) — kesh
- `sim_jobs` (type, version_id, params json, status, progress, result_path, log)
- `sensors` (project, name, protocol, address, element_guid, unit), `readings` (sensor_id, ts, value) — kengayganda TimescaleDB
- `audit_log` (kim, nima, qachon, obyekt)

### Tasdiqlash oqimi (ISO 19650 soddalashtirilgan)

```
Muhandis: commit → version(state=wip)
Muhandis: "Tasdiqqa yuborish" → change_request(open), version→shared
Tasdiqlovchi/taqrizchi: 3D da ko'radi, diff ko'radi, BCF issue ochadi
   ├─ "O'zgartirish so'raladi" → changes_requested → muhandis yangi versiya commit qiladi (CR ga bog'lanadi)
   └─ "Tasdiqlash" → approved → merged → version→published (avvalgi published→archived)
Har qadam audit_log ga yoziladi; ruxsatlar rolga qarab (faqat Tasdiqlovchi approve qila oladi).
```

---

## Bosqichlar

Har bosqich o'zicha ishlaydigan natija beradi. Vaqtlar 1–2 dasturchi uchun taxminiy.

### 0-bosqich — Skelet (1–2 hafta)
- Monorepo, `pyproject` lar, Vite loyiha, Docker Compose, CI (GitHub Actions/GitLab CI: pytest, vitest, lint).
- `ges_server` ishga tushadi, `/docs` ochiladi, web build serverdan tarqatiladi.
- FreeCAD 1.0 portable yuklab olib `desktop/build` skripti bilan addon qo'shilgan zip yig'iladi.
- **Natija:** `docker compose up` → brauzerda bo'sh ilova; desktop zip ochiladi.

### 1-bosqich — "BIM uchun GitHub" MVP (6–8 hafta)
Server:
- Auth (JWT, parol hash), foydalanuvchi/rol CRUD (admin), loyiha va a'zolar.
- Model/versiya: IFC yuklash (sha256 dedup), yuklab olish, versiya ro'yxati, commit xabari, parent zanjiri.
- IfcOpenShell bilan yuklashda validatsiya + metadata (schema, element soni, storey lar).
- Audit log.
Web:
- Login, loyiha ro'yxati, model sahifasi, **IFC viewer** (ThatOpen: yuklash, orbit/pan/zoom, model daraxti, xususiyatlar paneli, tanlash, yashirish/izolyatsiya).
- Versiyalar ro'yxati, istalgan versiyani ochish.
Desktop (FreeCAD addon):
- Server manzili + login dialogi, loyiha/model brauzeri.
- "Ochish" (versiyani yuklab, FreeCAD BIM workbench da ochish), "Commit" (IFC eksport → yuklash + xabar).
- **Natija:** Muhandis desktopda chizadi, commit qiladi; hamma webda ko'radi, tarix bor.

### 2-bosqich — Taqriz va tasdiqlash (5–6 hafta)
- `ifcdiff` bilan versiyalar farqi → JSON kesh → webda **diff rejimi** (yashil/qizil/sariq elementlar, ro'yxat).
- Change request: yaratish, taqrizchilar, holatlar, approve/reject, merge → published.
- BCF issues: 3D nuqtaga bog'langan izoh (kamera + tanlangan elementlar saqlanadi), holat, ijrochi, izohlar; BCF-XML eksport/import (boshqa dasturlar bilan almashish).
- Desktopda: CR ro'yxati, issue larni 3D da ko'rish (kameraga o'tish), issue ochish.
- Bildirishnomalar: ilova ichida (+ email SMTP ixtiyoriy).
- **Natija:** To'liq tasdiqlash aylanmasi ishlaydi, hamma qadam auditda.

### 3-bosqich — AutoCAD uslubidagi UX (4–6 hafta)
Web viewer:
- Qora fon, crosshair, sichqoncha odatlari (g'ildirak zoom, o'rta tugma pan, Shift+o'rta orbit), `F8` ortho kabi tanish tugmalar.
- **Buyruqlar qatori** (`ZOOM`, `HIDE`, `ISOLATE`, `MEASURE`, `SECTION`, `LAYER`, `FIND` …) + avtoto'ldirish, Enter takror.
- Layer paneli (IFC tur/storey/tizim bo'yicha), Properties paneli, o'lchash (masofa, maydon), kesim tekisliklari, ko'rinishlar (saved views).
Desktop:
- FreeCAD preset: dark tema, AutoCAD keymap, ribbon-ga o'xshash toolbar, Draft buyruqlar qatori default ochiq, kerakmas workbench lar yashirilgan.
- **GES parametrik obyektlar** (Python FeaturePython): To'g'on, Suv ombori, Suv tashlagich, Suv qabul qilgich, Bosimli quvur (penstock), Turbina agregati, Mashina zali, Transformator — xususiyatlari (napor, sarf, quvvat, diametr…) IFC ga PropertySet sifatida yoziladi.
- **Natija:** AutoCAD ga o'rgangan ishchi 1 kunda o'tadi.

### 4-bosqich — Simulyatsiya I: suv ombori + turbina/quvvat (5–6 hafta)
`ges_sim`:
- `reservoir`: suv balansi — kiruvchi gidrograf, hajm–sath egri chizig'i, tashlama qoidalari, suv tashlagich sarf egri chizig'i → sath/hajm/tashlama vaqt qatori.
- `penstock`: napor yo'qotishi (Darcy–Weisbach), sof napor.
- `turbine`: P = η·ρ·g·Q·H, turbina turi (Francis/Kaplan/Pelton) uchun soddalashtirilgan FIK egri chizig'i, agregatlar orasida yuk taqsimoti, sutkalik/yillik ishlab chiqarish.
- Parametrlar avtomatik modeldagi GES obyektlaridan (PropertySet) olinadi, foydalanuvchi to'ldiradi/tuzatadi.
Server: `sim_jobs` (yaratish, holat, natija JSON/Parquet), natija versiyaga bog'lanadi.
Web/desktop:
- Kirish formasi (gidrograf CSV/qo'lda), "Ishga tushirish", grafiklar (sath, sarf, quvvat), **3D da suv sathi tekisligi vaqt slayderi bilan animatsiya**, agregatlar holati rang bilan.
- **Natija:** Modeldan to'g'ridan-to'g'ri rejim va quvvat hisobi.

### 5-bosqich — Real vaqt monitoring (4–5 hafta)
- Sensor ro'yxati, IFC element GUID ga bog'lash (3D da tanlab).
- Ingest adapterlar: MQTT, OPC UA, Modbus TCP, CSV/REST import; `readings` ga yozish; chegaralar/alarm.
- WebSocket orqali jonli qiymatlar → 3D da elementlar rangi/yorliqlari, dashboard (grafiklar, alarm ro'yxati).
- Tarix so'rovlari; kengayganda TimescaleDB.
- **Natija:** Digital twin — SCADA dan sath, sarf, quvvat 3D modelda jonli.

### 6-bosqich — Simulyatsiya II: CFD (6–10 hafta, alohida Linux/Docker worker)
- `cfd_worker` konteyner: OpenFOAM, `ges_sim.cfd` case shablonlari (suv tashlagich, suv qabul qilgich, quvur) — geometriya FreeCAD dan STL eksport, mesh (`snappyHexMesh`/`cfMesh`), `interFoam`/`simpleFoam`.
- Job navbat (bu bosqichda `arq` + Redis), progress, log, bekor qilish.
- Natija: VTK → yengil format (glTF + skalyar maydon) → web/desktopda tezlik/bosim rangli, oqim chiziqlari.
- **Natija:** Og'ir hisoblar serverda, ko'rish yengil klientda.

### 7-bosqich — Sayqal va tarqatish (3–4 hafta)
- Desktop installer (Inno Setup), avto-yangilanish (server `/desktop/latest` dan versiya tekshiradi).
- Zaxira skripti (`data/` + DB), tiklash hujjati, HTTPS (Caddy/Traefik ixtiyoriy).
- Foydalanuvchi qo'llanmasi (o'zbek), admin qo'llanmasi, video darslar.
- Yuklama testi (katta IFC: server tomonda IFC → fragments konvertatsiya, keshlash).

---

## O'rnatish tajribasi (maqsad)

**Server (admin, 1 marta):**
```
git clone … && cd deploy
cp .env.example .env      # SECRET_KEY, admin parol
docker compose up -d      # server + web bitta konteyner; postgres/cfd ixtiyoriy profil
```
Brauzer: `http://server:8000` → admin kiradi → foydalanuvchi va loyiha yaratadi.

**Ishchi:** brauzerda URL ochadi (ko'rish/taqriz/simulyatsiya); chizish uchun `Sath-Desktop-x.y.zip` ochib `Sath.exe` ishga tushiradi, server manzili + login kiritadi.

---

## Tekshirish (har bosqichda)

- `server/`: `pytest` — auth, ruxsatlar (har rol uchun rad/ruxsat), versiya zanjiri, state machine o'tishlari, ifcdiff namunaviy IFC juftlarida, sim modellar analitik yechim bilan solishtiriladi (masalan doimiy sarfda sath).
- `web/`: `vitest` (command parser, diff coloring), Playwright e2e — login → model ochish → CR yaratish → approve.
- `desktop/`: `freecadcmd -c` headless testlar — GES obyekt yaratish → IFC eksport → PropertySet mavjudligi; server_client mock bilan commit.
- `sim/`: `pytest` + ma'lum GES ma'lumotlari bilan taqqoslash (quvvat hisobi ±5%).
- Qo'lda: 2-bosqichdan boshlab har bosqich oxirida 2–3 haqiqiy ishchi bilan sinov, fikr-mulohaza.

## Xatarlar va e'tibor

- **Ko'lam katta** — bosqich tartibi muhim; 1–2 bosqich tugagach allaqachon foydali (versiya + tasdiq). CFD (6) eng og'ir va oxirgi.
- FreeCAD 1.0 API o'zgarishi — versiyani qotirib (pin) qo'yamiz, portable bilan tarqatamiz.
- Katta IFC fayllar brauzerda sekin — 7-bosqichda server tomonda fragments konvertatsiya rejalashtirilgan.
- CFD Windows serverda ishlamaydi — Linux mashina yoki WSL2/Docker Desktop kerak.
- Real vaqt monitoring SCADA tarmog'iga kirish huquqi va protokol ma'lumotlarini talab qiladi — 5-bosqichdan oldin aniqlash.
