# Sath Desktop

Desktop klient — **Blender 5.2 extension** `blender/sath` (Bonsai IFC; GES geometriyasi sof Python — FreeCAD siz).
Batafsil: [`blender/README.md`](blender/README.md); bundle (`Sath.exe`, installer): `build/build_blender_bundle.py`.

## Tuzilma
- `blender/sath/` — addon; `blender/template/` — Sath app template; `blender/fork/` — Blender brend forki skriptlari
- `build/` — `sync_blender.py` (umumiy modullar nusxasi, `--check`), `build_blender_addon.py`, `build_blender_bundle.py`,
  `publish_desktop.py` (serverga yuklash, Ed25519 imzo), `ci_blender_setup.py`
- `tests/` — pytest (`test_*.py`, Blender siz) va headless Blender testlari (`run_blender_tests.ps1`, `sath_tests/`);
  `data/ges_golden.json` — GES turlari uchun FreeCAD etaloni (paritet testlari)

## Legacy: FreeCAD (arxivlangan)
FreeCAD 1.1.3 forki (`Sath-FreeCAD`), `GesWorkbench/` workbench, `build_portable.py`/`sync_fork.py`, FreeCAD
testlari va Blender+FreeCAD spike Poydevor P2 da (roadmap K1) repodan olib tashlandi. Oxirgi holat —
`archive/freecad-legacy` tegida:

    git show archive/freecad-legacy:desktop/GesWorkbench/LEGACY.md
    git checkout archive/freecad-legacy -- desktop/GesWorkbench   # kerak bo'lsa vaqtincha tiklash

Serverda avval yuklangan `Sath-FreeCAD-*` paketlari (`?product=freecad`) qoladi, yangilari yig'ilmaydi.
