# Sath Blender addoni (2-bosqich) — dizayn

Sana: 2026-09-17. Oldingi bosqich: `docs/spike-blender-freecad.md` (FreeCAD Blender ichida in-process ishlaydi).
Keyingi: 3) Blender forki + brend + CI, 4) web UI Blender uslubida, 5) SCADA / raqamli egizak.

## Maqsad

FreeCAD workbench (`desktop/GesWorkbench`) beradigan hamma narsani Blender addoni sifatida berish — serverga
ulanish, model ochish/commit, taqriz, versiyalar/farq, simulyatsiya, monitoring, GES parametrik obyektlari,
DXF/DWG/mesh import — **Blender interfeysida**, IFC Bonsai'da yashaydi, FreeCAD faqat geometriya/import dvigateli.
Addon stock Blender 5.2 LTS + Bonsai 0.8.5 da ishlaydi (fork keyin shuni o'rab oladi).

## Stack

Blender 5.2 LTS (Python 3.13) · Bonsai 0.8.5 (extension, ifcopenshell 0.8.5) · FreeCAD 1.1.3 conda-forge `py313`
(`GES_FC_HOME` yoki addon sozlamasidagi yo'l; sukut `%USERPROFILE%\Tools\fc-py313`, fork bundle'da `./freecad`).

## Arxitektura

```
desktop/blender/sath/                 Blender extension (blender_manifest.toml, id = sath)
  __init__.py        register/unregister; FreeCAD ni kech (lazy) yuklaydi
  prefs.py           AddonPreferences: server, login, parol(memory), fc_home; Scene.ges PropertyGroup
  session.py         GesClient nusxasi + token (xotirada), prefs bilan saqlash    ← shared/server_client
  fc_engine.py       FreeCAD loader (spike fc_bridge retsepti) + shape→mesh (numpy foreach_set) + throwaway doc
  ifc.py             Bonsai ko'prigi: load/save, guid↔obyekt, mesh obyekt → IFC element + Pset_GES_*, diff bo'yash
  ges_objects.py     GES obyektlari: Scene/Object PropertyGroup (kind + parametrlar) → fc_engine → mesh → ifc
  viewpoint.py       BCF ko'rinish (kamera + tanlangan GUID) — web bilan bir xil format, metr, Z yuqoriga
  ops_server.py      operatorlar: connect, open, commit, submit, issues, review, versions/diff, notify, open_web
  ops_sim.py         sim katalogi, xavfsizlik tekshiruvi, suv sathi tekisligi (timer bilan poll)
  ops_monitor.py     SCADA monitoring — modal timer, sensor→obyekt rang, suv sathi
  ops_import.py      DXF/DWG (FreeCAD Import/Draft + libredwg), mesh (FBX/3DS/... assimp), .blend to'g'ridan
  ui.py              N-panel "Sath": Server · Model · Obyektlar · Sim · Monitoring; header menyu
  shared/            FreeCAD siz umumiy kod: server_client.py, dxf_prepare.py, assimp_load.py (nusxa)
  vendor/            ezdxf, assimp-py wheel lari (manifest `wheels`)
desktop/build/sync_blender.py   GesWorkbench/ges_workbench → sath/shared nusxalash, --check CI uchun
desktop/tests/test_sath_*.py  pytest (FreeCAD/Blender siz) + blender_headless.py (blender -b)
```

**Manba qoidasi**: `server_client.py`, `dxf_prepare.py`, `assimp_load.py` yagona manbasi `GesWorkbench/ges_workbench`;
addonga `sync_blender.py` nusxalaydi (CI `--check`). Qolgan addon kodi addonning o'zida.

## Asosiy qarorlar

1. **IFC — Bonsai manba.** Ochilgan model = Bonsai loyihasi (`bim.load_project`). Commit = `bim.save_project`
   → fayl serverga. Element ↔ Blender obyekt mosligi Bonsai'niki (`tool.Ifc.get_entity/get_object`), GUID
   saqlanadi → server diff ishlaydi.
2. **FreeCAD stateless.** `fc_engine` bitta yashirin FreeCAD hujjatini ushlaydi; GES obyekt yaratish/qayta hisoblash:
   FreeCAD'dagi `ges_objects.make(kind)` (workbench klasslari — parametrik ta'rif yagona manba) → parametrlarni
   qo'yish → `recompute` → `Shape` → mesh; keyin FreeCAD obyekti o'chiriladi. Blender obyektida saqlanadigan holat:
   `Object.ges.kind` + parametrlar (PropertyGroup). Parametr o'zgarsa `update` callback mesh'ni qayta quradi va
   Bonsai representation'ni yangilaydi (`bim.update_representation`).
3. **GES obyekt = IFC element.** Yaratilganda `bim.assign_class(ifc_class=<FreeCAD IfcType dan>)` + `Pset_GES_*`
   (`ifc_io._write_psets` mantiqi ifcopenshell.api.pset bilan). Bonsai loyihasi ochilmagan bo'lsa — avval
   `bim.create_project` (yangi loyiha) avtomatik.
4. **Birlik**: Blender/IFC metr, FreeCAD mm — faqat `fc_engine` chegarasida ×0.001 / ×1000.
5. **Blender qotib qolmasin**: qisqa so'rovlar sinxron (FreeCAD'dagidek); sim poll va monitoring `bpy.app.timers`;
   fayl yuklash/yuklab olish `threading.Thread` + timer bilan natijani UI'ga qaytarish. `bpy` faqat asosiy oqimda.
6. **Xatolar**: `ServerError`/`RuntimeError` → `self.report({'ERROR'}, ...)` + panelda oxirgi holat qatori;
   FreeCAD yuklanmasa — Obyektlar/Import panellari "FreeCAD topilmadi: sozlamalarda yo'lni ko'rsating" bilan o'chadi,
   server funksiyalari ishlayveradi.
7. **UI**: Blender uslubi — N-panel yorliqlari, operatorlar `F3` qidiruvda, `Ctrl+Shift+G` menyu; Qt dialoglar
   o'rniga operator `invoke_props_dialog` / panel ro'yxatlari (`UIList`). Ro'yxat ma'lumotlari (loyihalar, modellar,
   versiyalar, CR, issue, sensorlar) `Scene.ges` CollectionProperty'larda keshlanadi.

## Ma'lumot oqimi

- **Ochish**: Server → loyiha/model/versiya tanlash (UIList) → IFC `%TEMP%/sath/<v>.ifc` → `bim.load_project`
  → `Scene.ges.model_id/version_id/model_name` (FreeCAD `doc.Meta` o'rniga).
- **Commit**: `bim.save_project` → `client.upload_version(model_id, path, message)` → yangi `version_id`;
  ixtiyoriy CR ochish.
- **Versiyalar/farq**: `client.diff(version_id)` → GUID → `tool.Ifc.get_object` → `obj.color` (yashil/sariq/qizil,
  viewport Object color rejimi); "tozalash" asl ranglarni qaytaradi (`_ColorState` porti).
- **Issue/ko'rinish**: `viewpoint.capture()` — `region_3d.view_matrix` dan pozitsiya/target, tanlangan GUIDlar;
  `apply()` — `view_location/rotation/distance`, obyektlarni tanlash.
- **Sim**: `client.sim_catalog/prefill/create_sim/sim_job/sim_result` — forma `invoke_props_dialog`, natija panelda
  jadval + `open_web`; grafik uchun webga havola (matplotlib yo'q — YAGNI).
- **Monitoring**: timer har N s `client.sensors` → alarm rangi obyektga, suv sathi tekisligi (`place_water_plane` porti).
- **Import**: DWG → `dwg2dxf` → DXF → (`dxf_prepare` ezdxf) → FreeCAD `importDXF.insert` → shape'lar → mesh/curve,
  qatlam = Blender collection; mesh formatlar → assimp → mesh (Y-up → Z-up).

## Test

- pytest (Blender/FreeCAD siz): `shared/server_client` (mavjud test), `viewpoint` matematikasi (kamera↔matritsa),
  pset formatlash (`ifc._grouped_psets`), `ges_objects` parametr → FreeCAD xususiyat nomlari xaritasi.
- `blender -b --python desktop/tests/blender_headless.py`: addon yoqish → FreeCAD yuklash → 7 GES obyekt yaratish
  (IFC class + pset tekshirish) → DXF import → save_project → qayta ochib GUID/pset tekshirish. Server kerak emas
  (`server_client` uchun `unittest.mock`/lokal `http.server` stub).
- Qo'lda: GUI'da server bilan to'liq oqim (ulanish → ochish → obyekt → commit → web'da ko'rish).

## Ko'lam tashqarisi (keyingi bosqichlar)

Brending/splash/fork, web UI, SCADA arxitekturasi, matplotlib grafiklar, `dxf_edit` (AutoCAD-uslubi tahrirlash —
Blender'ning o'z curve tahrirlashi bor), `preset.py` (FreeCAD prefs — kerak emas), `mesh_open` FreeCAD import
plagini (Blender'da assimp to'g'ridan).
