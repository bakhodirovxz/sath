# Sath desktop: Blender yadroli BIM-SCADA ilova — Poydevor (dizayn)

## Kontekst

Sath — GES uchun «GitHub for BIM» server (IFC versiyalar, CR, ifcdiff, BCF, RBAC, audit), simulyatsiya (`sim/ges_sim`, OpenFOAM) va SCADA/raqamli egizak (`server/ges_server/monitoring`). Desktop klient — Blender 5.2 extension `desktop/blender/sath/` (Bonsai IFC, FreeCAD jarayon ichida geometriya uchun).

Maqsad: ilova (desktop) birinchi o'rinda; Blender — yadro va dizayn tili; BIM-SCADA ga maksimal yaqin (raqamli egizak, simulyatsiya, versiyalar va taqqoslash, rollar); istalgan 2D/3D faylni ochish/o'zgartirish; yengil va optimallashgan; yangi funksiyalar Blender addonlari kabi muammosiz qo'shiladigan modullar.

Hozirgi to'siqlar: plagin tizimi yo'q; rollar UI da tasodifiy (`ui.py:141` faqat approver); bloklovchi chaqiruvlar Blender ni 15 daqiqagacha qotiradi (K3); serverdan ochilgan GES obyektlari parametrlarini yo'qotadi (K2); IFC o'zgarishlari undo dan tashqarida — yetim GUID lar (K4); GES obyektlari FreeCAD siz yaratilmaydi (~0.9 GB, xotira oqishi); Blender testlari CI da yo'q (K7).

### Foydalanuvchi qarorlari
1. **Blender chuqurligi:** rasmiy Blender + Sath app template + extension (o'z workspace lari, editor/panel/menyular). C++ fork yo'q (faqat mavjud brend forki).
2. **FreeCAD:** alohida jarayon ham qilinmaydi — kerakli funksiya va formulalar o'zimizning sof Python kodimizga ko'chiriladi, FreeCAD desktopdan butunlay chiqadi (roadmap K1 yakuni). Tekshiruv: hozir FreeCAD faqat primitivlar (box, cylinder, cone, torus, polygon extrude, revolve, pipe sweep, loft), `fuse/cut` va `tessellate` uchun ishlatiladi (`wb/ges_objects.py`), DXF import uchun esa ezdxf allaqachon o'rinbosar. FEM hozir umuman yo'q, simulyatsiya formulalari allaqachon o'zimizniki (`sim/ges_sim`).
3. **Fayllar:** ochiq formatlar to'liq round-trip; DWG — LibreDWG/ODA Converter; .max va to'liq DWG — 3ds Max/AutoCAD ichidagi Sath konnektor-plaginlar.
4. **Birinchi quyi-loyiha:** Poydevor.
5. **Til strategiyasi — gibrid, o'lchovdan keyin:** ilova logikasi, plagin tizimi va `geom` Python + numpy da (Blender plaginlari baribir Python). `geom` keyinroq C++ ga almashtirish oson bo'lgan aniq interfeys bilan yoziladi (faqat numpy massivlar kiradi/chiqadi, bpy siz). P0 da bazaviy o'lchov olinadi; Unumdorlik quyi-loyihasida profil bo'yicha aniqlangan sekin joylar `sath_core` C++23 (MSVC/GCC/Clang qo'llaydigan qismi) + nanobind + scikit-build-core wheel ga ko'chiriladi, Python versiyasi zaxira va paritet etaloni bo'lib qoladi.
6. **Qo'shimcha (BIM-SCADA namunasi bo'yicha):** fazoviy alarmlar, aktiv inspektori (trend + ish buyurtmalari + hujjatlar), 3D da jonli qiymatlar, energiya KPI — Poydevordan keyingi «Jonli egizak» moduli.

## Umumiy yo'l xaritasi (har biri alohida spec → reja → bajarish)

| # | Quyi-loyiha | Mazmun |
|---|---|---|
| 1 | **Poydevor** (shu reja) | Modul tizimi, rolga sezgir UI, async vazifalar, K2/K4, FreeCAD siz o'z geometriyamiz (`geom` + `ges_kinds`), workspace lar, CI |
| 2 | **Jonli egizak (SCADA) moduli** | `/api/projects/{id}/live` WebSocket push (5 s polling o'rniga); ilovada alarm ro'yxati → kamera aktivga uchadi, izolyatsiya, ISA-101 shakllari ◆▲■● + 1 Hz miltillash; «Aktiv inspektori» (historian trend, `WorkOrder`, `AssetDocument`, sog'liq indeksi); 3D overlay yozuvlar (`gpu`/`blf`, sahnaga obyekt qo'shmasdan); energiya KPI (agregat FIK, yo'qotishlar, o'z ehtiyoji, `ges_sim` dispatch tavsiyasi) |
| 3 | **Versiya boshqaruvi va taqqoslash** | `feat/vcs2` ni birlashtirish (tarmoqlar, element qulflari, 3 tomonlama IFC merge); diff server job; Compare workspace (sinxron ikki viewport, element bo'yicha farq ro'yxati, slayder) |
| 4 | **Fayl I/O markazi va konnektorlar** | `io` moduli orqali ochiq formatlar round-trip (IFC, DXF, glTF, FBX, OBJ, STEP, .blend, STL, 3DS); DWG; 3ds Max (pymxs) va AutoCAD (.NET) konnektorlari — shu modul API si bilan |
| 5 | **Simulyatsiya yadrosi** | O'z formulalarimiz (`sim/ges_sim`) kengaytiriladi; kerak bo'lsa FEM — FreeCAD siz, to'g'ridan-to'g'ri Gmsh + CalculiX (yoki yengil scikit-fem) server worker da; natijalar Blender timeline/overlay da. Aniq STEP/B-rep kerak bo'lsa — faqat serverda, mavjud ixtiyoriy OCP (`models/cad_import.py`) |
| 6 | **Unumdorlik va `sath_core` (C++23)** | Profil asosida: katta model diff/clash, jonli overlay buferlari, LOD/mesh soddalashtirish, instancing — `sath_core` (nanobind, wheel lar CI da Windows/Linux, imzolangan) ga; Python implementatsiya zaxira + paritet testlari; Bonsai geometriyasini dangasa yuklash, xotira profili, byudjetlar |

---

## Poydevor — dizayn

### 1. Sath modul (plagin) tizimi
**Qaror:** yagona `sath` extension ichida ichki reyestr (har modul alohida Blender extension emas — extension lar orasida bog'liqlik/yuklash tartibi yo'q, paket yo'li o'zgaruvchan, rol/API tekshiruvi uchun baribir xost kerak). Modullar oddiy `Panel/Operator/Menu/UIList` qayd qiladi → F3 qidiruvda, o'z N-panel yorlig'ida, Blender ga to'liq tabiiy ko'rinadi.

```
sath/core/      registry.py tasks.py events.py perms.py ifc_ops.py tokens.py
sath/api.py     barqaror fasad, API_VERSION = (1, 0)
sath/modules/<id>/sath_module.toml + __init__.py     (birinchi tomon, bundle ichida)
<user config>/sath_modules/<id>/                     (uchinchi tomon; prefs.allow_user_modules + Ed25519 imzo, update.py dagi tekshiruv qayta ishlatiladi)
```

Manifest (`sath_module.toml`): `id, name, version, api = ">=1.0,<2", requires = [...], permissions = ["network","files","subprocess","ifc.write"], visible_if_any = [server ruxsat satrlari], workspaces = [...], category, default_enabled, order`.

Hayot sikli: `registry.discover()` (tomllib, bpy siz → pytest) → API/bog'liqlik tekshiruvi → topologik tartib → `module.register(api)`. `api.register_classes(mod_id, classes)` klasslarni yozib boradi → prefs da o'chirilganda jonli unregister (Blender Add-ons ro'yxati kabi: checkbox, versiya, ruxsatlar). Register da yiqilgan modul izolyatsiya qilinadi, traceback prefs da.

Public API (`sath.api`): `session`, `tasks.run`, `perms.can/require`, `ifc` (+ `IfcOperator`, `restore_ges`), `events.subscribe/publish`, `ui.SathPanel` (manifestdan `bl_category`; `sath_needs={"login","model"}`, `sath_perm="sim.run"`; yagona `poll`: modul yoqilgan + workspace tegi + ruxsat + holat), `ui.keymap()`, `props.scene_group(mod_id, cls)` (snapshot/restore ga avtomatik), `geom`/`kinds` (§6 sof Python geometriya va GES turlari).

Hodisalar: `session.login/logout`, `project.changed`, `ifc.loaded`, `scada.snapshot`, `task.*` — asosiy oqimda, vazifa pompasidan. `scada.snapshot` hozir REST dan; 2-quyi-loyihada faqat manba WS ga almashadi.

**Migratsiya (strangler):** A) core + mavjud `MODULES` ni o'zgarishsiz ro'yxatga oluvchi `legacy` psevdo-modul. B) bittadan: `review` → `sim` → `scada` → `twin` → `io` → `bim`. Har modul avval mavjud `ops_*.py` ni qayta eksport qiladi va `ui.py` dagi panelini oladi; fayllar faqat tegilganda ko'chadi. `bl_idname` lar (`sath.diff`, …) o'zgarmaydi. Core da qoladi: Server/login, bildirishnomalar, update, status-bar vazifa UI, prefs, `Scene.ges`.

### 2. Rolga sezgir UI
- **Server:** `server/ges_server/projects/router.py::_out` → `ProjectOut.permissions: list[str]` = `sorted(role_permissions(role))` (`auth/deps.py` dagi `ROLE_PERMISSIONS`). Test `server/tests` da.
- **Klient:** `core/perms.py` loyiha tanlanganda keshlaydi (`flows.model_role` lazy chaqiruvi o'rniga). Eski server uchun zaxira: `common/sath_common/permissions.py` (sync orqali), pytest `ROLE_PERMISSIONS` bilan tenglikni tekshiradi.
- Moslik: commit → `model.write`, submit → `cr.create`, approve → `cr.approve`, merge → `cr.merge`, review → `cr.review`, issue → `issue.write`, sim/twin/xavfsizlik → `sim.run`, monitoring → `scada.read`.
- Panel `visible_if_any` bajarilmasa yashiriladi; operator `poll` + `poll_message_set("Ruxsat yo'q: cr.approve")` bilan kulrang.

### 3. Async vazifa ishchisi (K3) — `core/tasks.py`
`tasks.run(title, fn, on_done, on_error, *, key, cancellable)`; `fn(ctx)` daemon `threading.Thread` da (ThreadPoolExecutor emas — chiqishda osilib qoladi); `ctx.progress(frac, text)`, `ctx.cancelled`. Worker bpy ga tegmaydi → `queue.SimpleQueue` → `bpy.app.timers` pompa 0.1 s, `persistent=True` (Bonsai `read_homefile` dan omon qoladi). `on_done` epoch (model + sessiya) ni tekshiradi. `key` takrorlanishni bloklaydi. Status bar: `layout.progress` + X (`sath.task_cancel`). `GesClient._refresh` atrofida `threading.Lock`; `download_version` `.part` ga oqim bilan, progress va bekor qilish bilan. Headless test uchun `tasks.drain(timeout)`.
Qo'llash: connect, open_version/pull_head (yuklash worker da; `ifc.load` + K2 asosiy oqimda), commit upload, diff, safety_check, download_update (`update.download_and_verify` progressi), sim_catalog, `ops_monitor._tick`, `ops_sim._poll_factory`, `_TwinSim` polling.

### 4. K2 round-trip va K4 undo
- **K2:** mavjud `Pset_GES_*` yonida `Pset_SathParametric` (`Kind`, `Role`, `SchemaVersion`, `Params` JSON, metrik). `ges_objects.restore_from_ifc() -> RestoreReport(restored, inferred, unknown)`: avval shu pset, bo'lmasa `Pset_GES_<X>` nomidan kind va kind spec (§6) orqali teskari xaritalash. Mesh qayta qurilmaydi (GUID va geometriya saqlanadi). `ifc.loaded` da ishlaydi; noma'lumlar uchun aniq ogohlantirish. `sim_anim` da yetishmagan rol uchun `TwinBindingError` (jim `if o is not None` o'rniga).
- **K4:** `core/ifc_ops.IfcOperator` — Bonsai `tool.Ifc.Operator` ustidan mixin (`_execute`, IFC tranzaksiyasi Blender undo ga qo'shiladi), `bl_options={"REGISTER","UNDO"}`: `add_object`, `rebuild_object`, `build_demo_plant`, import «assign», yangi `sath.sync_ifc`. Parametr o'zgarishi timer da faqat mesh ni qayta quradi + `obj.ges.ifc_dirty`; IFC yozuvi faqat `sath.sync_ifc` da (commit boshida, «IFC ga qo'llash» tugmasi, «3 obyekt sinxronlanmagan» hisoblagich). `ifc.orphans()` — commit dialogida yetim entitylarni o'chirish/bekor qilish. `flush_pending` dagi `print()` → `s.status` + report. `sath_tests/objects.py` avval `sath.sync_ifc()` ni chaqiradigan qilib yangilanadi.

### 5. App template va workspace lar
`template/Sath/__init__.py` + yangi `workspaces.py`, `load_factory_startup_post` da idempotent:
- **BIM** (Outliner, Properties, N-panel `bim`), **Compare** (ikki `VIEW_3D`, 3-quyi-loyiha to'ldiradi), **Simulation** (Timeline, Graph), **SCADA** (Object-colour shading, ISA-101 kulrang asos).
- Workspace tegi `ws["sath_ws"]` ↔ manifest `workspaces`. Sculpting/UV/Texture/Shading/Rendering/Compositing/GeoNodes o'chiriladi (Scripting faqat developer UI da). `use_filter_by_owner=True`, `owner_ids` = sath, bonsai. `sath.reset_workspaces` operatori.
- **Tema:** Blender Dark asosida `template/Sath/theme_sath.xml` (`setup_bundle.py` da qo'llanadi). `core/tokens.py` `web/src/ui/tokens.ts` dan generatsiya (sync + CI `--check`) — 3D diff/alarm ranglari web bilan bir xil.
- **Keymap:** Ctrl+Shift+G saqlanadi; modullar `api.ui.keymap()` orqali; headless konflikt testi.
- **Byudjetlar** (P0 bazaviy o'lchovdan keyin tasdiqlanadi): Sath register jami < 150 ms (har modul `perf_counter` bilan log); og'ir importlar (`ifcopenshell`, `ezdxf`, `assimp`, `numpy`) funksiya ichida; sovuq start ≤ 1.2× Blender+Bonsai; bo'sh sahnada RSS ≤ bazaviy + 50 MB.

### 6. FreeCAD funksiyalarini o'zimizga ko'chirish (FreeCAD to'liq olib tashlanadi)
**Nima ko'chiriladi** (o'zimizning `wb/ges_objects.py` kodimiz Part API dan sof Python ga qayta yoziladi — FreeCAD kodi nusxalanmaydi, faqat geometrik usullar; LGPL muammosi yo'q):
- `common/sath_common/geom.py` (sof Python + numpy, float64, bpy siz → server ham ishlata oladi; kirish/chiqish faqat numpy massivlar — keyin `sath_core` C++ bilan bir xil API da almashtiriladi): `box`, `cylinder`, `cone`, `torus`, `extrude(polygon)`, `revolve(profile)`, `sweep(profile, path)` (bosimli quvur, tirsak — `penstock_path()` bilan), `loft(ring_a, ring_b)`. Kesish (`cut`) imkon qadar **to'g'ridan-to'g'ri qurish** bilan almashtiriladi (quvur = halqa profilni sweep, ichi bo'sh bino = devorlar) — tez va barqaror; zarur joyda Blender `Boolean` modifier (Manifold/Exact solver) faqat desktopda.
- **Aniqlik:** tessellatsiya chord tolerance bo'yicha (sagitta ≤ sozlanadigan, default 5 mm, obyekt o'lchamiga mos — mavjud `fc_engine` dagi tolerance mantiqi saqlanadi). Muhandislik miqdorlari (hajm, yuza, massa, QTO) mesh dan emas, **parametrlardan analitik formulalar** bilan `ges_kinds` da hisoblanadi → FreeCAD tessellatsiyasidan ham aniqroq; mesh hajmi faqat nazorat uchun.
- `common/sath_common/ges_kinds.py` — 11 kind: parametr, birlik, default, pset xaritasi, `ifc_class`, rang, `build(params) -> (verts, faces)`, `quantities(params)` (manba: `wb/ges_objects.py` + `web/src/viewer/draftKinds.ts`; web, desktop, server bir xil element beradi).
- **Paritet:** FreeCAD hali o'rnatilgan mashinada bir martalik skript `desktop/tests/gen_fc_golden.py` har kind uchun default va 2-3 parametr to'plamida FreeCAD `Shape.Volume/Area/BoundBox` ni `desktop/tests/data/ges_golden.json` ga yozadi. Pytest yangi builder larni shu golden bilan solishtiradi (hajm ±0.5 %, bbox ±tolerance) — CI da FreeCAD kerak emas.
- **Olib tashlanadi:** `fc_engine.py`, `sath/wb/`, `ops_import.py` dagi FreeCAD DXF yo'li (ezdxf qoladi), `prefs.py` FreeCAD papkasi, `build_blender_bundle.py` dagi `freecad/` (~0.9 GB), `sync_blender.py` dagi wb nusxasi; `desktop/GesWorkbench/` va FreeCAD fork quvuri `archive/` ga yoki alohida tarmoqqa (git tarixida qoladi).
- `ges_objects` sxemani `ges_kinds` dan oladi; `add_object.poll` faqat login/loyiha holatiga bog'liq.
- Blender ga uzatish: `from_pydata` (Python ro'yxatlari) o'rniga `mesh.vertices.foreach_set` / `loops` / `polygons` numpy massivlari bilan — hozirgi asosiy sekinlik shu yerda.

### 7. K7 — Blender testlari CI da
`.github/workflows/ci.yml` ga `desktop-blender` (windows-2022): Blender 5.2.2 va Bonsai 0.8.5 zip lari `actions/cache` + SHA-256 pin; `BLENDER_USER_RESOURCES` izolyatsiya; Bonsai o'rnatish; `sync_blender.py --check`; `run_blender_tests.ps1`; `build_blender_addon.py` → artefakt. P2 gacha FreeCAD ga bog'liq `engine` testi `[SKIP]` (`GES_FC_HOME` bo'lmasa), P2 da u golden-paritet testi bilan almashadi. Server talab qiladigan testlar (`e2e_server`, `commit_conflict`, `sim_hydro`, `sim_twin`) — tungi bosqich.

## Bosqichlar

| Bosqich | Mazmun | Tayyor mezoni |
|---|---|---|
| **P0** | K7 CI ishi; bazaviy o'lchov skripti `desktop/tests/perf_startup.py` (start vaqti, RSS, register vaqti, namuna GES qurish, katta IFC ochish, diff) — natija `docs/benchmark.md` ga (C++ qarorlari uchun asos) | CI `sath_tests` da qizil/yashil; bazaviy raqamlar yozilgan |
| **P1** | `core/tasks.py`, `core/events.py`, GesClient lock + oqimli yuklash; 9 ta chaqiruv joyini ko'chirish | headless `tasks_async`: sekin soxta server chaqiruvida pompa ishlaydi, bekor qilish ishlaydi |
| **P2** | Avval `gen_fc_golden.py` (FreeCAD hali bor mashinada); `geom` + `ges_kinds`; `ges_objects` ni ko'chirish; FreeCAD ni olib tashlash; K2 restore; K4 `IfcOperator`/`sync_ifc`/orphans | golden paritet (hajm ±0.5 %); FreeCAD siz mashinada barcha 11 GES obyekti va «Namuna GES» quriladi; `roundtrip_ges` (namuna GES → saqlash → yangi yuklash → kind/role/params teng → `animate_hydro` > 0 keyframe); `undo_ifc` (qo'shish → undo → `orphans()==[]`) |
| **P3** | Reyestr, `api.py`, prefs modul ro'yxati, server `permissions`, `SathPanel`; modullarni ketma-ket ko'chirish | headless `modules`: `review` jonli o'chadi/yonadi; viewer roli sim/commit ni yashiradi |
| **P4** | Workspace lar, tema, tokens sync, keymap testi, FreeCAD siz bundle, byudjetlar | bundle ~0.9 GB kichik, BIM workspace da ochiladi; byudjetlar log da va bajarilgan |

P2 va P3 P1 dan keyin parallel (umumiy fayllar: `ges_objects.py`, `ui.py`). Har bosqich alohida tarmoq/commit lar, xabarlar o'zbekcha (`fix(K2): …`, `feat(MOD): …`).

## Asosiy fayllar
- O'zgaradi: `desktop/blender/sath/__init__.py`, `ui.py`, `ges_objects.py`, `ifc.py`, `ops_server.py`, `ops_review.py`, `ops_sim.py`, `ops_monitor.py`, `prefs.py`, `props.py`, `sim_anim.py`; `common/sath_common/server_client.py`; `server/ges_server/projects/router.py`; `desktop/blender/template/Sath/__init__.py`, `template/setup_bundle.py`; `desktop/build/build_blender_bundle.py`, `sync_blender.py`; `desktop/tests/run_blender_tests.ps1`, `blender_headless.py`, `sath_tests/objects.py`; `.github/workflows/ci.yml`.
- O'chiriladi/arxivlanadi: `desktop/blender/sath/fc_engine.py`, `sath/wb/`, `desktop/GesWorkbench/`, FreeCAD fork/portable build skriptlari.
- Yangi: `desktop/blender/sath/core/*`, `api.py`, `modules/<id>/`; `common/sath_common/geom.py`, `ges_kinds.py`, `permissions.py`; `desktop/tests/gen_fc_golden.py`, `desktop/tests/data/ges_golden.json`; `desktop/blender/template/Sath/workspaces.py`, `theme_sath.xml`; testlar `sath_tests/{tasks_async,roundtrip_ges,undo_ifc,modules}.py`, `desktop/tests/perf_startup.py`.
- Qayta ishlatiladi: `ops_sim._poll_factory` (polling namunasi), `update.download_and_verify` (oqim + progress + Ed25519), `props.snapshot/restore`, `wb/ges_objects.penstock_path`, `web/src/viewer/draftKinds.ts`, `auth/deps.py::ROLE_PERMISSIONS`/`role_permissions`, Bonsai `tool.Ifc.Operator`.

## Xavflar
- Bonsai `tool.Ifc.Operator` ichki API → `core/ifc_ops.py` da izolyatsiya, CI da Bonsai versiyasi pin.
- `-b` rejimda undo farqli bo'lishi mumkin → `IfcStore.undo()` + GUI tekshiruv (`blender_gui_check.py`).
- Worker dan bpy ga tegish Blender ni yiqitadi → `api` setterlarida debug assert (asosiy oqim).
- Yangi builder lar FreeCAD tessellatsiyasidan farq qiladi → eski versiyalar bilan mesh diff da «geometriya o'zgardi» shovqini; yuklashda qayta qurmaslik GUID/mesh ni saqlaydi, qayta qurish faqat parametr o'zgarganda.
- Boolean dan qochib to'g'ridan-to'g'ri qurish har kind uchun qo'lda ishlash talab qiladi (eng murakkablari: mashina zali kesimi, suv qabul qilgich) → golden paritet testi xatoni ushlaydi.
- FreeCAD ni olib tashlashdan oldin golden fayl yaratilishi shart (P2 birinchi qadami).
- Mavjud foydalanuvchilarda workspace lar faqat `sath.reset_workspaces` bilan paydo bo'ladi.
- Windows CI ~600 MB kesh, 10–15 daqiqa.

## Tekshirish
```
python desktop/build/sync_blender.py --check
pytest -q desktop/tests                          # registry, geom, ges_kinds + golden paritet, perms paritet, tasks navbati
pytest -q server/tests -k project                # permissions maydoni
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; .\desktop\tests\run_blender_tests.ps1
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test roundtrip_ges --bonsai
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test undo_ifc --bonsai
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test tasks_async
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai
python desktop/build/build_blender_bundle.py --no-zip    # Sath.exe: workspace lar, perf log, FreeCAD siz GES obyektlari
```
Qo'lda: katta modelda sekin serverga «Ota bilan farq» — viewport qayta chiziladi, status barda progress, X bekor qiladi; viewer rolida commit/approve ko'rinmaydi.

## Bajarish tartibi
Ushbu spec tasdiqlangach: batafsil implementatsiya rejasi (writing-plans) → bosqichma-bosqich bajarish (P0 → P1 → P2‖P3 → P4), har bosqich testlar bilan. Keyin 2-quyi-loyiha (Jonli egizak moduli) uchun alohida spec.
