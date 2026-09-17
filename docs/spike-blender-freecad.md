# Spike: FreeCAD Blender ichida — natija va tavsiya

Sana: 2026-09-17. Kod: `desktop/blender/spike/` (throwaway), loglar: `spike-45.log`, `spike-52.log`.

## Savol

Blender desktop qobiq bo'lganda FreeCAD **dvigatel** sifatida (`import FreeCAD`) Blender jarayoniga
yuklanadimi — Python ABI, DLL to'qnashuvi, Bonsai bilan birga yashash, DXF/DWG, GES obyektlari?

## Javob: HA, in-process ishlaydi. Ikkala stack ham 37/37 OK, 0 FAIL, GUI rejimida ham.

| Stack | Blender | Python | FreeCAD | numpy (Blender / FC) | Bonsai | Natija |
|---|---|---|---|---|---|---|
| **45** | 4.5.14 LTS | 3.11.15 | 1.1.3 rasmiy installer (`C:\Program Files\FreeCAD 1.1`) | 1.26.4 / 1.26.4 | 0.8.5-post1 | 37/37 OK |
| **52** | 5.2.2 LTS | 3.13.13 | 1.1.3 conda-forge `py313` (micromamba, `~\Tools\fc-py313`) | 2.3.4 / 2.5.3 | 0.8.5 | 37/37 OK |

### Qadamlar bo'yicha

| Qadam | 45 | 52 | Izoh |
|---|---|---|---|
| S2 `import FreeCAD` | 0.15 s | 0.2 s | `os.add_dll_directory(bin, lib)` + `sys.path` (bin, lib, Ext, site-packages OXIRIDA). Xato yo'q. |
| S3a `Part.makeBox` → mesh | OK | OK | mm → m (×0.001), `from_pydata` |
| S3b 7 GES obyekt (`ges_objects.make`) | OK | OK | FeaturePython GUI'siz ishlaydi, `IfcType`/`IfcProperties` to'g'ri |
| S3c Import/Mesh/MeshPart/Sketcher/Draft/importDXF/Spreadsheet/TechDraw | OK | OK | Draft uchun FreeCAD'ning PySide6 kerak — Blender ichida yuklanadi (QtCore, QApplication yo'q) |
| S4 DWG→DXF (libredwg) → `Import.readDXF` (C++) va `importDXF.insert` (Draft) → Blender curve | OK | OK | readDXF Layer obyektlari Draft'ga tayanadi → site-packages shart; hujjat `setActiveDocument` bo'lishi kerak |
| S5 Bonsai yoqish → FreeCAD yuklash → IFC ochish → `Pset_GES_*` o'qish → FreeCAD shape Bonsai sahnasida → FreeCAD `nativeifc` | OK | OK | Bitta ifcopenshell (Bonsai'niki) ishlatiladi, FreeCAD'niki chetda qoladi |
| S6 stress 10×7 obyekt + tessellate, GUI rejimida ham | 17 s | 21 s | RSS +90 MB (549→642), hujjatlar yopilganda ham — pastga qarang |
| S7 subprocess RPC fallback | — | — | **Kerak bo'lmadi** |

GES obyektlari (ikkala stackda bir xil):

| Obyekt | uchburchak | make | tessellate→bpy |
|---|---|---|---|
| Dam | 12 | 240 ms (birinchi, Part init) | 1 ms |
| Penstock | 1 240 | 5 ms | 10 ms |
| Turbine | 59 656 | 11 ms | ~1 600 ms |
| Spillway | 12 | 1 ms | 1 ms |
| Powerhouse | 16 | 4 ms | 1 ms |
| Transformer | 1 684 | 92 ms | 18 ms |
| Intake | 44 | 9 ms | 2 ms |

## Nima uchun DLL to'qnashuvi bo'lmadi

Blender va FreeCAD 20 ta bir nomli DLL tashiydi (`python311.dll`, `tbb12.dll`, `tbbmalloc.dll`, `openexr*.dll`,
`avcodec-61.dll`…, `vulkan-1.dll`). Windows yuklovchisi nom bo'yicha allaqachon yuklangan modulni qaytaradi —
FreeCAD `.pyd`lari Blender'ning nusxasini oladi. OCC/boost/Coin/Qt DLL'lari faqat FreeCAD'da bor, to'qnashmaydi.
Ikki Python minor versiyasi bir xil bo'lishi **shart** (4.5↔3.11, 5.2↔3.13) — shu sababli 5.2 uchun conda-forge
`py313` build kerak (rasmiy FreeCAD installer 3.11).

## Tavsiya

1. **Ko'prik: in-process** (`import FreeCAD` Blender python'ida). Subprocess RPC kerak emas.
2. **Fork bazasi: Blender 5.2 LTS + FreeCAD conda-forge py3.13** (stack 52).
   - 5.2 LTS qo'llab-quvvatlash 4.5 dan ~1 yil uzoqroq; Bonsai 0.8.5+ 5.1+ ga yo'nalgan.
   - FreeCAD conda paketini pixi bilan olish fork CI'siga tabiiy tushadi (fork CI allaqachon pixi/rattler-build).
   - Blender fork qilinganda Python versiyasi bizning nazoratda — kelajakda 3.11 muammosi yo'q.
   - Stack 45 ishonchli zaxira: rasmiy installerlar bilan hech narsa kompilyatsiya qilmasdan ishlaydi.
3. **Yuklash retsepti** (`fc_bridge.load_freecad`): `add_dll_directory(Library/bin, Library/lib)`;
   `sys.path += [bin, lib, Ext, Lib/site-packages]` — site-packages **oxirida**, shunda Blender numpy va Bonsai
   ifcopenshell ustun turadi; FreeCAD site-packages faqat PySide6/pivy kabi Blender'da yo'q paketlar uchun.
4. Bonsai ifcopenshell'i bilan FreeCAD `nativeifc` ham ishlaydi → `ifc_io.py` mantiqini ko'chirishda ikkita
   ifcopenshell tashish shart emas.

## Kuzatuvlar / 2-bosqich uchun ochiq savollar

- **Tessellate tezligi**: `shape.tessellate()` Python ro'yxat + `from_pydata` — 60k uchburchak 1.6 s. 2-bosqichda
  `MeshPart.meshFromShape` → `mesh.Topology`/`Points` numpy massiv → `mesh.vertices.foreach_set` (10–50× tez).
- **Xotira**: 70 obyekt + 10 hujjat yopilganda RSS +50…+90 MB ushlab qolinadi (OCC kesh / FreeCAD hujjat
  ob'ektlari). Addonda uzoq seans soak test kerak; kerak bo'lsa FreeCAD hujjatini bitta ushlab, obyektlarni
  qayta ishlatish.
- **PySide6 Blender ichida**: Draft/importDXF uchun QtCore yetarli; hech qachon `QApplication` yaratmaslik
  (Blender event loop bilan to'qnashadi). Draft'ning GUI qismlariga (`DraftGui`) tegmaslik.
- **DXF**: FreeCAD'ning 1.1 C++ importeri ham, Draft python importeri ham ishlaydi. `dxf_prepare.py`
  (ezdxf) uchun ezdxf'ni Blender extension wheel sifatida qo'shish (`vendor/` hozir repoda yo'q).
- **Birlik**: FreeCAD mm, Blender/IFC m — ko'prikda ×0.001; `ges_objects` psetlarida qiymatlar allaqachon metr.
- **FreeCAD hujjat ↔ Blender obyekt bog'lash**: GES obyektini qayta hisoblash (parametr o'zgarganda) uchun
  Blender custom property ← FreeCAD obyekt nomi; `recompute()` → mesh yangilash. Bonsai'da esa element
  IFC'da yashaydi — qaror: GES parametrik obyektlar **IFC + Pset** (Bonsai manba) bo'lsin, FreeCAD faqat
  geometriya generatori (stateless) — spec'da hal qilinadi.
- **Fayl hajmi**: FreeCAD conda muhiti ~1.2 GB (Qt, OCC, PySide6, pivy...). Bundle uchun Gui/PySide6 qismini
  kesish mumkinmi — S4 ko'rsatdi Draft PySide6'siz import bo'lmaydi; Draft'siz (faqat Part/Import/Mesh) ~400 MB.
- **Blender 5.2 GUI + PowerShell pipe**: GUI jarayon chiqishi pipe'da kesiladi — `run.ps1` faylga yo'naltiradi
  (crash emas, exit 0).

## Qayta ishga tushirish

```
cd desktop\blender\spike
.\run.ps1             # stack 45: ~\Tools\blender-4.5 + C:\Program Files\FreeCAD 1.1
.\run.ps1 -Stack 52   # stack 52: ~\Tools\blender-5.2 + ~\Tools\fc-py313 (micromamba: freecad=1.1.3=py313*)
```
Bonsai: `blender -b --command extension install-file --repo user_default --enable <bonsai zip>`.
GUI natijasi: `%TEMP%\ges_spike_gui.blend` (7 GES obyekt + kub + DXF).
