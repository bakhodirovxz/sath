# Sath

Kompaniya ichki BIM platformasi — gidroelektrostansiyalar (GES) uchun 3D modellash, simulyatsiya,
versiyalash va rol orqali tasdiqlash. Server = "BIM uchun GitHub": fayllar, versiyalar, tasdiqlash.

| Qism | Papka | Texnologiya | Holat |
|---|---|---|---|
| Server (API, versiyalar, tasdiqlash, simulyatsiya, monitoring) | `server/` | Python 3.10+, FastAPI, SQLAlchemy, IfcOpenShell, ifcdiff | ishlaydi, 57 test |
| Web klient (ko'rish, taqriz, simulyatsiya, CFD, monitoring) | `web/` | React, TypeScript, Vite, ThatOpen (Three.js) | ishlaydi |
| Desktop klient (to'liq CAD) | `desktop/` + fork `../Sath-FreeCAD` | FreeCAD 1.1.3 forki (o'z brending, installer) + GES workbench | ishlaydi (installer sinalgan) |
| Simulyatsiya kutubxonasi | `sim/` | Python (`ges_sim`), OpenFOAM (Docker) | suv ombori/quvur/turbina, 15 simulyatsiya moduli, CFD — 51 test |
| SCADA gateway | `deploy/gateway/` | Python (Modbus TCP, OPC UA, CSV) | ishlaydi |
| O'rnatish | `deploy/` | Docker Compose (+ postgres, cfd profillari) | ishlaydi |

## Nima qila oladi (hozir)

- **Loyihalar, modellar, versiyalar** — har IFC yuklash = versiya (commit izohi, ota versiya, sha256 dedup, yorliq/teg,
  qayta tiklash, ikki versiya farqi).
- **Rollar**: administrator, loyiha ichida Ko'ruvchi / Dispetcher / Muhandis / Tasdiqlovchi.
- **Tasdiqlash oqimi** (ISO 19650 soddalashtirilgan): Ishda → Tasdiqda → Tasdiqlangan → Arxiv;
  tasdiqlash so'rovi (GitHub PR kabi), izoh / o'zgartirish so'rash / ma'qullash / tasdiqlash, audit log.
- **Versiyalar farqi** (ifcdiff): qo'shilgan / o'zgargan / o'chirilgan elementlar 3D da rang bilan.
- **Issue lar** (BCF uslubi): 3D ko'rinish (kamera, tanlangan elementlar, kesimlar) bilan, ijrochi, holat, izohlar.
- **3D ish maydoni, Blender/3ds Max uslubida**: menyu satri, ish maydonlari, viewport sarlavhasi (Solid/Wireframe/X-ray),
  navigatsiya gizmosi, Outliner + ikonkali xususiyatlar muharriri, tezkor tugmalar (H, Alt+H, /, 1/3/7, Z, N…),
  AutoCAD buyruqlar qatori (`ZOOM E`, `HIDE`, `ISO`, `FIND`, `SEC`, `DIST`, `CLASH`, `QTO` …), o'rta tugma — surish.
  Rendered shading (AO + konturlar), kamera rejimlari (yurish, plan), kesim qutisi, rang sxemalari, hover, render PNG,
  outliner qidiruv/ko'z. Katta IFC: serverda `.frag` ga konvertatsiya (35 MB IFC → 0.5 MB, brauzerda parse yo'q).
- **BIM tekshiruvlar**: to'qnashuvlarni aniqlash (clash detection: to'qnashuv / ehtimoliy / tegib turadi, 3D da ajratish,
  issue ochish), hajm-miqdor hisobi (QTO: hajm, sirt, o'lchamlar, tur/qavat jamlanmasi, CSV).
- **Simulyatsiya (gidro)**: kiruvchi gidrograf → suv ombori balansi → quvur yo'qotishlari → turbinalar (FIK egri chiziqlari,
  agregatlar taqsimoti) → quvvat/energiya; 5 ish rejimi; natijalar grafiklar, xulosa, 3D da suv sathi animatsiyasi.
  Parametrlar IFC dagi `Pset_GES_*` xususiyatlaridan olinadi.
- **CFD (OpenFOAM)**: bosimli quvur (o'q-simmetrik, k-ε), suv tashlagich (2D erkin sirt, VOF) va **model geometriyasi**
  (tanlangan IFC elementlari → STL → snappyHexMesh + simpleFoam: gidrodinamik kuch, sirtdagi bosim);
  Docker yoki alohida worker; natija — napor yo'qotishi, tezlik/bosim maydoni (2D xarita, 3D tekislik), suv sirti profili.
- **Monitoring / SCADA (digital twin)**: sensorlar IFC elementga bog'lanadi, SCADA dan HTTP/MQTT/CSV (gateway: Modbus, OPC UA),
  jonli qiymatlar (WebSocket), 3D da rang; **dispetcher paneli** — GES mimik sxemasi, KPI, trendlar, **alarm jurnali**
  (kvitlash, ustuvorlik, ovoz), kun/hafta/oy **hisobot** (energiya, CSV, kunlik email); historian (soatlik agregat,
  saqlash muddati), **supervisory control** (setpoint buyruqlari → gateway → Modbus/OPC UA, audit), **smena jurnali**,
  ilova ichi **bildirishnomalar** (qo'ng'iroq) va email, **audit jurnali** ko'rish.
- **Simulyatsiya katalogi** (17 tur, aniq formulalar, pasport/model/jonli holatdan avtomatik to'ldirish): gidravlik zarba (MOC),
  minora, agregat–regulyator (HYGOV), to'g'on barqarorligi, **yorilish xavfi** (gravitatsion usul, issiqlik indeksi, moyil
  joylar), filtratsiya/suffoziya, to'g'on turi maslahatchisi, zilzila (EC8/KMK), **yog'ingarchilik → toshqin** (SCS-CN, qor,
  GLOF), toshqin/yorilish (Puls, Froehlich, Muskingum), tog' ko'chishi to'lqini (Heller–Hager), loyqa (Brune), optimal yuk
  taqsimoti, **maxsus formulali** simulyatsiya (xavfsiz hisoblagich, shablonlar). **Maydon pasporti** (yer, tuproq,
  seysmiklik, sathlar, materiallar) va materiallar katalogi (beton B10–B60, po'lat, grunt).
- **Boshqa dasturlardan import/eksport**: Blender/3ds Max/AutoCAD fayllari (OBJ+MTL, STL, PLY, glTF/GLB, DAE, 3MF, DXF; serverda
  Assimp/LibreDWG/Blender bo'lsa FBX, 3DS, DWG, BLEND) webga yuklanadi → IFC (nom, rang, nom bo'yicha GES turi/Pset) → versiya;
  IFC → glTF/OBJ yuklab olish; **Blender addoni** (`desktop/blender/`) — yuborish/olish tugmalari.
- **Web 3D da element yaratish** (Shift+A: primitivlar va GES inshootlari), G/R/S, Pset_GES, «IFC ga qo'shish» → yangi versiya.
- **Holat monitoringi**: sog'liq indeksi, ISO 20816-5 tebranish zonalari, harorat, trend → RUL, anomaliya, kavitatsiya (Toma);
  «nima bo'lsa» sinovi va optimal rejim (dispatch) jonli holatdan; **toshqin prognozi** (yog'in + jonli sath → sath, tavsiya);
  **ish buyruqlari** (CMMS: MTTR/MTBF, avtomatik — sog'liqdan), **ehtiyot qismlar** ombori, transformator yuklanishi
  (IEC 60076-7), tashqi **ML modeli** uchun integratsiya nuqtasi (`/ml/predictions` → ML.* sensorlar).
- **Raqamli egizak**: jonli sath/sarf + model `Pset_GES` → kutilgan quvvat, og'ish %, haqiqiy FIK (virtual sensorlar,
  og'ish alarmlari), 3D da jonli suv sathi, simulyatsiya jonli holatdan, **aktivlar** (ish soatlari, ishga tushishlar,
  texnik xizmat), **vaqt mashinasi** (istalgan vaqtdagi holat).
- **Issue almashinuvi**: BCF 2.1 eksport/import; **saqlangan ko'rinishlar**; **email** bildirishnomalar (SMTP).
- **Desktop (Sath = FreeCAD forki)**: o'z nomi/ikonkasi/splash i, NSIS installer va portable zip, serverga ulanish,
  modelni ochish, commit, tasdiqlash so'rovlari (qarorlar), issue lar, simulyatsiya (natija + 3D suv sathi), bildirishnomalar,
  GES parametrik obyektlari (to'g'on, quvur, turbina, suv tashlagich), qora tema + CAD navigatsiya, yangilanish tekshiruvi.
- **Sinovlar**: pytest (server, sim, desktop), vitest, Playwright e2e (login → model → tasdiqlash → tekshiruv → dispetcher), CI, Docker.

Qo'llanmalar: [docs/qollanma.md](docs/qollanma.md) (foydalanuvchi), [docs/admin.md](docs/admin.md) (administrator), [docs/plan.md](docs/plan.md) (reja va holat).

## O'rnatish (ishlab chiqarish)

```bash
cd deploy
cp .env.example .env          # admin parol va kalitni xohlasangiz kiriting (bo'sh — avtomatik)
docker compose up -d --build  # http://<server>:8000
docker compose logs ges       # birinchi admin paroli qayerdaligi ko'rsatiladi
```

Korporativ proksi (TLS) bo'lsa build da: `--build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" --build-arg NPM_STRICT_SSL=false`.
Zaxira: `deploy/backup.sh`. Postgres: `docker compose --profile postgres up -d` + `.env` da `GES_DATABASE_URL`.
CFD (OpenFOAM worker): `.env` da `GES_CFD_MODE=worker`, `docker compose --profile cfd up -d`.

## Ishlab chiqish

```bash
python -m venv .venv && .venv/Scripts/activate       # Windows
pip install -e "./sim[dev]" -e "./server[dev]"
cd server && ges-server                                 # http://localhost:8000/docs
cd web && npm install && npm run dev                    # http://localhost:5173 (API proksi 8000 ga)
```

Testlar: `ruff check . && pytest sim/tests server/tests desktop/tests` va `cd web && npm test && npm run typecheck`.
Namunaviy model: `docs/samples/namuna_ges_v1.ifc` / `_v2.ifc` (`docs/samples/make_sample_ges.py`).

## Tuzilma

```
server/ges_server/   auth/ projects/ models/ review/ sim/ — FastAPI routerlar, orm.py, audit.py
web/src/             viewer/ (ThatOpen o'rami, buyruqlar) ui/ pages/ api/
desktop/GesWorkbench FreeCAD addon: ges_workbench/{server_client,commands,dialogs,ges_objects,preset}
sim/ges_sim/         reservoir.py penstock.py turbine.py scenario.py
deploy/              Dockerfile docker-compose.yml .env.example backup.sh
```

3D viewer [That Open Company](https://thatopen.com) (`@thatopen/components`, MIT) va IFC ishlov
[IfcOpenShell](https://ifcopenshell.org) (LGPL) asosida. FreeCAD — LGPL.
