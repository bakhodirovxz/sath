# Sath Desktop

O'z dasturimiz — **FreeCAD 1.1.3 forki** (`../Sath-FreeCAD`, LGPL) + shu papkadagi GES workbench.
Ishchi bitta installer o'rnatadi: dastur «Sath» nomi, o'z ikonkasi/splash i bilan, qora tema,
metr birliklari, CAD navigatsiya, Sath workbench bilan ochiladi; profil `%APPDATA%\Sath`
(o'rnatilgan FreeCAD bilan aralashmaydi). FreeCAD 1.1.3 da sinalgan (2026-09-14): workbench,
serverga kirish, model ochish (NativeIFC), GES obyektlar, commit (GUID lar saqlanadi, Pset_GES_*
yoziladi), issue/ko'rinish, installer o'rnatish/o'chirish.

## Blender addoni

Yangi yo'nalish (2026-09-17): desktop qobiq **Blender** bo'ladi, FreeCAD faqat dvigatel. `blender/sath/` —
Blender 5.2 extension: shu workbench beradigan hamma narsa (server, GES obyektlari, sim, monitoring, DXF/DWG)
Blender panellarida, IFC Bonsai da. Batafsil: `blender/README.md`; texnik asos: `../docs/spike-blender-freecad.md`,
dizayn: `../docs/superpowers/specs/2026-09-17-blender-addon-design.md`.

## Tuzilma
- `GesWorkbench/` — workbench manbasi (**yagona manba**; fork `src/Mod/Ges` shundan sinxronlanadi)
- `build/sync_fork.py` — fork ga nusxalash (`--check` CI uchun)
- `build/build_portable.py` — paket yig'ish (fork overlay + zip + NSIS installer)
- `tests/` — `test_server_client.py` (pytest), `fc_headless.py` (freecadcmd), `fc_gui.py` (GUI, server kerak)

Fork da nima bor (brending, CMake presetlar, NSIS, CI) — `../Sath-FreeCAD/README.md`.

## Nima beradi
- **Serverga ulanish** — login/parol, server manzili saqlanadi; yangi versiya bo'lsa xabar
- **Modelni ochish** — loyiha → model → versiya, IFC yuklab olinib NativeIFC bilan ochiladi
- **Commit** — hujjat IFC qilib yangi versiya sifatida yuklanadi (ixtiyoriy: darhol tasdiqqa)
- **Tasdiqqa yuborish**, **Issue lar** (3D ko'rinish bilan, izohlar)
- **Versiyalar va farq** — tarix, istalgan versiyani ochish, ota bilan farq 3D da (yashil/sariq), webda ochish
- **Simulyatsiya katalogi** — webdagi barcha turlar (forma serverdan, pasport/modeldan to'ladi, grafik, 3D suv),
  **Xavfsizlik tekshiruvi** (12 ssenariy, ball)
- **Monitoring (SCADA)** — jonli qiymatlar, obyektlar alarm rangi, suv sathi tekisligi, sensor → 3D
- **Webda ochish** — joriy model va tanlangan element brauzerda (`?v=&sel=`)
- **GES obyektlari** — To'g'on, Bosimli quvur, Turbina agregati, Suv tashlagich, Mashina zali, Transformator,
  Suv qabul qilgich: parametrik, IFC ga `Pset_GES_*` xususiyatlari bilan chiqadi (web bilan bir xil nomlar)
- Chizish uchun FreeCAD ning BIM/Draft/Part/Sketcher/TechDraw/FEM workbench lari (Robot, CAM,
  OpenSCAD va h.k. olib tashlangan)

## Paket yig'ish (Windows)
Kerak: o'rnatilgan FreeCAD 1.1.3 (`C:\Program Files\FreeCAD 1.1`), fork (`../Sath-FreeCAD`),
installer uchun NSIS (`winget download NSIS.NSIS` → setup `/S /D=%USERPROFILE%\Tools\NSIS`; admin kerak emas).
```
python desktop/build/build_portable.py            # zip + siqilgan installer (~15 daqiqa)
python desktop/build/build_portable.py --fast     # installer siqilmagan (sinov, ~2 daqiqa)
```
Natija `desktop/dist/`:
- `Sath-<ver>-Windows-x86_64-installer.exe` — ishchiga shu (Start menyu, ishchi stol, o'chirish)
- `Sath-<ver>-Windows-x86_64.zip` — portable (ochib `Sath.exe`; Blender bundle — `blender/README.md`)

FreeCAD kompilyatsiya qilinmaydi: rasmiy 1.1.3 binari fork tegi bilan bir xil commit, fork
`overlay.py` uni brending + Mod/Ges bilan Sath ga aylantiradi. To'liq kompilyatsiya (yadro
o'zgartirilganda) — fork dagi GitHub Actions «Sath build» (~2–3 soat), natija bir xil nomlar.

**Formatlar**: FreeCAD o'zi — IFC, STEP/IGES/BREP, OBJ/STL/PLY/OFF/3MF, glTF/GLB, DAE, 3DS, DXF; Sath qo'shimchasi —
DWG (LibreDWG) va DXF/DWG ni AutoCAD kabi tahrirlanadigan ochish (`dxf_edit`, ezdxf), FBX/LWO/X/ASE/AC/MS3D/AMF/X3D…
(`mesh_open`, assimp-py) — Fayl → Ochish. Kutubxonalar `Mod/Ges/vendor` da (paket bilan keladi).

**DWG**: yig'ishda `~/Tools/libredwg/dwg2dxf.exe` (yoki `LIBREDWG_DIR`) topilsa `tools/libredwg/` sifatida paketga
qo'shiladi (https://github.com/LibreDWG/libredwg/releases → win64 zip). Dastur ochilganda `Init.py`
(`ges_workbench/converters.py`) uni topib Draft «DWG converter» sozlamasiga yozadi — ishchi hech narsa
sozlamaydi. Paketda bo'lmasa `~/Tools`, `C:\Tools`, `GES_TOOLS_DIR`, PATH va ODA File Converter qidiriladi.

Versiya: `GesWorkbench/package.xml` `<version>` — installer nomi, o'rnatish papkasi, yangilanish tekshiruvi.
Serverga yuklash: `docs/admin.md`.

## Ishlab chiquvchi uchun (installer siz)
O'rnatilgan FreeCAD ga workbench ni bog'lash: `mklink /J "%APPDATA%\FreeCAD\v1-1\Mod\GesWorkbench" desktop\GesWorkbench`
(FreeCAD 1.1 foydalanuvchi papkasi `%APPDATA%\FreeCAD\v1-1`). FreeCAD ni qayta oching, Workbench → Sath.
Workbench o'zgarganda fork ga: `python desktop/build/sync_fork.py`.

## Testlar
```
python -m pytest desktop/tests                                   # server_client (haqiqiy server oqimda)
"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" desktop\tests\fc_headless.py
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" desktop\tests\fc_gui.py        # yoki Sath.exe; natija %TEMP%\sath\fc_gui.log
```
