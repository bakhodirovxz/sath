# Sath Blender addoni (`sath`)

FreeCAD workbench imkoniyatlari Blender 5.2 LTS ichida: server (loyiha/model/versiya, commit, tasdiqlash,
issue lar, versiyalar farqi), GES parametrik obyektlari, simulyatsiya katalogi va xavfsizlik tekshiruvi,
SCADA monitoring, DWG/DXF va mesh import. IFC — **Bonsai** da yashaydi, **FreeCAD** faqat geometriya/import
dvigateli (Blender jarayoniga `import FreeCAD` bilan yuklanadi — `docs/spike-blender-freecad.md`).

## Talablar

- Blender **5.2 LTS** (Python 3.13) — `~\Tools\blender-5.2`
- Bonsai **0.8.5+** extension (Edit → Preferences → Get Extensions → Bonsai)
- FreeCAD **1.1.3 py313** (conda-forge): `micromamba create -p %USERPROFILE%\Tools\fc-py313 -c conda-forge "freecad=1.1.3=py313*"`
  (yo'l: addon sozlamalari «FreeCAD papkasi» yoki `GES_FC_HOME` env). Rasmiy installer (py3.11) faqat Blender 4.5 bilan mos.
- DWG uchun LibreDWG `dwg2dxf` (`~\Tools\libredwg`) yoki ODA File Converter.

## Tayyor bundle (foydalanuvchi uchun)

```
python desktop/build/build_blender_bundle.py --installer
```
→ `desktop/dist/Sath-<ver>-Windows-x86_64.zip` va `-installer.exe`: rasmiy Blender 5.2 + **Sath app template**
(splash, bo'sh metr sahna, N-panel ochiq) + `Sath.exe` (konsolsiz launcher, Sath ikonkasi) + `portable/`
(prefs, Bonsai va sath extension lari yoqilgan; `portable/scripts/startup/sath_boot.py` argumentsiz ochilganda ham
Sath template ga o'tkazadi) + `freecad/` (conda py313 muhiti, ~0.9 GB ga kesilgan: MKL/VTK/libclang/FEM yo'q)
+ `tools/libredwg/`. Kerak: `~\Tools\blender-5.2`, `~\Tools\fc-py313`, `~\Tools\libredwg`, Bonsai zip (`~\Tools`
yoki avtomatik yuklab olinadi), NSIS (`~\Tools\NSIS`), venv da `pillow` (splash/ikonka).
Oyna sarlavhasi «Sath» bo'lishi uchun manba forki: GitHub Actions **«Blender fork (Sath brend)»** (qo'lda, ~2–3 soat) —
`desktop/blender/fork/brand.py` Blender manbasiga sarlavha/ProductName/ikonka/splash brendini qo'llaydi, artefakt
`sath-blender-<teg>-windows-x64.zip`; uni ochib `build_blender_bundle.py --blender <papka>` bilan bundle yig'iladi.

## O'rnatish (faqat addon, o'z Blender ingizga)

```
python desktop/build/build_blender_addon.py          # → desktop/dist/sath-<ver>.zip (ezdxf, assimp-py wheel lari bilan)
blender --command extension install-file --repo user_default --enable desktop/dist/sath-<ver>.zip
```
yoki Blender: Edit → Preferences → Get Extensions → ▾ → Install from Disk.

## Ishlatish

3D Viewport → `N` yon panel → **Sath** yorlig'i (yoki sarlavha menyusi «Sath», `Ctrl+Shift+G`):

| Panel | Nima beradi |
|---|---|
| Server | manzil, login, parol → Ulanish (yangi versiya va o'qilmagan bildirishnomalar haqida xabar) |
| Model | loyiha → model → versiya; Ochish (Bonsai), Commit (IFC → yangi versiya, ixtiyoriy darhol tasdiqqa), Tasdiqqa yuborish, Webda ochish (`?v=&sel=GUID`) |
| GES obyektlari | To'g'on, Bosimli quvur, Turbina, Suv tashlagich, Mashina zali, Transformator, Suv qabul qilgich — parametrlar obyektda, geometriya FreeCAD dan, IFC klass + `Pset_GES_*` Bonsai da; parametr o'zgarsa qayta quriladi |
| Taqriz va issue lar | ota bilan farq (3D rang: yashil/sariq), issue lar (ko'rinishga o'tish, izoh, yangi issue kamera bilan), tasdiqlash so'rovlari (ma'qullash / o'zgartirish / merge / rad — rolga qarab) |
| Simulyatsiya | server katalogi (barcha turlar), forma pasport/modeldan, hisob (poll), natija, 3D suv sathi (`GES_SuvSathi`), xavfsizlik tekshiruvi (12 ssenariy) |
| Monitoring (SCADA) | 5 s da sensorlar, obyektlar alarm yoki sog'liq rangi, suv sathi tekisligi, sensor → 3D |
| Raqamli egizak | napor, agregatlar o'lchangan/kutilgan quvvat va og'ish, jonli xavfsizlik ko'rsatkichlari, aktivlar sog'liq indeksi (aktiv → 3D), vaqt mashinasi (N soat oldingi sath 3D da) |
| Import | DWG/DXF (FreeCAD importeri, ezdxf bilan tekislash, qatlam = collection), mesh (assimp: FBX/3DS/OBJ/…) |

## Tuzilma

- `sath/` — extension (`blender_manifest.toml`, `wheels/`)
  - `fc_engine.py` FreeCAD yuklash + `ges_build` · `ifc.py` Bonsai ko'prigi · `flows.py` bpy siz server oqimlari
  - `ops_*.py` operatorlar · `ui.py` panellar/menyu · `props.py` sahna holati · `ges_objects.py` parametrik obyektlar
  - `shared/` (`server_client`, `dxf_prepare`, `assimp_load`) va `wb/ges_objects.py` — **workbench nusxasi**
    (`python desktop/build/sync_blender.py`, CI `--check`)
- Testlar: `pytest desktop/tests/test_sath_pure.py desktop/tests/test_sath_flows.py` (Blender siz, real server);
  `.\desktop\tests\run_blender_tests.ps1` (headless Blender: 9 ta sinov, Bonsai + FreeCAD kerak).

Sinalgan: 2026-09-17, Blender 5.2.2, Bonsai 0.8.5, FreeCAD 1.1.3 py313 — addon: 10/10 headless (e2e: ulanish → loyiha/model → GES obyekt → commit v1/v2 + CR → diff → ochish → issue → taqriz → sim → monitoring) va GUI chizish;
bundle: zip dan `Sath.exe` (template, addonlar, bundle ichidagi FreeCAD/libredwg, GES obyekt), installer jimgina o'rnatish/o'chirish (yorliq, registr).
