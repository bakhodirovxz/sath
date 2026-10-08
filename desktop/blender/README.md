# Sath Blender addoni (`sath`)

Sath desktop Blender 5.2 LTS ichida: server (loyiha/model/versiya, commit, tasdiqlash, issue lar, versiyalar farqi), GES parametrik obyektlari, simulyatsiya katalogi va xavfsizlik tekshiruvi, SCADA monitoring, DWG/DXF va mesh import. IFC — **Bonsai** da; GES geometriyasi — sof Python (`shared/geom`, `shared/ges_kinds`, numpy), FreeCAD kerak emas.

## Talablar

- Blender **5.2 LTS** (Python 3.13) — `~\Tools\blender-5.2`
- Bonsai **0.9.0+** extension (Edit → Preferences → Get Extensions → Bonsai)
- DWG uchun LibreDWG `dwg2dxf` (`~\Tools\libredwg`) yoki ODA File Converter.

## Tayyor bundle (foydalanuvchi uchun)

```
python desktop/build/build_blender_bundle.py --installer
```
→ `desktop/dist/Sath-Blender-<ver>-Windows-x86_64.zip` va `-installer.exe`: rasmiy Blender 5.2 + **Sath app template**
(splash, bo'sh metr sahna, N-panel ochiq) + `Sath.exe` (konsolsiz launcher, Sath ikonkasi) + `portable/`
(prefs, Bonsai va sath extension lari yoqilgan; `portable/scripts/startup/sath_boot.py` argumentsiz ochilganda ham
Sath template ga o'tkazadi) + `tools/libredwg/`. Bundle hajmi ≈1568 MB (`freecad/` siz). Kerak: `~\Tools\blender-5.2`, `~\Tools\libredwg`, Bonsai zip (`~\Tools`
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
| GES obyektlari | To'g'on, Bosimli quvur (to'g'ri/egri: qiyalik, tirsak radiusi), Turbina, **Generator**, **Chiqarish quvuri**, Suv tashlagich, Mashina zali (yopiq/kesim), **Boshqaruv xonasi**, Transformator, Suv qabul qilgich, **Daryo oqimi kanali** — parametrlar obyektda, geometriya sof Python (`ges_kinds`, FreeCAD bilan paritet ±0.5 %), IFC klass + `Pset_GES_*` Bonsai da; parametr o'zgarsa mesh darhol yangilanadi, IFC — «IFC ga qo'llash» (`sath.sync_ifc`) yoki commit da; qo'shish va «Namuna GES» — bitta undo qadami; qayta ochilganda tur/rol/parametrlar `Pset_SathParametric` dan tiklanadi (K2). **«Namuna GES qurish»** — rasmdagi 9 komponentli stansiya egizagi bir tugma bilan (napor, agregatlar soni, quvvat → joylashuv, egri quvurlar, suv tekisliklari, `obj.ges.role`) |
| Taqriz va issue lar | ota bilan farq (3D rang: yashil/sariq), issue lar (ko'rinishga o'tish, izoh, yangi issue kamera bilan), tasdiqlash so'rovlari (ma'qullash / o'zgartirish / merge / rad — rolga qarab) |
| Simulyatsiya | **Suv ombori/energiya → Blender timeline** (suv sathi keyframe, agregat/generator/transformator rangi yuklama bo'yicha, Francis qo'pol zona sariq, quyi byef Manning reyting egri chizig'i, chiqarish quvuri Thoma σ < σ_c → qizil, tashlama rangi). Server katalogi (barcha turlar), forma pasport/modeldan, natija, xavfsizlik tekshiruvi (12 ssenariy) |
| Egizak simulyatsiyalari | Parametrlar modeldagi obyektlardan: gidrozarba (MOC) — quvur bo'ylab bosim markerlari; regulyator (HYGOV) — rotor aylanishi n·f/f_nom, chastota rangi; transformator (IEC 60076-7) — issiq nuqta rangi; zilzila (EC8) — S_d = S_a(T/2π)² siljish tebranishi. Natija → timeline (namuna GES: «GES obyektlari»). (`sim.run` ruxsati) |
| Monitoring (SCADA) | 5 s da sensorlar, obyektlar alarm yoki sog'liq rangi, suv sathi tekisligi, sensor → 3D |
| Raqamli egizak | napor, agregatlar o'lchangan/kutilgan quvvat va og'ish, jonli xavfsizlik ko'rsatkichlari, aktivlar sog'liq indeksi (aktiv → 3D), vaqt mashinasi (N soat oldingi sath 3D da) |
| Import | DWG/DXF (ezdxf bilan tekislash, qatlam = collection), mesh (assimp: FBX/3DS/OBJ/…) |

- **Modullar:** Edit → Preferences → Add-ons → Sath → «Modullar» — har modul (Taqriz, Simulyatsiya, Monitoring,
  Raqamli egizak, Import, GES obyektlari) belgi bilan jonli yoqiladi/o'chiriladi; bog'liqlari birga (masalan sim
  o'chsa egizak ham). Yuklanmagan modul sababi va traceback shu yerda. `bim` ni o'chirish, agar GES obyektlarida IFC ga yozilmagan
  o'zgarish bo'lsa, rad etiladi — avval «IFC ga qo'llash».
- **Uchinchi tomon modullari:** «Uchinchi tomon modullari» ni yoqing, nashriyotchining ochiq kalitini «Modul kalitlari»
  ga yozing, modul papkasini `<Blender config>/sath_modules/<id>/` ga qo'ying. Faqat imzolangan modul yuklanadi:
  `python desktop/build/sign_module.py --new-key kalit.txt`, `python desktop/build/sign_module.py <papka> --key kalit.txt`.
- **Rollar:** panel va tugmalar loyihadagi ruxsatga qarab — ko'ruvchi commit/simulyatsiyani ko'rmaydi, kulrang
  tugma ustida sababi («Ruxsat yo'q: cr.approve»). Haqiqiy tekshiruv serverda.

## Tuzilma

- `sath/` — extension (`blender_manifest.toml`, `wheels/`)
  - `ifc.py` Bonsai ko'prigi (+ `orphans`) · `flows.py` bpy siz server oqimlari
  - `ops_*.py` operatorlar (modullar `api.adopt` bilan oladi) · `ui.py` yadro panellari (Server, Model, Bildirishnomalar)/menyu · `props.py` sahna holati · `ges_objects.py` parametrik obyektlar
  - `shared/` (`server_client`, `dxf_prepare`, `assimp_load`, `ifc_classes`, `cad_common`, `geom`, `ges_kinds`, `permissions`) — **`common/sath_common`
    nusxasi** (`python desktop/build/sync_blender.py`, CI `--check`)
  - `core/` — `tasks.py` (fon vazifalari, bpy siz), `events.py` (hodisalar shinasi), `ifc_ops.py` (IfcOperator — IFC undo, K4), `ui_tasks.py` (pompa, status bar
    progressi/bekor qilish, `run_op`) — uzoq tarmoq ishlari Blender ni qotirmaydi (K3), `registry.py` (modul reyestri: manifest, imzo, tartib, hayot sikli — bpy siz), `host.py` (reyestrning
    Blender ulagichi, Sozlamalardagi ro'yxat), `perms.py` (rolga sezgir UI), `panels.py` (`SathPanel`)
  - `api.py` — modullar uchun barqaror fasad (`API_VERSION`); `modules/<id>/` — `sath_module.toml` + `__init__.py`
    (`review`, `sim`, `scada`, `twin`, `io`, `bim`); `ops_*.py` o'z joyida, modul ularni `api.adopt` bilan oladi
- Testlar: `pytest desktop/tests` (Blender siz: pure, flows, tasks, events, registry, perms, client threading, `geom`, `ges_kinds` — FreeCAD etaloniga paritet, `data/ges_golden.json`); server: `test_permissions_mirror`;
  `.\desktop\tests\run_blender_tests.ps1` (headless Blender: 22 ta sinov — `modules` yangi (jonli yoqish/o'chirish, imzo, viewer roli); `GES_TEST_SERVER` bilan yana 4 ta server sinovi: e2e_server, commit_conflict, sim_hydro, sim_twin; `tasks_async`, `ops_async` — asinxron yo'l soxta sekin server bilan).
  CI: `desktop-blender` ishi (windows-2022), SKIP taqiqlangan.
- Unumdorlik: `python desktop/tests/perf_baseline.py` → `docs/benchmark-desktop.md`.

Sinalgan: 2026-10-08, Blender 5.2.2, Bonsai 0.9.0, FreeCAD siz — headless 22/22, FAIL 0, SKIP 0 (`SATH_REQUIRE_NO_SKIP=1`); dev server bilan 4 ta (e2e_server, commit_conflict, sim_hydro, sim_twin) OK; bundle ≈1568 MB (freecad/ siz); GUI: Ctrl+Z dan keyin orphans() tekshiruvi qo'lda kutilmoqda; GUI chizish va bundle installer qayta sinalmagan.

Avval sinalgan: 2026-09-17, Blender 5.2.2, Bonsai 0.8.5, FreeCAD 1.1.3 py313 — addon: 10/10 headless (e2e: ulanish → loyiha/model → GES obyekt → commit v1/v2 + CR → diff → ochish → issue → taqriz → sim → monitoring) va GUI chizish;
bundle: zip dan `Sath.exe` (template, addonlar, bundle ichidagi FreeCAD/libredwg, GES obyekt), installer jimgina o'rnatish/o'chirish (yorliq, registr).

## Ma'lum cheklovlar

- ifcopenshell 0.9.0 (Bonsai 0.9.0): katta (30 ming+ yuz) meshni Bonsai ning o'zining «Update Representation» tugmasi bilan
  yangilash tranzaksiya ichida kvadratik sekin (soatlar). Sath o'z `ifc.update_representation` ida buni chiziqli
  yozuv bilan aylanib o'tadi (Ctrl+Z to'liq ishlaydi); Bonsai ning native tugmasi uchun yechim yo'q (upstream).
