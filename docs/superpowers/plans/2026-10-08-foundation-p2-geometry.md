# Poydevor P2: FreeCAD siz geometriya (`geom` + `ges_kinds`), K2 round-trip va K4 undo — amalga oshirish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 11 ta GES obyekti va «Namuna GES» FreeCAD siz (sof Python + numpy) quriladi va FreeCAD bilan paritetda (hajm ±0.5 %); FreeCAD desktopdan butunlay chiqadi (bundle ~0.9 GB kichrayadi); serverdan qayta ochilgan GES obyektlari tur/rol/parametrlarini tiklaydi (K2); IFC o'zgarishlari Blender undo bilan bitta qadam, yetim entity qolmaydi (K4).

**Architecture:** `common/sath_common/geom.py` — bpy/FreeCAD siz geometriya yadrosi (numpy massivlar kiradi/chiqadi, boolean siz to'g'ridan-to'g'ri qurish, chord tolerance). `common/sath_common/ges_kinds.py` — 11 tur uchun yagona manba (parametrlar, Pset_GES_* xaritasi, IFC klass, rang, `build`, analitik `quantities`, K2 `Pset_SathParametric` va teskari xaritalash). Ikkalasi `sync_blender.py` bilan `sath/shared/` ga nusxalanadi. Blender tomoni (`ges_objects.py`) sxema va mesh ni `ges_kinds` dan oladi, mesh ni `foreach_set` bilan uzatadi. FreeCAD paritet etaloni (`desktop/tests/data/ges_golden.json`) FreeCAD olib tashlanishidan OLDIN bir marta yoziladi; keyin pytest faqat shu faylga tayanadi. K4: `core/ifc_ops.IfcOperator` mixin Bonsai `IfcStore.execute_ifc_operator` orqali IFC tranzaksiyasini Blender undo qadamiga bog'laydi; parametr o'zgarishi faqat mesh ni quradi va `ifc_dirty` qo'yadi, IFC ga yozish faqat `sath.sync_ifc` da.

**Tech Stack:** Blender 5.2.2 LTS (Python 3.13, bpy, bmesh, numpy), Bonsai 0.9.0 / ifcopenshell 0.9.0; numpy 2.2.6 (`server/requirements.lock`, pytest `.venv` Python 3.10); FreeCAD 1.1.3 py313 (`~/Tools/fc-py313`) — FAQAT Task 1 da; pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-08-sath-foundation-design.md` (§4 K2/K4, §6 FreeCAD funksiyalarini ko'chirish, «Bosqichlar» P2, «Xavflar»); roadmap `docs/roadmap-bim-scada.md` K1, K2, K4.

## Global Constraints

- **Tartib qat'iy:** Task 1 (FreeCAD etaloni) hamma narsadan oldin — FreeCAD (`~/Tools/fc-py313`) o'chirilmaguncha. Task 7 gacha `fc_engine.py` repoda turadi, lekin Task 6 dan keyin hech kim uni GES uchun chaqirmaydi.
- **Qator oxirlari saqlanadi.** Har faylni tahrirlashdan oldin `git ls-files --eol <fayl>`. CRLF fayllar (`w/crlf`): `desktop/blender/sath/{__init__,ges_objects,demo_plant,ifc,sim_anim,ops_sim,physics,water,ops_monitor}.py`, `desktop/blender/README.md`, `desktop/build/build_blender_bundle.py`, `desktop/tests/sath_tests/demo_plant.py`; `flows.py` — `i/mixed`. Write/Edit vositasi LF yozsa, CRLF ni tiklang:
  `python -c "import pathlib,sys; p=pathlib.Path(sys.argv[1]); b=p.read_bytes().replace(b'\r\n',b'\n'); p.write_bytes(b.replace(b'\n',b'\r\n'))" <fayl>`
  Tekshiruv: `git ls-files --eol <fayl>` → avvalgi `w/...`; `git diff --stat <fayl>` faqat haqiqiy o'zgarishni ko'rsatadi (butun fayl qayta yozilmagan). Yangi fayllar — LF (`common/sath_common/`, `desktop/tests/`, `desktop/tests/sath_tests/`, `desktop/blender/sath/core/` LF konvensiyasida).
- **Kodlash UTF-8.** PowerShell `Get-Content`/`Set-Content`/`Out-File` bilan matn faylini YOZMANG (cp1251 mojibake bo'lgan). Edit/Write vositasi yoki `open(..., encoding="utf-8", newline=...)` bilan Python.
- `common/sath_common/*` — kanonik manba; `desktop/blender/sath/shared/*` faqat `python desktop/build/sync_blender.py` bilan yangilanadi, qo'lda tahrirlanmaydi; CI `--check`.
- Sof modullar (`geom.py`, `ges_kinds.py`) Python **3.10** da ishlaydi (pytest `.venv`): `from __future__ import annotations`, `tomllib`/`ExceptionGroup`/3.11+ sintaksis yo'q; faqat numpy (bpy, FreeCAD, ifcopenshell yo'q).
- Ishchi oqim **hech qachon** `bpy` ga tegmaydi. Timer callback (`flush_pending`) da `bpy.ops.*` va IFC yozuvi yo'q (K4).
- Bonsai ichki API faqat `desktop/blender/sath/ifc.py` va `desktop/blender/sath/core/ifc_ops.py` da (spec «Xavflar»).
- Mavjud `bl_idname` lar o'zgarmaydi (`sath.add_object`, `sath.rebuild_object`, `sath.build_demo_plant`, `sath.import_dxf`, `sath.import_mesh`, `sath.commit`); yangilari: `sath.sync_ifc`, `sath.purge_orphans`, `sath.assign_ifc`, `sath.restore_ges`.
- Koordinatalar va Pset_GES_* nomlari/qiymatlari FreeCAD davri bilan bir xil (server `ges_params.py` va eski modellar o'zgarmasdan ishlaydi).
- Foydalanuvchi matnlari o'zbekcha (lotin). Commit xabarlari o'zbekcha (`feat(P2): …`, `fix(K2): …`, `feat(K4): …`, `test(P2): …`, `chore(K1): …`, `docs(…): …`), oxirida bo'sh qator va `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Push qilinmaydi (foydalanuvchi qaroriga ko'ra).
- `ruff check server sim desktop common` toza qoladi (`ruff.toml`: py310, `E,F,I,UP,B`; `zip(..., strict=True)`).
- Buyruqlar (Windows, repo ildizidan): pytest — `.venv\Scripts\python.exe -m pytest …`; ruff — `.venv\Scripts\python.exe -m ruff check …`; headless — `$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; .\desktop\tests\run_blender_tests.ps1`.

## Review Focus

1. **Serverdan eski (FreeCAD davri) modelni ochish** — mesh/GUID o'zgarmaydi (qayta qurilmaydi), tur va rollar Pset_GES_* dan tiklanadi, sim animatsiyasi ishlaydi → Task 8 `roundtrip_ges` (namuna_ges_v1.ifc qismi, `rebuild_mesh` chaqirilmasligi).
2. **Obyekt qo'shib Ctrl+Z bosish yoki «Namuna GES» ni orqaga qaytarish** — IFC da yetim element/pset/representation qolmaydi; commit dialogi yetimlarni ko'rsatadi va tozalaydi, Bonsai yuklamagan oddiy elementlarga tegmaydi → Task 9 `undo_ifc`, `ifc.orphans()` doirasi.
3. **Parametrni sudrab o'zgartirish va darhol commit** — har qadamda IFC tranzaksiyasi yo'q, commit boshida `sath.sync_ifc` hammasini yozadi, serverga eskirgan pset ketmaydi → Task 9 `objects` (dirty → sync), `ops_server.commit`.
4. **FreeCAD siz geometriya to'g'riligi** (eng xavflisi: mashina zali «Kesim», suv qabul qilgich teshiklari, egri quvur, chiqarish quvuri tirsagi) — FreeCAD etaloniga hajm/bbox/pset paritet, web qoralama pset farqlari ro'yxatda → Task 3–5 `test_ges_kinds`.
5. **FreeCAD yo'q mashina/CI** — barcha headless testlar OK, SKIP 0 (CI da SKIP taqiqlangan), bundle `freecad/` siz va unda GES obyekti quriladi; legacy kod `archive/freecad-legacy` tegidan tiklanadi → Task 6–7.

---

## Fayl tuzilmasi

| Fayl | Mas'uliyat |
|---|---|
| `desktop/tests/gen_fc_golden.py` (yangi, bir martalik) | FreeCAD bilan etalon: 11 tur × 3–4 holat → JSON |
| `desktop/tests/data/ges_golden.json` (yangi, generatsiya) | Volume/Area/BoundBox, sxema, IFC klass, rang, Pset_GES_* |
| `common/sath_common/geom.py` (yangi) → `sath/shared/geom.py` | numpy geometriya: box/cylinder/cone/torus/extrude/revolve/sweep/loft, triangulyatsiya, hajm/yuza/bbox/yopiqlik |
| `common/sath_common/ges_kinds.py` (yangi) → `sath/shared/ges_kinds.py` | 11 tur: parametrlar, Pset xaritasi, `build`, `quantities`, `psets`, `parametric_pset`, `from_psets`, `infer_roles` |
| `desktop/tests/test_geom.py`, `test_ges_kinds.py` (yangi) | pytest: geometriya xossalari, FreeCAD paritet, K2 teskari xaritalash, web farqlari |
| `desktop/build/sync_blender.py` (o'zgaradi) | `geom.py`, `ges_kinds.py` nusxasi; Task 7 da `wb/` va GesWorkbench nusxalari olib tashlanadi |
| `desktop/blender/sath/ges_objects.py` (o'zgaradi) | sxema/mesh `ges_kinds` dan, `set_mesh` (foreach_set), K2 `restore_from_ifc`, K4 `ifc_dirty`/`sync_ifc`/operatorlar |
| `desktop/blender/sath/demo_plant.py` (o'zgaradi) | `_add` parametrlarni yaratishda beradi; K4 `IfcOperator` |
| `desktop/blender/sath/ifc.py` (o'zgaradi) | `write_psets(text=…)` (IfcText), `orphans()`, `purge_orphans()` |
| `desktop/blender/sath/core/ifc_ops.py` (yangi) | `IfcOperator` mixin, `SathOpError`, `last_key`/`undo_to`/`rebuild_maps` |
| `desktop/blender/sath/sim_anim.py`, `ops_sim.py` (o'zgaradi) | `TwinBindingError` — jim `if o is not None` o'rniga |
| `desktop/blender/sath/ops_import.py`, `ops_server.py`, `flows.py` (o'zgaradi) | FreeCAD DXF yo'li olib tashlanadi; import/assign `IfcOperator`; commit: sync + yetimlar |
| `desktop/blender/sath/{prefs,converters,cad_read,__init__}.py`, `blender_manifest.toml` (o'zgaradi) | FreeCAD papkasi/yo'llari olib tashlanadi |
| `desktop/blender/sath/fc_engine.py`, `sath/wb/` (o'chiriladi) | — |
| `desktop/GesWorkbench/`, `desktop/blender/spike/`, `desktop/build/{sync_fork,build_portable}.py`, `desktop/tests/{fc_cad,fc_gui,fc_headless,test_freecad_cad}.py`, `desktop/tests/Namuna GES.FCStd` (o'chiriladi, `archive/freecad-legacy` tegida) | legacy FreeCAD trek |
| `desktop/build/build_blender_bundle.py` (o'zgaradi) | `freecad/` nusxasi, `--fc-home`, `--no-freecad` olib tashlanadi |
| `desktop/tests/sath_tests/kinds_mesh.py`, `roundtrip_ges.py`, `undo_ifc.py` (yangi); `engine.py` (o'chiriladi); `objects.py`, `demo_plant.py`, `e2e_server.py`, `import_ezdxf.py`, `import_ops.py`, `_req.py` (o'zgaradi) | headless testlar |
| `desktop/tests/run_blender_tests.ps1`, `blender_headless.py`, `blender_gui_check.py`, `.github/workflows/ci.yml` (o'zgaradi) | ro'yxat; `SATH_REQUIRE_NO_SKIP` |
| `desktop/tests/test_sath_pure.py`, `test_sath_import.py`, `test_server_client.py`, `server/tests/test_ifc43.py` (o'zgaradi) | FreeCAD/GesWorkbench havolalari olib tashlanadi |
| `desktop/blender/README.md`, `desktop/README.md`, `docs/admin.md`, `docs/roadmap-bim-scada.md`, `ruff.toml` (o'zgaradi) | hujjat, K1/K2/K4 belgilari |

`props.py` o'zgarmaydi: `Object.ges` (kind/role/params) `ges_objects.py` da, K2 uni IFC dan tiklaydi (snapshot ga kiritish shart emas).

---

### Task 1: FreeCAD etaloni — `gen_fc_golden.py` → `ges_golden.json`

**Model:** haiku — to'liq kod va kutilgan raqamlar berilgan, faqat yozish va ishga tushirish.

FreeCAD olib tashlanishidan oldingi YAGONA FreeCAD ga bog'liq qadam. Skript mavjud `sath.fc_engine` (FreeCAD `wb/ges_objects.py` ni yuklaydi) orqali har tur uchun default, «Namuna GES» (agregat 1, `demo_plant.build(head 45, 2 agregat, 25 MW, zero 850)` formulalari) va qo'shimcha holatlarni quradi.

**Files:**
- Create: `desktop/tests/gen_fc_golden.py`
- Create (generatsiya): `desktop/tests/data/ges_golden.json`

**Interfaces:**
- Produces: `ges_golden.json` = `{"generator": {...}, "kinds": {<kind>: {"label", "ifc_class", "color": [r,g,b], "schema": [{"name","label","type","default","items"}], "cases": [{"id","params","volume_m3","area_m2","bbox_m":[xmin,ymin,zmin,xmax,ymax,zmax],"solids","ifc_class","psets"}]}}}` — 11 tur, 39 holat; holat id lari `default`, `demo`, `x1`, `x2`. Task 3–5 testlari shu formatga tayanadi.

- [ ] **Step 1: FreeCAD muhiti borligini tekshiring**

```powershell
& "$HOME\Tools\fc-py313\python.exe" -c "import sys; print(sys.version.split()[0])"
Test-Path "$HOME\Tools\fc-py313\Library\bin\FreeCAD.pyd"
```
Expected: `3.13.x` va `True`. Yo'q bo'lsa — TO'XTANG va foydalanuvchiga xabar bering (etalonsiz keyingi vazifalar mumkin emas).

- [ ] **Step 2: Skriptni yarating** — `desktop/tests/gen_fc_golden.py`

```python
"""Bir martalik: FreeCAD (sath/wb/ges_objects.py) bo'yicha GES turlarining etalon qiymatlari →
desktop/tests/data/ges_golden.json. FreeCAD olib tashlanishidan OLDIN ishga tushirilgan (P2, Task 1); keyin
`ges_kinds` paritet testlari (pytest, CI) faqat shu faylga tayanadi — FreeCAD kerak emas. FreeCAD olib tashlangach
(P2 Task 7) skript `archive/freecad-legacy` tegida ishga tushiriladi (etalonni qayta yozish kerak bo'lsa).

    %USERPROFILE%\\Tools\\fc-py313\\python.exe desktop/tests/gen_fc_golden.py [--out <json>]

Har tur uchun: label, ifc_class, rang, sxema (FreeCAD «GES» xususiyatlari: nom, izoh, tur, default, enum) va
3–4 holat (default, «Namuna GES» agregat 1, qo'shimcha): to'liq parametrlar (metr), Volume (m³), Area (m²),
aniq BoundBox (m), qattiq jismlar soni, Pset_GES_* (fc_engine._parse_props bilan, Blender ga yozilgandek).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "desktop" / "tests" / "data" / "ges_golden.json"
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
os.environ.setdefault("GES_FC_HOME", str(Path.home() / "Tools" / "fc-py313"))

from sath import fc_engine, physics  # noqa: E402

KINDS = (
    "GES_Dam", "GES_Penstock", "GES_Turbine", "GES_Spillway", "GES_Powerhouse", "GES_Transformer",
    "GES_Intake", "GES_Generator", "GES_DraftTube", "GES_ControlRoom", "GES_Tailrace",
)  # fmt: skip
EXTRA: dict[str, list[dict]] = {
    "GES_Dam": [dict(Length=100.0, Height=30.0, CrestWidth=8.0, BaseWidth=24.0, DamType="Arkali", ConcreteClass="B30", CrestElevation=850.0, BaseElevation=820.0)],
    "GES_Penstock": [dict(Length=60.0, Inclination=40.0), dict(Length=35.0, Diameter=3.2, WallThickness=0.03, Material="GRP", Roughness=0.05)],
    "GES_Turbine": [dict(RunnerDiameter=4.5, Height=6.0, TurbineType="Kaplan", RatedPower=40.0), dict(RunnerDiameter=1.2, Height=2.0, TurbineType="Pelton")],
    "GES_Spillway": [dict(Width=20.0, Length=30.0, Thickness=1.5, Gates=3, DischargeCoefficient=0.48)],
    "GES_Powerhouse": [dict(View="Kesim")],
    "GES_Transformer": [dict(Length=8.0, Width=5.0, Height=6.0, RatedPower=63.0, Cooling="ODAF"), dict(Length=3.0, Width=2.0, Height=2.5)],
    "GES_Intake": [dict(Openings=1), dict(Width=60.0, Openings=4, ScreenBarSpacing=80.0)],
    "GES_Generator": [dict(StatorDiameter=9.0, Height=5.0, Poles=32, Frequency=60.0)],
    "GES_DraftTube": [dict(InletDiameter=4.5, ConeHeight=7.0, OutletWidth=11.0, OutletHeight=5.0, DiffuserLength=18.0), dict(InletDiameter=2.0, ConeHeight=3.0, OutletWidth=3.0, OutletHeight=3.0, DiffuserLength=6.0)],
    "GES_ControlRoom": [dict(Length=20.0, Width=10.0, Height=5.0, FloorElevation=10.0, Operators=4), dict(Length=6.0, Width=4.0, Height=3.0)],
    "GES_Tailrace": [dict(Width=10.0, Length=25.0, Depth=4.0, WallThickness=0.5)],
}  # fmt: skip


def demo_params(head_m: float = 45.0, units: int = 2, unit_mw: float = 25.0, zero_m: float = 850.0) -> dict[str, dict]:
    """demo_plant.build dagi formulalar (agregat 1) — «Namuna GES» holati (sath_tests/demo_plant bilan bir xil kirish)."""
    rho_g, tailwater, bed, spacing, y_turbine = 9806.65, -2.0, -12.0, 14.0, 22.0
    n, h = units, head_m
    z_up = tailwater + h
    crest = z_up + 3.0
    dam_h = crest - bed
    bw = round(0.8 * dam_h, 1)
    h_net = 0.95 * h
    q_unit = unit_mw * 1e6 / (rho_g * h_net * 0.92)
    d_pen = math.sqrt(4 * q_unit / (math.pi * 4.0))
    z_sill = z_up - min(25.0, 0.55 * h)
    z_in = z_sill + 3.0
    y_in = -(bw - 6.0) / 2 * (z_in - bed) / dam_h + 0.5
    alpha, length = physics.solve_penstock(z_in + 2.0, (y_turbine - 2.6) - y_in, 8.0, 6.0)
    return {
        "GES_Dam": dict(Length=n * spacing + 60.0, Height=dam_h, CrestWidth=6.0, BaseWidth=bw, CrestElevation=zero_m + crest, BaseElevation=zero_m + bed),
        "GES_Penstock": dict(Length=round(length, 2), Diameter=round(d_pen, 2), WallThickness=0.02, Roughness=0.1, Inclination=round(alpha, 3), BendRadius=8.0, OutletLength=6.0),
        "GES_Turbine": dict(TurbineType="Francis", RatedPower=unit_mw, RatedHead=round(h_net, 1), RatedFlow=round(q_unit, 2), Efficiency=0.92, RunnerDiameter=3.0, Height=4.0),
        "GES_Spillway": dict(Width=12.0, Length=bw + 4.0, Thickness=1.0, CrestElevation=zero_m + z_up, Gates=2),
        "GES_Powerhouse": dict(Length=n * spacing + 16.0, Width=36.0, Height=22.0, Units=n, FloorElevation=zero_m, View="Kesim"),
        "GES_Transformer": dict(RatedPower=round(unit_mw / 0.9, 1), VoltageHV=110.0, VoltageLV=10.5),
        "GES_Intake": dict(Width=n * spacing + 6.0, Depth=8.0, Height=crest + 2.0 - z_sill, SillElevation=zero_m + z_sill, DesignFlow=round(n * q_unit, 1), Openings=n),
        "GES_Generator": dict(RatedPower=round(unit_mw / 0.9, 1), Voltage=10.5, Poles=48, Frequency=50.0, StatorDiameter=6.0, Height=3.5),
        "GES_DraftTube": dict(InletDiameter=3.0, ConeHeight=5.0, OutletWidth=8.0, OutletHeight=4.0, DiffuserLength=12.0, SuctionHead=round(-2.0 - tailwater, 2)),
        "GES_ControlRoom": dict(Length=12.0, Width=8.0, Height=4.0, FloorElevation=zero_m + 10.0),
        "GES_Tailrace": dict(Width=n * spacing + 10.0, Length=40.0, Depth=11.0, BedSlope=0.001, Manning=0.03, BedElevation=zero_m + bed, DesignTailwater=zero_m + tailwater, DesignFlow=round(n * q_unit, 1)),
    }  # fmt: skip


def _bbox(shape) -> list[float]:
    try:
        bb = shape.optimalBoundingBox(False, False)  # aniq (triangulyatsiyasiz)
    except Exception:  # noqa: BLE001 — eski OCC
        bb = shape.BoundBox
    return [bb.XMin / 1e3, bb.YMin / 1e3, bb.ZMin / 1e3, bb.XMax / 1e3, bb.YMax / 1e3, bb.ZMax / 1e3]


def _case(kind: str, schema: list[dict], cid: str, overrides: dict) -> dict:
    params = {f["name"]: f["default"] for f in schema}
    unknown = set(overrides) - set(params)
    assert not unknown, (kind, unknown)
    params.update(overrides)
    b = fc_engine.ges_build(kind, params)
    s = fc_engine.last_shape()
    return {
        "id": cid, "params": params, "volume_m3": s.Volume / 1e9, "area_m2": s.Area / 1e6, "bbox_m": _bbox(s),
        "solids": len(s.Solids), "ifc_class": b.ifc_class, "psets": b.psets,
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    fc = fc_engine.load()
    labels = dict(fc_engine.ges_kinds())
    demo = demo_params()
    out: dict = {
        "generator": {
            "script": "desktop/tests/gen_fc_golden.py", "freecad": ".".join(fc.Version()[:3]),
            "python": platform.python_version(), "date": date.today().isoformat(), "units": "m, m2, m3",
        },
        "kinds": {},
    }  # fmt: skip
    n = 0
    for kind in KINDS:
        schema = fc_engine.ges_schema(kind)
        cases = [_case(kind, schema, "default", {}), _case(kind, schema, "demo", demo[kind])]
        cases += [_case(kind, schema, f"x{i}", ov) for i, ov in enumerate(EXTRA[kind], start=1)]
        out["kinds"][kind] = {
            "label": labels[kind], "ifc_class": cases[0]["ifc_class"], "color": list(fc_engine.ges_color(kind)[:3]),
            "schema": schema, "cases": cases,
        }  # fmt: skip
        for c in cases:
            n += 1
            print(f"GOLD {kind:16} {c['id']:8} V={c['volume_m3']:.6f} A={c['area_m2']:.4f} solids={c['solids']}", flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"[OK] gen_fc_golden: {n} holat -> {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Etalonni yozing**

Run: `& "$HOME\Tools\fc-py313\python.exe" desktop/tests/gen_fc_golden.py`
Expected (2026-10-08 da shu kod bilan sinalgan; ~1 daqiqa), jumladan:
```
GOLD GES_Dam          default  V=13200.000000 A=4233.8634 solids=1
GOLD GES_Penstock     x1       V=9.123185 A=912.6226 solids=1
GOLD GES_Turbine      default  V=27.209736 A=84.3883 solids=2
GOLD GES_Powerhouse   default  V=15696.000000 A=3865.7427 solids=1
GOLD GES_Powerhouse   x1       V=1115.574816 A=3813.2683 solids=1
GOLD GES_Transformer  default  V=74.056991 A=161.2899 solids=1
GOLD GES_Intake       default  V=903.575520 A=679.8740 solids=1
GOLD GES_Generator    default  V=79.698273 A=132.3727 solids=1
GOLD GES_DraftTube    default  V=429.170100 A=469.6717 solids=3
GOLD GES_ControlRoom  default  V=370.193280 A=370.2172 solids=1
GOLD GES_Tailrace     default  V=1075.200000 A=2805.7600 solids=1
[OK] gen_fc_golden: 39 holat -> ...\desktop\tests\data\ges_golden.json
```
Boshqa qiymat chiqsa — TO'XTANG: FreeCAD versiyasi (`generator.freecad` = `1.1.3`) yoki `wb/ges_objects.py` o'zgargan; sababini aniqlamasdan davom etmang.

- [ ] **Step 4: Faylni tekshiring (FreeCAD siz Python bilan)**

```powershell
.venv\Scripts\python.exe -c "import json; g=json.load(open('desktop/tests/data/ges_golden.json',encoding='utf-8')); k=g['kinds']; print(len(k), sum(len(v['cases']) for v in k.values()), k['GES_Dam']['ifc_class'], [f['name'] for f in k['GES_Dam']['schema']][:3], k['GES_Generator']['cases'][1]['psets']['Pset_GES_Generator']['Aylanish_rpm'])"
git ls-files --eol desktop/tests/data/ges_golden.json; git add -N desktop/tests/data/ges_golden.json; git ls-files --eol desktop/tests/data/ges_golden.json
```
Expected: `11 39 IfcWall ['BaseElevation', 'BaseWidth', 'ConcreteClass'] 125.0` (FreeCAD `PropertiesList` alfavit tartibida — `ges_kinds` mantiqiy tartibda saqlaydi, testlar nom bo'yicha solishtiradi); `w/lf`.

- [ ] **Step 5: ruff**

Run: `.venv\Scripts\python.exe -m ruff check desktop/tests/gen_fc_golden.py` → `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add desktop/tests/gen_fc_golden.py desktop/tests/data/ges_golden.json
git commit -m "test(P2): FreeCAD etaloni — 11 GES turi, 39 holat (hajm, yuza, aniq bbox, Pset_GES_*), FreeCAD olib tashlanishidan oldin" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `common/sath_common/geom.py` — sof geometriya yadrosi

**Model:** sonnet — to'liq kod berilgan, lekin tessellatsiya/yo'nalish xatolarini testlar bilan tekshirish kerak.

**Files:**
- Create: `common/sath_common/geom.py`
- Create: `desktop/tests/test_geom.py`
- Modify: `desktop/build/sync_blender.py:23,33-36` (FILES, EXTRA)
- Generated: `desktop/blender/sath/shared/geom.py`

**Interfaces:**
- Produces: `geom.Mesh = tuple[np.ndarray, np.ndarray]` (V `(n,3)` float64 metr, F `(m,3)` int64, normal tashqariga); `TOL=0.005`, `MIN_SEG=64`, `MAX_SEG=512`; `segments(radius, tol=TOL) -> int`; `circle(r, n, center=(0,0)) -> (n,2)`; `merge(*meshes)`, `transform(m, matrix4x4)`, `translate(m, offset)`; `signed_volume(m)`, `area(m)`, `bbox(m) -> [xmin,ymin,zmin,xmax,ymax,zmax]`, `is_closed(m)`; `triangulate(poly2d) -> (n-2,3)`; `extrude(poly3d, vec)`, `box(size, origin)`, `revolve(profile_rz, angle=2π, *, tol, matrix=None)`, `cylinder(r, h, *, base, tol)`, `cone(r1, r2, h, *, base, tol)`, `torus(big_r, r, *, center, tol)`, `sweep(profile, path, tangents, normal, *, hole=None)`, `loft(ring_a, ring_b)`. Task 3–6 shularga tayanadi.

- [ ] **Step 1: Testni yozing** — `desktop/tests/test_geom.py`

```python
"""common/sath_common/geom.py — sof geometriya yadrosi (FreeCAD siz): yopiqlik, tashqi normallar, analitik hajm,
chord tolerance, bbox aniqligi, ear clipping, aks ettirish."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import geom  # noqa: E402


def _outward_convex(m, center) -> bool:
    """Qavariq shakl: har yuz normali markazdan tashqariga qaraydi."""
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    return bool((np.einsum("ij,ij->i", n, (a + b + c) / 3 - np.asarray(center)) > 0).all())


def test_segments_tolerance_multiple_of_four():
    for r in (0.05, 0.6, 3.0, 25.0, 400.0):
        n = geom.segments(r)
        assert n % 4 == 0 and geom.MIN_SEG <= n <= geom.MAX_SEG
        if geom.MIN_SEG < n < geom.MAX_SEG:
            assert r * (1 - math.cos(math.pi / n)) <= geom.TOL + 1e-12, r
    assert geom.segments(25.0, tol=0.001) > geom.segments(25.0)


def test_box_closed_outward_exact():
    m = geom.box((2.0, 3.0, 4.0), (1.0, -1.0, 0.5))
    assert geom.is_closed(m) and _outward_convex(m, (2.0, 0.5, 2.5))
    assert geom.signed_volume(m) == pytest.approx(24.0) and geom.area(m) == pytest.approx(52.0)
    assert geom.bbox(m).tolist() == [1.0, -1.0, 0.5, 3.0, 2.0, 4.5]


@pytest.mark.parametrize(
    "mesh,exact,bb",
    [
        (lambda: geom.cylinder(1.5, 4.0, base=(1.0, 2.0, -1.0)), math.pi * 1.5**2 * 4.0, [-0.5, 0.5, -1.0, 2.5, 3.5, 3.0]),
        (lambda: geom.cone(2.0, 0.5, 3.0), math.pi * 3.0 / 3 * (4.0 + 1.0 + 0.25), [-2.0, -2.0, 0.0, 2.0, 2.0, 3.0]),
        (lambda: geom.cone(1.0, 0.0, 2.0), math.pi * 2.0 / 3, [-1.0, -1.0, 0.0, 1.0, 1.0, 2.0]),
        (lambda: geom.torus(2.1, 0.6), 2 * math.pi**2 * 2.1 * 0.36, [-2.7, -2.7, -0.6, 2.7, 2.7, 0.6]),
    ],
    ids=["cylinder", "frustum", "cone", "torus"],
)
def test_revolved_primitives(mesh, exact, bb):
    m = mesh()
    assert geom.is_closed(m)
    vol = geom.signed_volume(m)
    assert 0 < vol <= exact and vol == pytest.approx(exact, rel=4e-3)  # ichki chizilgan: biroz kichik, ≤ 2·θ²/6
    assert geom.bbox(m) == pytest.approx(bb, abs=1e-9)  # n 4 ga karrali — ekstremumlar aniq


def test_cylinder_normals_outward():
    assert _outward_convex(geom.cylinder(1.0, 2.0), (0.0, 0.0, 1.0))


def test_extrude_concave_u_profile():
    u = [(-3, 0, -1), (3, 0, -1), (3, 0, 4), (2, 0, 4), (2, 0, 0), (-2, 0, 0), (-2, 0, 4), (-3, 0, 4)]
    m = geom.extrude(u, (0.0, 10.0, 0.0))
    assert geom.is_closed(m)
    assert geom.signed_volume(m) == pytest.approx(10.0 * (6 * 5 - 4 * 4))
    m2 = geom.extrude(u[::-1], (0.0, 10.0, 0.0))  # teskari aylanish — natija bir xil
    assert geom.signed_volume(m2) == pytest.approx(geom.signed_volume(m))


def test_triangulate_orientation_and_errors():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    t = geom.triangulate(sq)
    assert t.shape == (2, 3)
    p = np.asarray(sq, float)
    assert all(geom._cross2(p[a], p[b], p[c]) > 0 for a, b, c in t)
    tcw = geom.triangulate(sq[::-1])
    pcw = p[::-1]
    assert all(geom._cross2(pcw[a], pcw[b], pcw[c]) < 0 for a, b, c in tcw)  # CW kirdi — CW chiqdi
    col = [(0, 0), (1, 0), (2, 0), (2, 1), (0, 1)]  # kollinear uch saqlanadi
    assert len(geom.triangulate(col)) == 3
    with pytest.raises(ValueError):
        geom.triangulate([(0, 0), (1, 0), (2, 0), (3, 0)])  # nol yuzali (degenerat)


def test_partial_revolve_disc_touching_axis():
    """Chiqarish quvuri tirsagi: o'qqa tegadigan disk 90° — o'q nuqtasi payvandlanadi, qopqoqlar bilan yopiq."""
    R = 2.25
    m = geom.revolve(geom.circle(R, geom.segments(R), (R, 0.0)), math.pi / 2)
    assert geom.is_closed(m)
    assert geom.signed_volume(m) == pytest.approx(math.pi**2 * R**3 / 2, rel=4e-3)  # Pappus


def test_sweep_annulus_along_bent_path():
    """Bosimli quvur: halqa kesim to'g'ri — yoy — to'g'ri yo'l bo'ylab; hajm = halqa yuzasi × o'q uzunligi."""
    R, ro, ri, m_arc = 8.0, 1.22, 1.2, 24
    path, tans = [(0.0, 0.0, 0.0)], [(0.0, 0.0, -1.0)]
    for k in range(m_arc + 1):  # (0,0,−10) dan +Y ga 90° yoy, markaz (0, R, −10)
        g = math.pi / 2 * k / m_arc
        path.append((0.0, R - R * math.cos(g), -10.0 - R * math.sin(g)))
        tans.append((0.0, math.sin(g), -math.cos(g)))
    path.append((0.0, R + 6.0, -10.0 - R))
    tans.append((0.0, 1.0, 0.0))
    n = geom.segments(ro)
    m = geom.sweep(geom.circle(ro, n), path, tans, (1.0, 0.0, 0.0), hole=geom.circle(ri, n))
    assert geom.is_closed(m)
    exact = math.pi * (ro**2 - ri**2) * (10.0 + R * math.pi / 2 + 6.0)
    assert geom.signed_volume(m) == pytest.approx(exact, rel=4e-3)
    solid = geom.sweep(geom.circle(ro, n), path, tans, (1.0, 0.0, 0.0))  # teshiksiz — qopqoqlar uchburchaklangan
    assert geom.is_closed(solid) and geom.signed_volume(solid) > geom.signed_volume(m)


def test_loft_rectangles_prismatoid_exact():
    def rect(y, w, h):
        return [(-w / 2, y, -h / 2), (w / 2, y, -h / 2), (w / 2, y, h / 2), (-w / 2, y, h / 2)]

    m = geom.loft(rect(0.0, 4.5, 4.5), rect(12.0, 8.0, 4.0))
    assert geom.is_closed(m)
    a1, a2, am = 4.5 * 4.5, 32.0, (4.5 + 8.0) / 2 * (4.5 + 4.0) / 2
    assert geom.signed_volume(m) == pytest.approx(12.0 / 6 * (a1 + 4 * am + a2), rel=1e-12)


def test_transform_mirror_keeps_outward_and_merge_offsets():
    m = geom.box((1.0, 2.0, 3.0))
    mirror = np.diag([-1.0, 1.0, 1.0, 1.0])
    mm = geom.transform(m, mirror)
    assert geom.is_closed(mm) and geom.signed_volume(mm) == pytest.approx(6.0)
    both = geom.merge(m, geom.translate(m, (5.0, 0.0, 0.0)))
    assert len(both[0]) == 16 and both[1].max() == 15 and geom.signed_volume(both) == pytest.approx(12.0)


def test_is_closed_detects_open_and_degenerate():
    v, f = geom.box((1.0, 1.0, 1.0))
    assert not geom.is_closed((v, f[1:]))
    bad = f.copy()
    bad[0, 1] = bad[0, 0]
    assert not geom.is_closed((v, bad))
```

- [ ] **Step 2: Yiqilishini ko'ring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_geom.py`
Expected: `ImportError: cannot import name 'geom' from 'sath_common'`

- [ ] **Step 3: Modulni yozing** — `common/sath_common/geom.py`

```python
"""Sath sof geometriya yadrosi — FreeCAD Part o'rniga (spec §6). numpy, float64, bpy/FreeCAD siz.

Mesh = (V, F): V — (n, 3) float64 nuqtalar (metr), F — (m, 3) int64 uchburchaklar. Yopiq qobiqlarda normal
tashqariga (tashqaridan qaraganda soat miliga qarshi). Kirish/chiqish faqat numpy massivlari — keyin `sath_core`
(C++23, nanobind) xuddi shu API bilan almashtiriladi, bu modul paritet etaloni bo'lib qoladi.

Tessellatsiya chord tolerance bo'yicha: aylana bo'lagining sagittasi ≤ tol (default 5 mm). Segmentlar soni 4 ga
karrali (o'qlar bo'ylab ekstremum nuqtalar aniq → bbox aniq) va kamida MIN_SEG (ichki chizilgan ko'pburchakning
hajm xatosi ≈ θ²/6 ≤ 0.16 %, θ = 2π/MIN_SEG). Boolean (cut/fuse) yo'q: GES turlari to'g'ridan-to'g'ri quriladi
(`ges_kinds`), tegib turgan qismlar alohida yopiq qobiq bo'lib qoladi.
"""

from __future__ import annotations

import math

import numpy as np

TOL = 0.005
MIN_SEG = 64
MAX_SEG = 512
Mesh = tuple[np.ndarray, np.ndarray]


def segments(radius: float, tol: float = TOL) -> int:
    """To'liq aylana uchun segmentlar soni: sagitta r·(1 − cos(π/n)) ≤ tol; 4 ga karrali, [MIN_SEG, MAX_SEG]."""
    if radius <= 0 or tol >= radius:
        n = MIN_SEG
    else:
        n = math.ceil(math.pi / math.acos(1.0 - tol / radius))
    n = max(MIN_SEG, min(MAX_SEG, n))
    return (n + 3) // 4 * 4


def circle(r: float, n: int, center: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """(n, 2) aylana nuqtalari, burchak 0 dan soat miliga qarshi (n 4 ga karrali — ±r nuqtalar aniq)."""
    t = 2.0 * math.pi * np.arange(n) / n
    return np.column_stack([center[0] + r * np.cos(t), center[1] + r * np.sin(t)])


def _as_mesh(verts, faces) -> Mesh:
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3), np.asarray(faces, dtype=np.int64).reshape(-1, 3)


def merge(*meshes: Mesh) -> Mesh:
    """Bir nechta mesh → bitta (V, F); indekslar siljitiladi, qobiqlar alohida qoladi."""
    vs, fs, off = [], [], 0
    for v, f in meshes:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(vs), np.vstack(fs)


def transform(m: Mesh, matrix) -> Mesh:
    """4×4 affin matritsa; aks ettirishda (det < 0) uchburchak yo'nalishi tiklanadi (normal tashqarida qoladi)."""
    mat = np.asarray(matrix, dtype=np.float64)
    v, f = m
    v2 = v @ mat[:3, :3].T + mat[:3, 3]
    return v2, (f[:, ::-1].copy() if np.linalg.det(mat[:3, :3]) < 0 else f.copy())


def translate(m: Mesh, offset) -> Mesh:
    return m[0] + np.asarray(offset, dtype=np.float64), m[1].copy()


def signed_volume(m: Mesh) -> float:
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def area(m: Mesh) -> float:
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0)


def bbox(m: Mesh) -> np.ndarray:
    """[xmin, ymin, zmin, xmax, ymax, zmax]"""
    return np.concatenate([m[0].min(axis=0), m[0].max(axis=0)])


def is_closed(m: Mesh) -> bool:
    """Yopiq va izchil yo'naltirilgan qobiq(lar): har yo'naltirilgan qirra bir marta, teskarisi ham bor;
    takroriy indeksli (degenerat) uchburchak yo'q."""
    v, f = m
    if len(f) == 0 or (f[:, 0] == f[:, 1]).any() or (f[:, 1] == f[:, 2]).any() or (f[:, 0] == f[:, 2]).any():
        return False
    e = f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    nv = len(v)
    key = e[:, 0] * nv + e[:, 1]
    rev = e[:, 1] * nv + e[:, 0]
    return len(np.unique(key)) == len(key) and bool(np.isin(rev, key).all())


def _area2(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _cross2(o, a, b) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _in_tri(q, a, b, c, eps: float) -> bool:
    """q CCW uchburchak (a, b, c) ichida yoki chegarasida."""
    return _cross2(a, b, q) >= -eps and _cross2(b, c, q) >= -eps and _cross2(c, a, q) >= -eps


def triangulate(poly) -> np.ndarray:
    """Oddiy ko'pburchak (n, 2) → (n − 2, 3) indekslar, quloq kesish (ear clipping). Uchburchaklar ko'pburchak
    bilan BIR XIL aylanish yo'nalishida (CW kirsa — CW). Kollinear uchlar saqlanadi. O'z-o'zini kesish
    tekshirilmaydi (kirish — ges_kinds profillari); quloq topilmasa (degenerat) — ValueError."""
    p = np.asarray(poly, dtype=np.float64)
    n = len(p)
    if n < 3:
        raise ValueError("ko'pburchakda kamida 3 uch kerak")
    ccw = _area2(p) > 0
    idx = list(range(n)) if ccw else list(range(n - 1, -1, -1))
    scale = float(np.abs(p).max()) or 1.0
    eps = 1e-12 * scale * scale
    tris: list[tuple[int, int, int]] = []
    while len(idx) > 3:
        m = len(idx)
        for i in range(m):
            a, b, c = idx[i - 1], idx[i], idx[(i + 1) % m]
            if _cross2(p[a], p[b], p[c]) <= eps:
                continue  # botiq yoki kollinear uch — quloq emas
            if any(_in_tri(p[k], p[a], p[b], p[c], eps) for k in idx if k not in (a, b, c)):
                continue
            tris.append((a, b, c))
            del idx[i]
            break
        else:
            raise ValueError("ko'pburchak degenerat yoki oddiy emas (quloq topilmadi)")
    tris.append((idx[0], idx[1], idx[2]))
    t = np.array(tris, dtype=np.int64)
    return t if ccw else t[:, ::-1].copy()


def _normal(p3: np.ndarray) -> np.ndarray:
    """Tekis 3D ko'pburchak normali (Newell usuli), uzunligi = 2 · yuza."""
    return np.cross(p3, np.roll(p3, -1, axis=0)).sum(axis=0)


def _cap(p3: np.ndarray) -> np.ndarray:
    """Tekis 3D ko'pburchak uchburchaklari, normali ko'pburchak normali (Newell) bilan bir tomonda."""
    nrm = _normal(p3)
    ax = int(np.argmax(np.abs(nrm)))
    t = triangulate(p3[:, [i for i in range(3) if i != ax]])
    tn = np.cross(p3[t[:, 1]] - p3[t[:, 0]], p3[t[:, 2]] - p3[t[:, 0]]).sum(axis=0)
    return t[:, ::-1].copy() if np.dot(tn, nrm) < 0 else t


def extrude(poly, vec) -> Mesh:
    """Tekis 3D ko'pburchakni (n, 3; botiq bo'lishi mumkin) `vec` bo'ylab cho'zish — prizma."""
    p = np.asarray(poly, dtype=np.float64).reshape(-1, 3)
    d = np.asarray(vec, dtype=np.float64)
    if np.dot(_normal(p), d) < 0:
        p = p[::-1].copy()
    n = len(p)
    t = _cap(p)
    i = np.arange(n)
    j = (i + 1) % n
    sides = np.concatenate([np.column_stack([i, j, j + n]), np.column_stack([i, j + n, i + n])])
    return _as_mesh(np.vstack([p, p + d]), np.concatenate([t[:, ::-1], t + n, sides]))


def box(size, origin=(0.0, 0.0, 0.0)) -> Mesh:
    """O'qlarga parallel quti: origin — minimal burchak, size — (dx, dy, dz)."""
    sx, sy, sz = (float(s) for s in size)
    x, y, z = (float(o) for o in origin)
    return extrude([(x, y, z), (x + sx, y, z), (x + sx, y + sy, z), (x, y + sy, z)], (0.0, 0.0, sz))


def revolve(profile, angle: float = 2 * math.pi, *, tol: float = TOL, matrix=None) -> Mesh:
    """(ρ, z) yarim tekislikdagi yopiq profilni (n, 2; ρ ≥ 0) lokal Z o'qi atrofida `angle` (0 < angle ≤ 2π) ga,
    +X dan +Y tomonga aylantirish. ρ ≈ 0 uchlar o'qda — bitta umumiy nuqta (payvandlanadi). angle < 2π — ikki
    uchida profil qopqog'i. `matrix` (4×4) natijani joylashtiradi (boshqa o'q atrofida aylantirish uchun)."""
    p = np.asarray(profile, dtype=np.float64)
    if _area2(p) < 0:
        p = p[::-1].copy()
    if (p[:, 0] < -1e-12).any():
        raise ValueError("revolve: profil ρ ≥ 0 bo'lishi kerak")
    n = len(p)
    rmax = float(p[:, 0].max())
    full = angle >= 2 * math.pi - 1e-12
    nseg = segments(rmax, tol)
    steps = nseg if full else max(1, math.ceil(nseg * angle / (2 * math.pi)))
    rings = steps if full else steps + 1
    on_axis = p[:, 0] <= 1e-9 * max(1.0, rmax)
    verts: list[tuple[float, float, float]] = []
    index = np.empty((rings, n), dtype=np.int64)
    axis_id: dict[int, int] = {}
    for k in range(rings):
        phi = angle * k / steps
        c, s = math.cos(phi), math.sin(phi)
        for i in range(n):
            if on_axis[i]:
                if i not in axis_id:
                    axis_id[i] = len(verts)
                    verts.append((0.0, 0.0, float(p[i, 1])))
                index[k, i] = axis_id[i]
            else:
                index[k, i] = len(verts)
                verts.append((float(p[i, 0]) * c, float(p[i, 0]) * s, float(p[i, 1])))
    faces: list = []
    for k in range(steps):
        k2 = (k + 1) % rings
        for i in range(n):
            j = (i + 1) % n
            if on_axis[i] and on_axis[j]:
                continue  # o'q bo'ylab qirra — sirt hosil qilmaydi
            q0, q1, q2, q3 = index[k, i], index[k2, i], index[k2, j], index[k, j]
            for tri in ((q0, q1, q2), (q0, q2, q3)):
                if len({int(x) for x in tri}) == 3:
                    faces.append(tri)
    if not full:
        t = triangulate(p)  # profil CCW → φ = 0 qopqog'i normali −Y (tashqariga)
        faces.extend(index[0][t].tolist())
        faces.extend(index[steps][t[:, ::-1]].tolist())
    m = _as_mesh(verts, faces)
    return transform(m, matrix) if matrix is not None else m


def cylinder(r: float, h: float, *, base=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli silindr, asosi markazi `base`."""
    return translate(revolve([(0.0, 0.0), (r, 0.0), (r, h), (0.0, h)], tol=tol), base)


def cone(r1: float, r2: float, h: float, *, base=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli kesik konus: pastda r1, yuqorida r2 (0 — uchli)."""
    prof = [(0.0, 0.0), (r1, 0.0)] + ([(r2, h)] if r2 > 0 else []) + [(0.0, h)]
    return translate(revolve(prof, tol=tol), base)


def torus(big_r: float, r: float, *, center=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli tor: markaziy aylana radiusi big_r, kesim radiusi r."""
    return translate(revolve(circle(r, segments(r, tol), (big_r, 0.0)), tol=tol), center)


def sweep(profile, path, tangents, normal, *, hole=None) -> Mesh:
    """Yopiq profilni (n, 2) yassi yo'l bo'ylab cho'zish. Kesim k: markazi path[k], tekisligi tangents[k] ga
    perpendikulyar; profil u o'qi — `normal` (yo'l tekisligiga perpendikulyar, doimiy), v o'qi — tangent × normal.
    hole (n, 2; profil bilan bir xil yo'nalish va uchlar soni) — ichki kontur: quvur, halqa qopqoqlar."""
    prof = np.asarray(profile, dtype=np.float64)
    inner = None if hole is None else np.asarray(hole, dtype=np.float64)
    if _area2(prof) < 0:
        prof = prof[::-1].copy()
        inner = None if inner is None else inner[::-1].copy()
    pts = np.asarray(path, dtype=np.float64)
    tan = np.asarray(tangents, dtype=np.float64)
    tan = tan / np.linalg.norm(tan, axis=1)[:, None]
    u = np.asarray(normal, dtype=np.float64)
    u = u / np.linalg.norm(u)
    bv = np.cross(tan, u)
    bv = bv / np.linalg.norm(bv, axis=1)[:, None]
    k, n = len(pts), len(prof)

    def rings(pr: np.ndarray) -> np.ndarray:
        return (pts[:, None, :] + pr[None, :, 0, None] * u + pr[None, :, 1, None] * bv[:, None, :]).reshape(-1, 3)

    verts = [rings(prof)] + ([] if inner is None else [rings(inner)])
    s = np.arange(k - 1)[:, None]
    i = np.arange(n)[None, :]
    j = (i + 1) % n
    a0, a1 = (s * n + i).ravel(), (s * n + j).ravel()
    b0, b1 = ((s + 1) * n + i).ravel(), ((s + 1) * n + j).ravel()
    faces = [np.column_stack([a0, a1, b1]), np.column_stack([a0, b1, b0])]
    last = (k - 1) * n
    ii = np.arange(n)
    jj = (ii + 1) % n
    if inner is None:
        t = triangulate(prof)
        faces += [t[:, ::-1], t + last]
    else:
        h = k * n  # ichki kontur indeks siljishi
        faces += [np.column_stack([a0 + h, b1 + h, a1 + h]), np.column_stack([a0 + h, b0 + h, b1 + h])]
        faces += [np.column_stack([ii, ii + h, jj + h]), np.column_stack([ii, jj + h, jj])]  # boshi (−t)
        o = ii + last
        faces += [np.column_stack([o, jj + last, jj + last + h]), np.column_stack([o, jj + last + h, o + h])]  # oxiri
    return _as_mesh(np.vstack(verts), np.concatenate(faces))


def loft(ring_a, ring_b) -> Mesh:
    """Ikki tekis yopiq kontur (n, 3; mos uchlar) orasida to'g'ri chiziqli (ruled) yuza + qopqoqlar."""
    a = np.asarray(ring_a, dtype=np.float64)
    b = np.asarray(ring_b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("loft: konturlarda uchlar soni bir xil bo'lishi kerak")
    d = b.mean(axis=0) - a.mean(axis=0)
    if np.dot(_normal(a), d) < 0:
        a, b = a[::-1].copy(), b[::-1].copy()
    if np.dot(_normal(b), d) <= 0:
        raise ValueError("loft: konturlar yo'nalishi mos emas")
    n = len(a)
    i = np.arange(n)
    j = (i + 1) % n
    sides = np.concatenate([np.column_stack([i, j, j + n]), np.column_stack([i, j + n, i + n])])
    return _as_mesh(np.vstack([a, b]), np.concatenate([_cap(a)[:, ::-1], _cap(b) + n, sides]))
```

- [ ] **Step 4: Testlar o'tadi**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_geom.py`
Expected: `14 passed`

- [ ] **Step 5: Addonga nusxa** — `desktop/build/sync_blender.py`

`FILES = [...]` qatorini (23) almashtiring:

```python
CORE_FILES = ["server_client.py", "dxf_prepare.py", "assimp_load.py", "ifc_classes.py", "cad_common.py"]
FILES = CORE_FILES + ["geom.py"]  # geom (P2) — sof numpy geometriya; faqat addon nusxasi (legacy workbench ga emas)
```

va `EXTRA` dagi `WB_SRC: FILES,` ni `WB_SRC: CORE_FILES,` ga almashtiring. So'ng:

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py
.venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_pure.py -k "synced or byte_identical"
.venv\Scripts\python.exe -m ruff check common desktop/tests/test_geom.py desktop/build/sync_blender.py
```
Expected: `nusxalandi: … desktop/blender/sath/shared/geom.py …`; `common/sath_common nusxalari sinxron`; `2 passed`; `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add common/sath_common/geom.py desktop/tests/test_geom.py desktop/build/sync_blender.py desktop/blender/sath/shared/geom.py
git commit -m "feat(P2): geom — sof numpy geometriya yadrosi (box/silindr/konus/tor, extrude, revolve, sweep, loft; chord tolerance, boolean siz)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ges_kinds.py` — API, K2 xaritalash va 4 tur (To'g'on, Suv tashlagich, Mashina zali, Daryo oqimi kanali)

**Model:** sonnet — ko'p qismli modul + paritet testlari; kod to'liq berilgan.

Prizma/qutidan iborat turlar: geometriya `extrude`/`box` bilan aniq (hajm xatosi 0). «Kesim» mashina zali FreeCAD dagi `body ∪ roof − inner − cut` o'rniga to'g'ridan-to'g'ri: pol + −X gable devori + ikki yon devor (tom qiyaligi bilan kesilgan), +X yarmi ochiq.

**Files:**
- Create: `common/sath_common/ges_kinds.py`
- Create: `desktop/tests/test_ges_kinds.py`
- Modify: `desktop/build/sync_blender.py` (FILES ga `ges_kinds.py`)
- Generated: `desktop/blender/sath/shared/ges_kinds.py`

**Interfaces:**
- Consumes: `geom.*` (Task 2), `ges_golden.json` (Task 1).
- Produces: `ges_kinds.ORDER` (11 kind, KIND_ITEMS tartibi), `KINDS: dict[str, KindSpec]`, `KIND_BY_PSET`, `SCHEMA_VERSION = 1`, `PARAMETRIC_PSET = "Pset_SathParametric"`, `EPS`, `UnknownKind(ValueError)`; `Param(name, label, ptype, default, items)`, `Field(name, ifc_type, param, derive)`, `KindSpec(kind, label, ifc_class, pset, role, color, params, fields, parts, volume, density, check)` + `.defaults()`; `spec(kind)`, `normalize(kind, params) -> dict`, `validate(kind, params) -> dict`, `build_parts(kind, params, tol) -> list[Mesh]`, `build(kind, params, tol) -> Mesh`, `quantities(kind, params) -> {"volume_m3", "mass_t"}`, `psets(kind, params) -> {pset: {...}}`, `parametric_pset(kind, role, params) -> {"Pset_SathParametric": {Kind, Role, SchemaVersion, Params(JSON), Units}}`, `Restored(kind, role, params, source, warnings)`, `from_psets(psets) -> Restored | None`, `infer_roles([(key, kind, x)]) -> {key: role}`. Task 4–5 yangi bo'limlarni `# --- reyestr va API` qatoridan YUQORIGA qo'shadi.

- [ ] **Step 1: Testni yozing** — `desktop/tests/test_ges_kinds.py`

```python
"""ges_kinds: FreeCAD etaloniga (desktop/tests/data/ges_golden.json) paritet — sxema, IFC klass, rang, Pset_GES_*,
analitik hajm (±0.1 %), mesh hajmi (±0.5 %), bbox, yuza (FreeCAD fuse qilmagan turlar, ±1 %), yopiq qobiqlar;
K2 teskari xaritalash; web qoralama turlari bilan ma'lum farqlar."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import geom, ges_kinds, ifc_classes  # noqa: E402

GOLDEN = json.loads((ROOT / "desktop" / "tests" / "data" / "ges_golden.json").read_text(encoding="utf-8"))
CASES = [(k, c) for k, g in GOLDEN["kinds"].items() for c in g["cases"]]
IDS = [f"{k}-{c['id']}" for k, c in CASES]
# FreeCAD fuse tegib turgan yuzalarni olib tashlaydi, bizda qismlar alohida qobiq → yuza faqat shu turlarda
AREA_EXACT = {"GES_Dam", "GES_Penstock", "GES_Turbine", "GES_Spillway", "GES_Powerhouse", "GES_DraftTube", "GES_Tailrace"}


def _ported(kind):
    if kind not in ges_kinds.KINDS:
        pytest.skip(f"{kind} hali ko'chirilmagan")


def _same(a, b):
    return a == pytest.approx(b, rel=1e-9, abs=1e-12) if isinstance(b, float) else a == b


@pytest.mark.parametrize("kind", list(GOLDEN["kinds"]))
def test_schema_and_meta_match_golden(kind):
    _ported(kind)
    g, s = GOLDEN["kinds"][kind], ges_kinds.spec(kind)
    assert (s.label, s.ifc_class) == (g["label"], g["ifc_class"])
    assert s.color == pytest.approx(tuple(g["color"]))
    assert s.ifc_class in ifc_classes.IFC4
    ours = {p.name: p for p in s.params}
    assert set(ours) == {f["name"] for f in g["schema"]}
    for f in g["schema"]:
        p = ours[f["name"]]
        assert (p.label, p.ptype, list(p.items)) == (f["label"], f["type"], f["items"]), f["name"]
        assert _same(p.default, f["default"]), (f["name"], p.default, f["default"])


@pytest.mark.parametrize("kind,case", CASES, ids=IDS)
def test_geometry_and_psets_match_golden(kind, case):
    _ported(kind)
    p = case["params"]
    assert ges_kinds.quantities(kind, p)["volume_m3"] == pytest.approx(case["volume_m3"], rel=1e-3), "analitik hajm"
    parts = ges_kinds.build_parts(kind, p)
    for i, m in enumerate(parts):
        assert geom.is_closed(m), f"qism {i} yopiq emas"
        assert geom.signed_volume(m) > 0, f"qism {i}: normallar ichkariga"
    mesh = geom.merge(*parts)
    assert geom.signed_volume(mesh) == pytest.approx(case["volume_m3"], rel=5e-3), "mesh hajmi"
    gb = np.array(case["bbox_m"])
    tol = max(0.01, 0.002 * float(np.linalg.norm(gb[3:] - gb[:3])))
    assert np.abs(geom.bbox(mesh) - gb).max() <= tol, (geom.bbox(mesh).round(4).tolist(), gb.tolist())
    if kind in AREA_EXACT and p.get("View") != "Kesim":
        assert geom.area(mesh) == pytest.approx(case["area_m2"], rel=1e-2), "yuza"
    got = ges_kinds.psets(kind, p)
    assert set(got) == set(case["psets"])
    for name, vals in case["psets"].items():
        assert set(got[name]) == set(vals), name
        for k, v in vals.items():
            assert _same(got[name][k], v), (name, k, got[name][k], v)


@pytest.mark.parametrize("kind", ges_kinds.ORDER)
def test_parametric_pset_roundtrip(kind):
    _ported(kind)
    params = GOLDEN["kinds"][kind]["cases"][-1]["params"]
    ps = {**ges_kinds.psets(kind, params), **ges_kinds.parametric_pset(kind, "unit:3", params)}
    r = ges_kinds.from_psets(ps)
    assert (r.kind, r.role, r.source, r.warnings) == (kind, "unit:3", "parametric", [])
    assert r.params == ges_kinds.normalize(kind, params)


@pytest.mark.parametrize("kind", ges_kinds.ORDER)
def test_pset_only_inverse_mapping(kind):
    """Eski (Pset_SathParametric siz) model: FreeCAD yozgan Pset_GES_* dan tur va parametrlar tiklanadi."""
    _ported(kind)
    case = GOLDEN["kinds"][kind]["cases"][-1]
    r = ges_kinds.from_psets(case["psets"])
    assert (r.kind, r.role, r.source, r.warnings) == (kind, "", "pset", [])
    full = ges_kinds.normalize(kind, case["params"])
    for f in ges_kinds.spec(kind).fields:
        if f.param:
            assert _same(r.params[f.param], full[f.param]), f.param


def test_from_psets_unknown_web_and_non_ges():
    _ported("GES_Dam")
    assert ges_kinds.from_psets({"Pset_WallCommon": {"IsExternal": True}}) is None
    for bad in (
        {"Pset_GES_Nasos": {"Q": 1.0}},
        {"Pset_SathParametric": {"Kind": "GES_Dam", "SchemaVersion": 99, "Params": "{}"}},
        {"Pset_SathParametric": {"Kind": "GES_Dam", "SchemaVersion": 1, "Params": "{buzuq"}},
        {"Pset_SathParametric": {"Kind": "GES_Yoq", "SchemaVersion": 1, "Params": "{}"}},
    ):
        with pytest.raises(ges_kinds.UnknownKind):
            ges_kinds.from_psets(bad)
    r = ges_kinds.from_psets({"Pset_GES_Dam": {"Turi": "beton og'irlik", "Balandlik_m": 25.0}})  # web qoralama
    assert r.params["Height"] == 25.0 and r.params["DamType"] == "Gravitatsion" and r.warnings


def test_normalize_and_validate_errors():
    _ported("GES_Dam")
    with pytest.raises(ValueError, match="noma'lum parametr"):
        ges_kinds.normalize("GES_Dam", {"Heigth": 3.0})
    with pytest.raises(ValueError, match="ruxsat etilmagan"):
        ges_kinds.normalize("GES_Dam", {"DamType": "Yog'och"})
    with pytest.raises(ValueError, match="0 dan katta"):
        ges_kinds.build("GES_Dam", {"Height": 0.0})
    with pytest.raises(ValueError, match="noma'lum GES turi"):
        ges_kinds.spec("GES_Yoq")
    assert ges_kinds.quantities("GES_Dam")["mass_t"] == pytest.approx(13200.0 * 2.4)


def test_infer_roles_by_x_and_singletons():
    for k in ("GES_Turbine", "GES_Dam", "GES_Spillway"):
        _ported(k)
    roles = ges_kinds.infer_roles(
        [("a", "GES_Turbine", 14.0), ("b", "GES_Turbine", -14.0), ("c", "GES_Dam", 0.0),
         ("d", "GES_Spillway", 1.0), ("e", "GES_Spillway", 2.0)]
    )  # fmt: skip
    assert roles == {"b": "unit:1", "a": "unit:2", "c": "dam"}


def test_penstock_path_matches_blender_physics():
    _ported("GES_Penstock")
    sys.path.insert(0, str(ROOT / "desktop" / "blender"))
    from sath import physics

    a = ges_kinds.penstock_path(60.0, 40.0, 8.0, 6.0)
    b = physics.penstock_path(60.0, 40.0, 8.0, 6.0)
    for k in ("p0", "p1", "pm", "p2", "p3", "u1"):
        assert a[k] == pytest.approx(b[k], abs=1e-12), k
    assert a["alpha"] == pytest.approx(b["alpha"]) and a["l1"] == pytest.approx(b["l1"])
```

- [ ] **Step 2: Yiqilishini ko'ring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_ges_kinds.py`
Expected: `ImportError: cannot import name 'ges_kinds'`

- [ ] **Step 3: Modulni yozing** — `common/sath_common/ges_kinds.py`

```python
"""GES inshoot turlari (11 kind) — yagona manba: parametrlar (metr), defaultlar, Pset_GES_* xaritasi, IFC klass,
rang, geometriya (`geom`, boolean siz) va analitik miqdorlar. bpy/FreeCAD siz: Blender addoni, server va pytest bir
xil element beradi (spec §6). Avvalgi manba — FreeCAD `wb/ges_objects.py` (P2 da olib tashlandi); paritet etaloni
`desktop/tests/data/ges_golden.json` (FreeCAD Volume/Area/BoundBox va Pset_GES_*).

Koordinatalar (metr, Z yuqoriga) FreeCAD builderlari bilan bir xil — eski modellardagi joylashuv o'zgarmaydi.
Muhandislik miqdorlari (hajm, massa) mesh dan emas, parametrlardan analitik formulalar bilan hisoblanadi.
Parametrlar mantiqiy (manba) tartibda — FreeCAD `PropertiesList` (alfavit) tartibi emas; moslik nom bo'yicha.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from . import geom

SCHEMA_VERSION = 1
PARAMETRIC_PSET = "Pset_SathParametric"
EPS = 0.001  # FreeCAD builderlaridagi «1 mm» chiqish (teshik/oyna kesuvchi qutilar) — hajm pariteti uchun saqlanadi
CONCRETE = ("B10", "B15", "B20", "B25", "B30", "B35", "B40", "B45", "B50", "B60")
DENSITY_CONCRETE = 2.4  # t/m³
DENSITY_PIPE = {"Po'lat": 7.85, "Temir-beton": 2.5, "GRP": 1.9}  # t/m³
ORDER = (
    "GES_Dam", "GES_Penstock", "GES_Turbine", "GES_Spillway", "GES_Powerhouse", "GES_Transformer",
    "GES_Intake", "GES_Generator", "GES_DraftTube", "GES_ControlRoom", "GES_Tailrace",
)  # fmt: skip


class UnknownKind(ValueError):
    """IFC dagi GES ma'lumotini tanib bo'lmadi (noma'lum tur, yangiroq sxema, buzilgan JSON)."""


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    ptype: str  # length (m) | float | int | enum
    default: float | int | str
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class Field:
    name: str  # Pset xususiyati, masalan "Balandlik_m"
    ifc_type: str  # IfcReal | IfcInteger | IfcLabel
    param: str | None = None  # manba parametr (to'g'ridan-to'g'ri)
    derive: Callable[[dict], object] | None = None  # hosila qiymat (param=None)


def _none(p: dict) -> None:
    return None


@dataclass(frozen=True)
class KindSpec:
    kind: str
    label: str
    ifc_class: str
    pset: str
    role: str  # "dam" (yagona) yoki "unit:" (indeksli: unit:1, unit:2, …)
    color: tuple[float, float, float]
    params: tuple[Param, ...]
    fields: tuple[Field, ...]
    parts: Callable[[dict, float], list]  # (parametrlar, tol) → [geom.Mesh] — har biri yopiq qobiq
    volume: Callable[[dict], float]  # analitik hajm, m³
    density: Callable[[dict], float | None] = _none  # t/m³ (None — massa hisoblanmaydi)
    check: Callable[[dict], None] = _none  # turga xos cheklovlar (ValueError)

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}


def _len(name: str, label: str, default: float) -> Param:
    return Param(name, label, "length", float(default))


def _flt(name: str, label: str, default: float) -> Param:
    return Param(name, label, "float", float(default))


def _int(name: str, label: str, default: int) -> Param:
    return Param(name, label, "int", int(default))


def _enum(name: str, label: str, items: tuple[str, ...], default: str | None = None) -> Param:
    return Param(name, label, "enum", default or items[0], tuple(items))


def _real(name: str, param: str) -> Field:
    return Field(name, "IfcReal", param)


def _count(name: str, param: str) -> Field:
    return Field(name, "IfcInteger", param)


def _label(name: str, param: str) -> Field:
    return Field(name, "IfcLabel", param)


def _concrete(p: dict) -> float:
    return DENSITY_CONCRETE


_SPECS: dict[str, KindSpec] = {}


def _register(spec: KindSpec) -> None:
    _SPECS[spec.kind] = spec


# --- To'g'on: trapetsiya kesim (oqim Y), uzunlik X bo'ylab ---------------------------------------------------------


def _dam_parts(p: dict, tol: float) -> list:
    L, H, cw, bw = p["Length"], p["Height"], p["CrestWidth"], p["BaseWidth"]
    prof = [(0.0, 0.0, 0.0), (0.0, bw, 0.0), (0.0, (bw + cw) / 2, H), (0.0, (bw - cw) / 2, H)]
    return [geom.extrude(prof, (L, 0.0, 0.0))]


_register(KindSpec(
    kind="GES_Dam", label="To'g'on", ifc_class="IfcWall", pset="Pset_GES_Dam", role="dam", color=(0.72, 0.70, 0.66),
    params=(
        _len("Length", "Gerbi uzunligi", 60), _len("Height", "Balandligi", 20),
        _len("CrestWidth", "Gerbi kengligi", 6), _len("BaseWidth", "Asos kengligi", 16),
        _enum("DamType", "Turi", ("Gravitatsion", "Arkali", "Tuproq", "Tosh-tuproq")),
        _flt("CrestElevation", "Gerbi belgisi, m (abs)", 0), _flt("BaseElevation", "Tag belgisi, m (abs)", 0),
        _enum("ConcreteClass", "Beton klassi (KMK 2.03.01)", ("B15", "B20", "B25", "B30", "B35", "B40"), "B20"),
    ),
    fields=(
        _label("Turi", "DamType"), _real("Balandlik_m", "Height"), _real("Uzunlik_m", "Length"),
        _real("GerbBelgisi_m", "CrestElevation"), _real("GerbKengligi_m", "CrestWidth"),
        _real("TagKengligi_m", "BaseWidth"), _real("TagBelgisi_m", "BaseElevation"), _label("BetonKlassi", "ConcreteClass"),
    ),
    parts=_dam_parts,
    volume=lambda p: p["Length"] * p["Height"] * (p["BaseWidth"] + p["CrestWidth"]) / 2,
    density=_concrete,
))  # fmt: skip


# --- Suv tashlagich: plita (quti) -------------------------------------------------------------------------------------


_register(KindSpec(
    kind="GES_Spillway", label="Suv tashlagich", ifc_class="IfcSlab", pset="Pset_GES_Spillway", role="spillway",
    color=(0.80, 0.80, 0.78),
    params=(
        _len("Width", "Kengligi (oqimga ko'ndalang)", 12), _len("Length", "Uzunligi (oqim bo'ylab)", 10),
        _len("Thickness", "Qalinligi", 1), _flt("CrestElevation", "Ostona belgisi, m", 0),
        _flt("DischargeCoefficient", "Sarf koeffitsienti m (Q = m·b·√(2g)·H^1.5)", 0.49),
        _int("Gates", "Darvozalar soni", 2),
    ),
    fields=(
        _real("Kenglik_m", "Width"), _real("OstonaBelgisi_m", "CrestElevation"),
        _real("SarfKoeff", "DischargeCoefficient"), _count("Darvozalar", "Gates"),
    ),
    parts=lambda p, tol: [geom.box((p["Width"], p["Length"], p["Thickness"]))],
    volume=lambda p: p["Width"] * p["Length"] * p["Thickness"],
    density=_concrete,
))  # fmt: skip


# --- Mashina zali: «Yopiq» — beshburchak kesim (quti + gable tom) X bo'ylab; «Kesim» — pol, −X gable devori, ---------
# --- ikki yon devor (x ≤ 0), +X yarmi va tomning ichki qismi ochiq (FreeCAD: body ∪ roof − inner − cut) ------------

PH_WALL = 0.6  # kesim devori qalinligi, m


def _powerhouse_parts(p: dict, tol: float) -> list:
    L, W, H = p["Length"], p["Width"], p["Height"]
    t, x0, w = 0.18 * H, -L / 2, PH_WALL
    if p["View"] != "Kesim":
        prof = [(x0, -W / 2, 0.0), (x0, W / 2, 0.0), (x0, W / 2, H), (x0, 0.0, H + t), (x0, -W / 2, H)]
        return [geom.extrude(prof, (L, 0.0, 0.0))]
    k = 2 * t * w / W  # tom balandligi devor ichki chetida (H ustidan)
    floor = geom.box((L, W, w), (x0, -W / 2, 0.0))
    end = geom.extrude([(x0, -W / 2, w), (x0, W / 2, w), (x0, W / 2, H), (x0, 0.0, H + t), (x0, -W / 2, H)], (w, 0.0, 0.0))
    xs, run = x0 + w, L / 2 - w
    right = geom.extrude([(xs, W / 2 - w, w), (xs, W / 2, w), (xs, W / 2, H), (xs, W / 2 - w, H + k)], (run, 0.0, 0.0))
    left = geom.extrude([(xs, -W / 2, w), (xs, -W / 2 + w, w), (xs, -W / 2 + w, H + k), (xs, -W / 2, H)], (run, 0.0, 0.0))
    return [floor, end, left, right]


def _powerhouse_volume(p: dict) -> float:
    L, W, H = p["Length"], p["Width"], p["Height"]
    t, w = 0.18 * H, PH_WALL
    if p["View"] != "Kesim":
        return L * (W * H + W * t / 2)
    return L * W * w + w * (W * (H - w) + W * t / 2) + 2 * (L / 2 - w) * (w * (H - w) + t * w * w / W)


def _powerhouse_check(p: dict) -> None:
    if p["View"] == "Kesim" and (p["Length"] <= 2 * PH_WALL or p["Width"] <= 2 * PH_WALL or p["Height"] <= PH_WALL):
        raise ValueError(f"Mashina zali (kesim): uzunlik/kenglik > {2 * PH_WALL} m, balandlik > {PH_WALL} m bo'lsin")


_register(KindSpec(
    kind="GES_Powerhouse", label="Mashina zali", ifc_class="IfcBuildingElementProxy", pset="Pset_GES_Powerhouse",
    role="powerhouse", color=(0.69, 0.63, 0.53),
    params=(
        _len("Length", "Uzunligi (X)", 40), _len("Width", "Kengligi (Y)", 20), _len("Height", "Balandligi", 18),
        _int("Units", "Agregatlar soni", 2), _flt("FloorElevation", "Pol belgisi, m (abs)", 0),
        _enum("ConcreteClass", "Beton klassi (karkas)", CONCRETE, "B25"), _enum("View", "Ko'rinish", ("Yopiq", "Kesim")),
    ),
    fields=(
        _count("Agregatlar", "Units"), _real("PolBelgisi_m", "FloorElevation"), _real("Uzunlik_m", "Length"),
        _real("Kenglik_m", "Width"), _real("Balandlik_m", "Height"), _label("BetonKlassi", "ConcreteClass"),
    ),
    parts=_powerhouse_parts, volume=_powerhouse_volume, density=_concrete, check=_powerhouse_check,
))  # fmt: skip


# --- Daryo oqimi kanali: U-kesim (tag + ikki devor) +Y bo'ylab -----------------------------------------------------


def _tailrace_parts(p: dict, tol: float) -> list:
    W, L, D, t = p["Width"], p["Length"], p["Depth"], p["WallThickness"]
    a, b = W / 2, W / 2 + t
    prof = [(-b, 0.0, -t), (b, 0.0, -t), (b, 0.0, D), (a, 0.0, D), (a, 0.0, 0.0), (-a, 0.0, 0.0), (-a, 0.0, D), (-b, 0.0, D)]
    return [geom.extrude(prof, (0.0, L, 0.0))]


_register(KindSpec(
    kind="GES_Tailrace", label="Daryo oqimi kanali", ifc_class="IfcCivilElement", pset="Pset_GES_Tailrace",
    role="tailrace", color=(0.62, 0.62, 0.60),
    params=(
        _len("Width", "Kanal kengligi (X)", 20), _len("Length", "Uzunligi (Y)", 40), _len("Depth", "Devor balandligi", 6),
        _len("WallThickness", "Devor/tag qalinligi", 0.8), _flt("BedSlope", "Tag nishabi S", 0.001),
        _flt("Manning", "Manning g'adir-budirligi n", 0.03), _flt("BedElevation", "Tag belgisi, m (abs)", 0),
        _flt("DesignTailwater", "Hisobiy quyi byef sathi, m (abs)", 0),
        _flt("DesignFlow", "Hisobiy sarf (barcha agregatlar), m3/s", 100),
    ),
    fields=(
        _real("Kenglik_m", "Width"), _real("Uzunlik_m", "Length"), _real("Chuqurlik_m", "Depth"),
        _real("Nishab", "BedSlope"), _real("Manning_n", "Manning"), _real("TagBelgisi_m", "BedElevation"),
        _real("HisobiyQuyiByef_m", "DesignTailwater"), _real("HisobiySarf_m3s", "DesignFlow"),
    ),
    parts=_tailrace_parts,
    volume=lambda p: p["Length"] * ((p["Width"] + 2 * p["WallThickness"]) * (p["Depth"] + p["WallThickness"]) - p["Width"] * p["Depth"]),
    density=_concrete,
))  # fmt: skip


# --- reyestr va API ---------------------------------------------------------------------------------------------------

KINDS: dict[str, KindSpec] = {k: _SPECS[k] for k in ORDER if k in _SPECS}
KIND_BY_PSET: dict[str, str] = {s.pset: k for k, s in KINDS.items()}


def spec(kind: str) -> KindSpec:
    try:
        return KINDS[kind]
    except KeyError:
        raise ValueError(f"noma'lum GES turi: {kind!r}") from None


def _cast_param(p: Param, v):
    if p.ptype == "enum":
        v = str(v)
        if v not in p.items:
            raise ValueError(f"{p.name}: {v!r} ruxsat etilmagan ({', '.join(p.items)})")
        return v
    if p.ptype == "int":
        return int(v)
    return float(v)


def normalize(kind: str, params: dict | None = None) -> dict:
    """Defaultlar + berilganlar, turlari keltirilgan. Noma'lum nom yoki ruxsat etilmagan enum — ValueError."""
    s = spec(kind)
    out = s.defaults()
    by = {p.name: p for p in s.params}
    for k, v in (params or {}).items():
        if k not in by:
            raise ValueError(f"{kind}: noma'lum parametr {k!r}")
        out[k] = _cast_param(by[k], v)
    return out


def validate(kind: str, params: dict | None = None) -> dict:
    """normalize + geometrik cheklovlar (uzunliklar > 0, turga xos). Xato — ValueError (foydalanuvchiga matn)."""
    s = spec(kind)
    p = normalize(kind, params)
    for prm in s.params:
        if prm.ptype == "length" and not p[prm.name] > 0:
            raise ValueError(f"{s.label}: «{prm.label}» 0 dan katta bo'lsin")
    s.check(p)
    return p


def build_parts(kind: str, params: dict | None = None, tol: float = geom.TOL) -> list:
    """Har biri yopiq qobiq bo'lgan qismlar ([geom.Mesh]); tegib turgan qismlar birlashtirilmaydi (boolean yo'q)."""
    return spec(kind).parts(validate(kind, params), tol)


def build(kind: str, params: dict | None = None, tol: float = geom.TOL) -> geom.Mesh:
    """Bitta mesh (V float64 metr, F int64 uchburchak) — Blender ga `foreach_set` bilan uzatiladi."""
    return geom.merge(*build_parts(kind, params, tol))


def quantities(kind: str, params: dict | None = None) -> dict:
    """Analitik miqdorlar: volume_m3, mass_t (zichlik ma'lum bo'lsa, aks holda None)."""
    s = spec(kind)
    p = validate(kind, params)
    v = s.volume(p)
    rho = s.density(p)
    return {"volume_m3": v, "mass_t": None if rho is None else v * rho}


def _cast_ifc(ifc_type: str, v):
    if ifc_type == "IfcReal":
        return float(v)
    if ifc_type == "IfcInteger":
        return int(v)
    return str(v)


def psets(kind: str, params: dict | None = None) -> dict[str, dict]:
    """{Pset_GES_<X>: {xususiyat: qiymat}} — FreeCAD davridagi nomlar va qiymatlar bilan bir xil (server o'qiydi)."""
    s = spec(kind)
    p = normalize(kind, params)
    vals = {}
    for f in s.fields:
        vals[f.name] = _cast_ifc(f.ifc_type, f.derive(p) if f.derive is not None else p[f.param])
    return {s.pset: vals}


def parametric_pset(kind: str, role: str, params: dict | None = None) -> dict[str, dict]:
    """K2: to'liq round-trip uchun {Pset_SathParametric: Kind, Role, SchemaVersion, Params (JSON, metr), Units}."""
    p = normalize(kind, params)
    return {
        PARAMETRIC_PSET: {
            "Kind": kind, "Role": role or "", "SchemaVersion": SCHEMA_VERSION,
            "Params": json.dumps(p, ensure_ascii=False, sort_keys=True), "Units": "m",
        }
    }  # fmt: skip


@dataclass
class Restored:
    kind: str
    role: str
    params: dict
    source: str  # "parametric" — Pset_SathParametric dan; "pset" — Pset_GES_* dan teskari xaritalangan
    warnings: list[str] = field(default_factory=list)


def _coerce(kind: str, raw: dict) -> tuple[dict, list[str]]:
    s = spec(kind)
    out, warns = s.defaults(), []
    by = {p.name: p for p in s.params}
    for k, v in raw.items():
        if k not in by:
            warns.append(f"noma'lum parametr {k!r} e'tiborsiz qoldirildi")
            continue
        try:
            out[k] = _cast_param(by[k], v)
        except (TypeError, ValueError):
            warns.append(f"{k}={v!r} yaroqsiz — default {by[k].default!r}")
    return out, warns


def from_psets(ps: dict) -> Restored | None:
    """IFC element psetlari ({nom: {xususiyat: qiymat}}) → Restored; GES elementi bo'lmasa None, tanib bo'lmasa
    UnknownKind. Avval Pset_SathParametric (tur, rol, barcha parametrlar), bo'lmasa Pset_GES_<X> nomidan tur va
    maydonlardan parametrlar (pset da yo'q geometriya parametrlari — default, rol — bo'sh; `infer_roles`)."""
    sp = ps.get(PARAMETRIC_PSET)
    if sp:
        kind = str(sp.get("Kind") or "")
        if kind not in KINDS:
            raise UnknownKind(f"{PARAMETRIC_PSET}: noma'lum tur {kind!r}")
        ver = int(sp.get("SchemaVersion") or 0)
        if ver > SCHEMA_VERSION:
            raise UnknownKind(f"{kind}: sxema v{ver} — bu ilova v{SCHEMA_VERSION} gacha biladi (Sath ni yangilang)")
        try:
            raw = json.loads(sp.get("Params") or "{}")
        except ValueError as e:
            raise UnknownKind(f"{kind}: Params JSON buzilgan ({e})") from None
        if not isinstance(raw, dict):
            raise UnknownKind(f"{kind}: Params obyekt emas")
        params, warns = _coerce(kind, raw)
        return Restored(kind, str(sp.get("Role") or ""), params, "parametric", warns)
    for name, values in ps.items():
        kind = KIND_BY_PSET.get(name)
        if kind is None:
            continue
        raw = {f.param: values[f.name] for f in spec(kind).fields if f.param and f.name in values}
        params, warns = _coerce(kind, raw)
        return Restored(kind, "", params, "pset", warns)
    ges = sorted(n for n in ps if n.startswith("Pset_GES_"))
    if ges:
        raise UnknownKind(f"noma'lum GES pset: {', '.join(ges)}")
    return None


def infer_roles(items) -> dict[str, str]:
    """[(kalit, tur, x)] → {kalit: rol}: indeksli turlar (unit:, gen:, draft:, penstock:, transformer:) X bo'yicha
    1..n; yagona turlar (dam, intake, …) faqat bitta bo'lsa. Pset_SathParametric siz (eski/web) modellar uchun."""
    groups: dict[str, list] = {}
    for key, kind, x in items:
        groups.setdefault(kind, []).append((float(x), key))
    out: dict[str, str] = {}
    for kind, its in groups.items():
        role = spec(kind).role
        if role.endswith(":"):
            for i, (_, key) in enumerate(sorted(its), start=1):
                out[key] = f"{role}{i}"
        elif len(its) == 1:
            out[its[0][1]] = role
    return out
```

- [ ] **Step 4: Testlar**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_ges_kinds.py`
Expected: `26 passed, 50 skipped` (to'rt tur ko'chirildi; qolganlari «hali ko'chirilmagan» skip — 2026-10-08 da shu kod bilan sinalgan).

- [ ] **Step 5: Nusxa, ruff**

`desktop/build/sync_blender.py`: `FILES = CORE_FILES + ["geom.py", "ges_kinds.py"]`.

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py; .venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m ruff check common desktop/tests/test_ges_kinds.py desktop/build/sync_blender.py
```
Expected: `common/sath_common nusxalari sinxron`, `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add common/sath_common/ges_kinds.py desktop/tests/test_ges_kinds.py desktop/build/sync_blender.py desktop/blender/sath/shared/ges_kinds.py
git commit -m "feat(P2): ges_kinds — GES turlari yagona manbasi (sxema, Pset_GES_*, analitik hajm, K2 Pset_SathParametric va teskari xaritalash); to'g'on, suv tashlagich, mashina zali, kanal FreeCAD bilan paritetda" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `ges_kinds` — egri sirtli turlar (Bosimli quvur, Turbina, Generator, Chiqarish quvuri)

**Model:** opus — aylanish/sweep/loft yo'nalishi va FreeCAD paritetini debug qilish (eng nozik geometriya).

Dekompozitsiya (FreeCAD `wb/ges_objects.py` → boolean siz):

| Tur | Manba qatorlari | Qurish | Analitik hajm |
|---|---|---|---|
| Bosimli quvur | 159–223 (`build_shape` 189–212, `penstock_path` 81–99) | Inclination ≤ 0: halqa profil `revolve` ([r, r+t] × [0, L]) — `outer.cut(inner)` o'rniga; aks holda halqa `sweep` (tashqi aylana + `hole` ichki aylana) o'q: p0 → p1 (qiya) → yoy (R, `segments(R+ro)` bo'yicha) → p3 (+Y), kesim normali X | π((r+t)² − r²) · (l1 + R·α + chiqish) yoki · L |
| Turbina | 226–270 (`build_shape` 256–261) | tor (0.7d, 0.2d) + val va korpus BITTA aylanish profili (0,0)→(0.12d,0)→(0.12d,0.6h)→(0.5d,0.6h)→(0.5d,h)→(0,h) — `fuse` o'rniga (tor ichki radiusi 0.5d > 0.12d, korpus z ≥ 0.6h > 0 → kesishmaydi) | 2π²·0.7d·(0.2d)² + π(0.12d)²·0.6h + π(0.5d)²·0.4h |
| Generator | 467–516 (`build_shape` 492–504) | stator + 12 qovurg'a = bitta yulduzsimon profil (stator yoylari + qovurg'a to'rtburchaklari, x_c = √(r² − w²)) z bo'ylab 0.7h cho'zilgan; qopqoq-konus + qo'zg'atgich bitta aylanish profili; val — silindr (tegib turadi) | 0.7h·(πr² + 12·(0.08d·0.05d − (∫√(r²−y²)dy − 2w·0.48d))) + konus + qo'zg'atgich + val |
| Chiqarish quvuri | 519–581 (`build_shape` 542–571) | kesik konus; tirsak — o'qqa tegadigan disk `revolve(π/2, matrix)` (lokal x→−Y, y→−Z, o'q→+X, markaz (0, R, −hc)); diffuzor — ikki to'rtburchak `loft`; FreeCAD da ham kompaund (3 jism) | πhc/3(R²+Rr+r²) + π²R³/2 + L/6(A1 + 4Am + A2) |

**Files:**
- Modify: `common/sath_common/ges_kinds.py` (importlar; yangi bo'limlar `# --- reyestr va API` dan yuqorida)
- Generated: `desktop/blender/sath/shared/ges_kinds.py`

**Interfaces:**
- Produces: `ges_kinds.penstock_path(length, inclination_deg, bend_radius, outlet_length) -> dict` (`physics.penstock_path` bilan bir xil); `KINDS` ga `GES_Penstock` (role `penstock:`), `GES_Turbine` (`unit:`), `GES_Generator` (`gen:`), `GES_DraftTube` (`draft:`).

- [ ] **Step 1: Importlar** — `import json` dan keyin `import math` qo'shing.

- [ ] **Step 2: Bo'limlarni qo'shing** — `# --- reyestr va API ---…` qatoridan YUQORIGA, aynan shu matn:

```python
def penstock_path(length: float, inclination_deg: float, bend_radius: float, outlet_length: float) -> dict:
    """Egri quvur o'qi (metr): kirish p0=(0,0,0) → qiya qism (u1) → yoy (R) → gorizontal +Y. Qaytaradi p0, p1 (yoy
    boshi), pm (yoy o'rtasi), p2 (yoy oxiri), p3 (chiqish), u1, alpha (rad), l1. `physics.penstock_path` bilan bir xil."""
    a = math.radians(inclination_deg)
    l1 = max(length * 0.1, length - outlet_length - bend_radius * a)
    u1 = (0.0, math.cos(a), -math.sin(a))
    n1 = (0.0, math.sin(a), math.cos(a))
    p1 = (0.0, u1[1] * l1, u1[2] * l1)
    c = (0.0, p1[1] + n1[1] * bend_radius, p1[2] + n1[2] * bend_radius)
    p2 = (0.0, c[1], c[2] - bend_radius)
    k = math.hypot(n1[1], n1[2] + 1.0)
    pm = (0.0, c[1] - n1[1] / k * bend_radius, c[2] - (n1[2] + 1.0) / k * bend_radius)
    p3 = (0.0, p2[1] + outlet_length, p2[2])
    return {"p0": (0.0, 0.0, 0.0), "p1": p1, "pm": pm, "p2": p2, "p3": p3, "u1": u1, "alpha": a, "l1": l1}


# --- Bosimli quvur: to'g'ri (Z bo'ylab halqa silindr) yoki egri (qiya → tirsak → gorizontal +Y; halqa sweep) ---------


def _penstock_axis(p: dict, tol: float, ro: float) -> tuple[list, list]:
    """Egri quvur o'qi nuqtalari va urinmalari: p0, yoy (k = 0..m), p3."""
    R = p["BendRadius"]
    pts = penstock_path(p["Length"], p["Inclination"], R, p["OutletLength"])
    a = pts["alpha"]
    c = (pts["p1"][1] + math.sin(a) * R, pts["p1"][2] + math.cos(a) * R)  # yoy markazi (y, z)
    m = max(2, math.ceil(geom.segments(R + ro, tol) * a / (2 * math.pi)))
    path, tans = [pts["p0"]], [pts["u1"]]
    for k in range(m + 1):
        g = a - a * k / m  # markazdan nuqtaga yo'nalish (0, −sin g, −cos g)
        path.append((0.0, c[0] - R * math.sin(g), c[1] - R * math.cos(g)))
        tans.append((0.0, math.cos(g), -math.sin(g)))
    path.append(pts["p3"])
    tans.append((0.0, 1.0, 0.0))
    return path, tans


def _penstock_parts(p: dict, tol: float) -> list:
    r, t, L = p["Diameter"] / 2, p["WallThickness"], p["Length"]
    ro = r + t
    if p["Inclination"] <= 0:
        return [geom.revolve([(r, 0.0), (ro, 0.0), (ro, L), (r, L)], tol=tol)]
    path, tans = _penstock_axis(p, tol, ro)
    n = geom.segments(ro, tol)
    return [geom.sweep(geom.circle(ro, n), path, tans, (1.0, 0.0, 0.0), hole=geom.circle(r, n))]


def _penstock_volume(p: dict) -> float:
    r, t, L = p["Diameter"] / 2, p["WallThickness"], p["Length"]
    ring = math.pi * ((r + t) ** 2 - r * r)
    if p["Inclination"] <= 0:
        return ring * L
    pts = penstock_path(L, p["Inclination"], p["BendRadius"], p["OutletLength"])
    return ring * (pts["l1"] + p["BendRadius"] * pts["alpha"] + p["OutletLength"])


def _penstock_check(p: dict) -> None:
    if p["Inclination"] > 0 and p["BendRadius"] <= p["Diameter"] / 2 + p["WallThickness"]:
        raise ValueError("Bosimli quvur: tirsak radiusi tashqi radiusdan katta bo'lsin")


_register(KindSpec(
    kind="GES_Penstock", label="Bosimli quvur", ifc_class="IfcPipeSegment", pset="Pset_GES_Penstock", role="penstock:",
    color=(0.45, 0.52, 0.60),
    params=(
        _len("Length", "Uzunligi", 20), _len("Diameter", "Ichki diametri", 2.4), _len("WallThickness", "Devor qalinligi", 0.02),
        _flt("Roughness", "G'adir-budirlik, mm (Darcy-Weisbach)", 0.1),
        _enum("Material", "Material", ("Po'lat", "Temir-beton", "GRP")),
        _flt("Inclination", "Qiyalik, ° (gorizontaldan pastga; 0 — to'g'ri)", 0),
        _len("BendRadius", "Tirsak radiusi", 8), _len("OutletLength", "Gorizontal chiqish qismi uzunligi", 6),
    ),
    fields=(
        _real("Diametr_m", "Diameter"), _real("Uzunlik_m", "Length"), _real("Gadirbudirlik_mm", "Roughness"),
        _label("Material", "Material"), _real("Qiyalik_deg", "Inclination"), _real("TirsakRadiusi_m", "BendRadius"),
        _real("ChiqishUzunligi_m", "OutletLength"),
    ),
    parts=_penstock_parts, volume=_penstock_volume, density=lambda p: DENSITY_PIPE[p["Material"]], check=_penstock_check,
))  # fmt: skip


# --- Turbina agregati: spiral kamera (tor) + val va korpus (bitta aylanish profili; fuse siz) ---------------------


def _turbine_parts(p: dict, tol: float) -> list:
    d, h = p["RunnerDiameter"], p["Height"]
    spiral = geom.torus(0.7 * d, 0.2 * d, tol=tol)
    body = geom.revolve(
        [(0.0, 0.0), (0.12 * d, 0.0), (0.12 * d, 0.6 * h), (0.5 * d, 0.6 * h), (0.5 * d, h), (0.0, h)], tol=tol
    )
    return [spiral, body]


def _turbine_volume(p: dict) -> float:
    d, h = p["RunnerDiameter"], p["Height"]
    return 2 * math.pi**2 * (0.7 * d) * (0.2 * d) ** 2 + math.pi * (0.12 * d) ** 2 * 0.6 * h + math.pi * (0.5 * d) ** 2 * 0.4 * h


_register(KindSpec(
    kind="GES_Turbine", label="Turbina agregati", ifc_class="IfcFlowMovingDevice", pset="Pset_GES_Turbine", role="unit:",
    color=(0.22, 0.65, 0.72),
    params=(
        _enum("TurbineType", "Turi", ("Francis", "Kaplan", "Pelton", "Bulb")),
        _flt("RatedPower", "Nominal quvvat, MW", 25), _flt("RatedHead", "Hisobiy napor, m", 45),
        _flt("RatedFlow", "Hisobiy sarf, m3/s", 62), _flt("Efficiency", "Maksimal FIK, 0..1", 0.92),
        _len("RunnerDiameter", "Ish g'ildiragi diametri", 3), _len("Height", "Agregat balandligi", 4),
    ),
    fields=(
        _label("Turi", "TurbineType"), _real("Quvvat_MW", "RatedPower"), _real("Napor_m", "RatedHead"),
        _real("Sarf_m3s", "RatedFlow"), _real("FIK", "Efficiency"),
    ),
    parts=_turbine_parts, volume=_turbine_volume,
))  # fmt: skip


# --- Generator: stator + 12 qovurg'a (bitta yulduzsimon profil cho'zilgan), qopqoq + qo'zg'atgich (aylanish), val --


def _generator_parts(p: dict, tol: float) -> list:
    d, h = p["StatorDiameter"], p["Height"]
    r, w, x_out = d / 2, 0.025 * d, 0.56 * d  # qovurg'a: x ∈ [0.48d, 0.56d], y ∈ [−w, w]
    xc, beta, step = math.sqrt(r * r - w * w), math.asin(w / r), 2 * math.pi / geom.segments(r, tol)
    prof = []
    for i in range(12):
        c = math.radians(30 * i)
        cs, sn = math.cos(c), math.sin(c)
        for x, y in ((xc, -w), (x_out, -w), (x_out, w), (xc, w)):
            prof.append((x * cs - y * sn, x * sn + y * cs, 0.0))
        a0, a1 = c + beta, c + math.radians(30) - beta  # qovurg'alar orasidagi stator yoyi
        m = max(1, math.ceil((a1 - a0) / step))
        for k in range(1, m):
            g = a0 + (a1 - a0) * k / m
            prof.append((r * math.cos(g), r * math.sin(g), 0.0))
    body = geom.extrude(prof, (0.0, 0.0, 0.7 * h))
    cap = geom.revolve(
        [(0.0, 0.7 * h), (0.35 * d, 0.7 * h), (0.2 * d, 0.9 * h), (0.15 * d, 0.9 * h), (0.15 * d, h), (0.0, h)], tol=tol
    )
    shaft = geom.cylinder(0.06 * d, 0.15 * h, base=(0.0, 0.0, -0.15 * h), tol=tol)
    return [body, cap, shaft]


def _generator_volume(p: dict) -> float:
    d, h = p["StatorDiameter"], p["Height"]
    r, w = d / 2, 0.025 * d
    seg = w * math.sqrt(r * r - w * w) + r * r * math.asin(w / r)  # ∫_{−w}^{w} √(r² − y²) dy
    rib_out = 0.08 * d * 0.05 * d - (seg - 2 * w * 0.48 * d)  # qovurg'aning stator tashqarisidagi yuzasi
    stator = 0.7 * h * (math.pi * r * r + 12 * rib_out)
    cap = math.pi * 0.2 * h / 3 * ((0.35 * d) ** 2 + 0.35 * d * 0.2 * d + (0.2 * d) ** 2)
    return stator + cap + math.pi * (0.15 * d) ** 2 * 0.1 * h + math.pi * (0.06 * d) ** 2 * 0.15 * h


_register(KindSpec(
    kind="GES_Generator", label="Generator", ifc_class="IfcElectricGenerator", pset="Pset_GES_Generator", role="gen:",
    color=(0.16, 0.45, 0.78),
    params=(
        _flt("RatedPower", "Nominal to'liq quvvat, MVA", 30), _flt("Voltage", "Stator kuchlanishi, kV", 10.5),
        _flt("EfficiencyMax", "Nominal FIK, 0..1", 0.985), _flt("IronLossFrac", "Temir (doimiy) yo'qotish ulushi, 0..1", 0.4),
        _int("Poles", "Qutblar soni", 24), _flt("Frequency", "Chastota, Hz", 50),
        _len("StatorDiameter", "Stator diametri", 6), _len("Height", "Balandligi", 3.5),
    ),
    fields=(
        _real("Quvvat_MVA", "RatedPower"), _real("Kuchlanish_kV", "Voltage"), _real("FIK", "EfficiencyMax"),
        _real("TemirUlushi", "IronLossFrac"), _count("Qutblar", "Poles"), _real("Chastota_Hz", "Frequency"),
        Field("Aylanish_rpm", "IfcReal", derive=lambda p: round(120.0 * p["Frequency"] / max(2, p["Poles"]), 2)),
    ),
    parts=_generator_parts, volume=_generator_volume,
))  # fmt: skip


# --- Chiqarish quvuri: konus (pastga kengayadi) + 90° tirsak (disk aylanishi) + to'g'ri burchakli diffuzor (loft) ---


def _drafttube_parts(p: dict, tol: float) -> list:
    d, hc = p["InletDiameter"], p["ConeHeight"]
    bw, bh, L = p["OutletWidth"], p["OutletHeight"], p["DiffuserLength"]
    R = 0.75 * d
    cone = geom.cone(R, d / 2, hc, base=(0.0, 0.0, -hc), tol=tol)
    # tirsak: konus tagidagi disk X o'qi atrofida (markaz (0, R, −hc)) 90° pastga; lokal (ρ, o'q) da disk o'qqa tegadi
    mat = [[0.0, 0.0, 1.0, 0.0], [-1.0, 0.0, 0.0, R], [0.0, -1.0, 0.0, -hc], [0.0, 0.0, 0.0, 1.0]]
    elbow = geom.revolve(geom.circle(R, geom.segments(R, tol), (R, 0.0)), math.pi / 2, tol=tol, matrix=mat)
    y0, z0 = R, -hc - R

    def rect(y: float, w: float, hh: float) -> list:
        return [(-w / 2, y, z0 - hh / 2), (w / 2, y, z0 - hh / 2), (w / 2, y, z0 + hh / 2), (-w / 2, y, z0 + hh / 2)]

    return [cone, elbow, geom.loft(rect(y0, 2 * R, 2 * R), rect(y0 + L, bw, bh))]


def _drafttube_volume(p: dict) -> float:
    d, hc = p["InletDiameter"], p["ConeHeight"]
    bw, bh, L = p["OutletWidth"], p["OutletHeight"], p["DiffuserLength"]
    R, r = 0.75 * d, d / 2
    a1, a2, am = 4 * R * R, bw * bh, (2 * R + bw) / 2 * (2 * R + bh) / 2  # prismatoid
    return math.pi * hc / 3 * (R * R + R * r + r * r) + math.pi**2 * R**3 / 2 + L / 6 * (a1 + 4 * am + a2)


_register(KindSpec(
    kind="GES_DraftTube", label="Chiqarish quvuri", ifc_class="IfcFlowSegment", pset="Pset_GES_DraftTube", role="draft:",
    color=(0.20, 0.40, 0.70),
    params=(
        _len("InletDiameter", "Kirish diametri (ish g'ildiragi ostida)", 3), _len("ConeHeight", "Konus balandligi", 5),
        _len("OutletWidth", "Chiqish kengligi", 8), _len("OutletHeight", "Chiqish balandligi", 4),
        _len("DiffuserLength", "Diffuzor uzunligi (+Y)", 12),
        _flt("SuctionHead", "So'rish balandligi H_s, m (ish g'ildiragi − quyi byef)", 2),
    ),
    fields=(
        _real("KirishDiametr_m", "InletDiameter"), _real("KonusBalandligi_m", "ConeHeight"),
        _real("ChiqishKenglik_m", "OutletWidth"), _real("ChiqishBalandlik_m", "OutletHeight"),
        _real("DiffuzorUzunligi_m", "DiffuserLength"), _real("SorishBalandligi_m", "SuctionHead"),
    ),
    parts=_drafttube_parts, volume=_drafttube_volume,
))  # fmt: skip
```

- [ ] **Step 3: Testlar**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_ges_kinds.py`
Expected: `55 passed, 21 skipped`.

Yiqilsa — diagnostika (har holat uchun hajm/bbox/yuza farqi, sabab qaysi qismda ekanini ko'rsatadi; superpowers:systematic-debugging):

```powershell
.venv\Scripts\python.exe -c "import json,sys; sys.path.insert(0,'common'); import numpy as np; from sath_common import geom, ges_kinds as K; G=json.load(open('desktop/tests/data/ges_golden.json',encoding='utf-8'))
for k,g in G['kinds'].items():
    if k not in K.KINDS: continue
    for c in g['cases']:
        ps=K.build_parts(k,c['params']); m=geom.merge(*ps); q=K.quantities(k,c['params'])['volume_m3']
        print(f\"{k:16}{c['id']:8} anal={q/c['volume_m3']-1:+.1e} mesh={geom.signed_volume(m)/c['volume_m3']-1:+.2e} bbox={np.abs(geom.bbox(m)-np.array(c['bbox_m'])).max():.4f} area={geom.area(m)/c['area_m2']-1:+.4f} parts={[round(geom.signed_volume(x),3) for x in ps]} closed={[geom.is_closed(x) for x in ps]}\")"
```
Sinalgan qiymatlar (shu kod bilan): mesh hajmi farqi ≤ 0.25 % (turbina 0.248 %, quvur 0.17 %, generator 0.10 %, chiqarish quvuri 0.09 %), analitik ≤ 1e-14, bbox farqi 0.0000.

- [ ] **Step 4: Nusxa, ruff, commit**

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py; .venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m ruff check common
```
```bash
git add common/sath_common/ges_kinds.py desktop/blender/sath/shared/ges_kinds.py
git commit -m "feat(P2): ges_kinds — bosimli quvur (halqa revolve/sweep), turbina, generator (yulduzsimon profil), chiqarish quvuri (tirsak revolve + loft) — boolean siz, FreeCAD bilan paritet ≤ 0.25 %" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `ges_kinds` — Transformator, Suv qabul qilgich, Boshqaruv xonasi; 11 tur va web farqlari

**Model:** sonnet — qutilardan iborat qobiqlar; teshik/oyna «1 mm» chiqishini to'g'ri saqlash kerak.

| Tur | Manba | Qurish (boolean siz) | Hajm |
|---|---|---|---|
| Transformator | 367–421 (391–413) | bak qutisi + 10 radiator (bak yon yuzasiga tegadi) + 3 izolyator silindri (bak ustida) — tegib turgan alohida qobiqlar | 0.7L·W·0.8H + 10·0.04L·0.15L·0.6H + 3π(0.05W)²·0.2H |
| Suv qabul qilgich | 424–464 (445–455) | minora − n teshik (−Y, chuqurlik 0.3D − 1 mm, z 0.1H…0.45H) → pastki qatlam + yuqori qatlam + orqa blok + teshiklar orasidagi ustunlar (qutilar) | WDH − 0.56W·(0.3D − 0.001)·0.35H (n ga bog'liq emas) |
| Boshqaruv xonasi | 584–617 (602–607) | xona − oyna (−Y, x ∈ ±0.4L, chuqurlik 0.1W − 1 mm, z 0.35H…0.8H) → 2 qatlam + orqa blok + 2 ustun | LWH − 0.8L·(0.1W − 0.001)·0.45H |

**Files:**
- Modify: `common/sath_common/ges_kinds.py` (bo'limlar `# --- reyestr va API` dan yuqorida)
- Modify: `desktop/tests/test_ges_kinds.py` (oxiriga 2 test, `import re`, web konstantalari)
- Generated: `desktop/blender/sath/shared/ges_kinds.py`

**Interfaces:**
- Produces: `KINDS` — to'liq 11 tur `ORDER` tartibida (`GES_Transformer` role `transformer:`, `GES_Intake` `intake`, `GES_ControlRoom` `controlroom`). Task 6 `KIND_ITEMS` ni shundan yasaydi.

- [ ] **Step 1: Bo'limlar** — `# --- reyestr va API` dan YUQORIGA:

```python
# --- Transformator: bak + 10 radiator (ikki yonda) + 3 izolyator — tegib turgan alohida qobiqlar -----------------


def _transformer_parts(p: dict, tol: float) -> list:
    L, W, H = p["Length"], p["Width"], p["Height"]
    parts = [geom.box((0.7 * L, W, 0.8 * H), (-0.35 * L, -W / 2, 0.0))]
    for i in range(5):
        x = -0.3 * L + i * (0.6 * L / 4)
        for side in (-1, 1):
            y = W / 2 if side > 0 else -W / 2 - 0.15 * L
            parts.append(geom.box((0.04 * L, 0.15 * L, 0.6 * H), (x, y, 0.1 * H)))
    for i in range(3):
        parts.append(geom.cylinder(0.05 * W, 0.2 * H, base=(-0.2 * L + i * 0.2 * L, 0.0, 0.8 * H), tol=tol))
    return parts


def _transformer_volume(p: dict) -> float:
    L, W, H = p["Length"], p["Width"], p["Height"]
    return 0.7 * L * W * 0.8 * H + 10 * 0.04 * L * 0.15 * L * 0.6 * H + 3 * math.pi * (0.05 * W) ** 2 * 0.2 * H


_register(KindSpec(
    kind="GES_Transformer", label="Transformator", ifc_class="IfcTransformer", pset="Pset_GES_Transformer",
    role="transformer:", color=(0.73, 0.53, 0.15),
    params=(
        _len("Length", "Uzunligi", 6), _len("Width", "Kengligi", 4), _len("Height", "Balandligi", 5),
        _flt("RatedPower", "Nominal quvvat, MVA", 40), _flt("VoltageHV", "Yuqori kuchlanish, kV", 110),
        _flt("VoltageLV", "Past kuchlanish, kV", 10.5),
        _enum("Cooling", "Sovitish turi (IEC 60076)", ("ONAN", "ONAF", "OFAF", "ODAF"), "ONAF"),
    ),
    fields=(
        _real("Quvvat_MVA", "RatedPower"), _real("KuchlanishYuqori_kV", "VoltageHV"),
        _real("KuchlanishPast_kV", "VoltageLV"), _label("Sovitish", "Cooling"),
    ),
    parts=_transformer_parts, volume=_transformer_volume,
))  # fmt: skip


# --- Suv qabul qilgich: minora, −Y yuzida n ta teshik (chuqurligi 0.3·D − 1 mm) — qatlamlar va ustunlar -----------


def _intake_parts(p: dict, tol: float) -> list:
    W, D, H = p["Width"], p["Depth"], p["Height"]
    n = max(1, int(p["Openings"]))
    ow, df, z0, z1 = 0.7 * W / n, 0.3 * D - EPS, 0.1 * H, 0.45 * H
    parts = [
        geom.box((W, D, z0), (-W / 2, -D / 2, 0.0)),
        geom.box((W, D, H - z1), (-W / 2, -D / 2, z1)),
        geom.box((W, D - df, z1 - z0), (-W / 2, -D / 2 + df, z0)),
    ]
    x = -W / 2
    for i in range(n):
        a = -0.35 * W + i * ow + 0.1 * ow
        parts.append(geom.box((a - x, df, z1 - z0), (x, -D / 2, z0)))
        x = a + 0.8 * ow
    parts.append(geom.box((W / 2 - x, df, z1 - z0), (x, -D / 2, z0)))
    return parts


def _intake_check(p: dict) -> None:
    if 0.3 * p["Depth"] <= EPS:
        raise ValueError("Suv qabul qilgich: chuqurlik juda kichik")


_register(KindSpec(
    kind="GES_Intake", label="Suv qabul qilgich", ifc_class="IfcBuildingElementProxy", pset="Pset_GES_Intake",
    role="intake", color=(0.49, 0.61, 0.71),
    params=(
        _len("Width", "Kengligi (X)", 8), _len("Depth", "Chuqurligi (Y)", 8), _len("Height", "Balandligi", 15),
        _flt("SillElevation", "Ostona belgisi, m (abs)", 0), _flt("DesignFlow", "Hisobiy sarf, m3/s", 120),
        _int("Openings", "Teshiklar soni", 2), _flt("ScreenBarSpacing", "Panjara oralig'i, mm", 100),
    ),
    fields=(
        _real("OstonaBelgisi_m", "SillElevation"), _real("HisobiySarf_m3s", "DesignFlow"), _count("Teshiklar", "Openings"),
        _real("PanjaraOraligi_mm", "ScreenBarSpacing"), _real("Balandlik_m", "Height"),
    ),
    parts=_intake_parts,
    volume=lambda p: p["Width"] * p["Depth"] * p["Height"] - 0.56 * p["Width"] * (0.3 * p["Depth"] - EPS) * 0.35 * p["Height"],
    density=_concrete, check=_intake_check,
))  # fmt: skip


# --- Boshqaruv xonasi: quti, −Y yuzida uzun oyna (chuqurligi 0.1·W − 1 mm) — qatlamlar va ustunlar ---------------


def _controlroom_parts(p: dict, tol: float) -> list:
    L, W, H = p["Length"], p["Width"], p["Height"]
    df, z0, z1 = 0.1 * W - EPS, 0.35 * H, 0.8 * H
    return [
        geom.box((L, W, z0), (-L / 2, -W / 2, 0.0)),
        geom.box((L, W, H - z1), (-L / 2, -W / 2, z1)),
        geom.box((L, W - df, z1 - z0), (-L / 2, -W / 2 + df, z0)),
        geom.box((0.1 * L, df, z1 - z0), (-L / 2, -W / 2, z0)),
        geom.box((0.1 * L, df, z1 - z0), (0.4 * L, -W / 2, z0)),
    ]


def _controlroom_check(p: dict) -> None:
    if 0.1 * p["Width"] <= EPS:
        raise ValueError("Boshqaruv xonasi: kenglik juda kichik")


_register(KindSpec(
    kind="GES_ControlRoom", label="Boshqaruv xonasi", ifc_class="IfcBuildingElementProxy", pset="Pset_GES_ControlRoom",
    role="controlroom", color=(0.82, 0.82, 0.86),
    params=(
        _len("Length", "Uzunligi (X)", 12), _len("Width", "Kengligi (Y)", 8), _len("Height", "Balandligi", 4),
        _flt("FloorElevation", "Pol belgisi, m (abs)", 0), _int("Operators", "Dispetcherlar soni", 2),
        _int("ScadaChannels", "SCADA kanallari soni", 256),
    ),
    fields=(
        _real("Uzunlik_m", "Length"), _real("Kenglik_m", "Width"), _real("Balandlik_m", "Height"),
        _real("PolBelgisi_m", "FloorElevation"), _count("Dispetcherlar", "Operators"), _count("SCADA_Kanallar", "ScadaChannels"),
    ),
    parts=_controlroom_parts,
    volume=lambda p: p["Length"] * p["Width"] * p["Height"] - 0.8 * p["Length"] * (0.1 * p["Width"] - EPS) * 0.45 * p["Height"],
    check=_controlroom_check,
))  # fmt: skip
```

- [ ] **Step 2: Yakuniy testlar** — `desktop/tests/test_ges_kinds.py`: importlarga `import re` (alfavit bo'yicha `import json` dan keyin), `AREA_EXACT = …` qatoridan keyin:

```python
WEB = ROOT / "web" / "src" / "viewer" / "draftKinds.ts"
# Web qoralama turlari ↔ desktop: ma'lum farqlar. O'zgarsa — ataylab (ikkala tomonni yoki shu ro'yxatni yangilang).
WEB_ONLY = {"Pset_GES_Penstock": {"DevorQalinligi_mm"}, "Pset_GES_Spillway": {"BetonKlassi"}}
DESKTOP_ONLY = {
    "Pset_GES_Penstock": {"Qiyalik_deg", "TirsakRadiusi_m", "ChiqishUzunligi_m"},
    "Pset_GES_Powerhouse": {"Uzunlik_m", "Kenglik_m", "Balandlik_m"},
}
```

va fayl oxiriga:

```python
def test_all_eleven_kinds_ported_in_order():
    assert tuple(ges_kinds.KINDS) == ges_kinds.ORDER and len(ges_kinds.ORDER) == 11
    assert set(GOLDEN["kinds"]) == set(ges_kinds.ORDER)


def test_web_draft_pset_fields_known_diff():
    src = WEB.read_text(encoding="utf-8")
    web = {
        m.group(1): set(re.findall(r'key: "(\w+)"', m.group(2)))
        for m in re.finditer(r'pset: \{ name: "(Pset_GES_\w+)", fields: \[(.*?)\] \}', src, re.S)
    }
    assert set(web) == {f"Pset_GES_{x}" for x in ("Dam", "Penstock", "Turbine", "Spillway", "Powerhouse", "Transformer", "Intake")}
    for name, keys in web.items():
        ours = {f.name for f in ges_kinds.spec(ges_kinds.KIND_BY_PSET[name]).fields}
        assert keys - ours == WEB_ONLY.get(name, set()), name
        assert ours - keys == DESKTOP_ONLY.get(name, set()), name
```

- [ ] **Step 3: Testlar**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_ges_kinds.py desktop/tests/test_geom.py`
Expected: `92 passed` (78 + 14; skip yo'q).

- [ ] **Step 4: Nusxa, ruff, commit**

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py; .venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m ruff check common desktop/tests
```
```bash
git add common/sath_common/ges_kinds.py desktop/tests/test_ges_kinds.py desktop/blender/sath/shared/ges_kinds.py
git commit -m "feat(P2): ges_kinds — transformator, suv qabul qilgich, boshqaruv xonasi; 11 tur FreeCAD etaloni bilan paritetda, web qoralama pset farqlari testda" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Blender — `ges_objects` va `demo_plant` `ges_kinds` ga, mesh `foreach_set` bilan

**Model:** sonnet — ko'p faylli integratsiya, headless testlar bilan.

**Files:**
- Modify (to'liq almashtirish, CRLF): `desktop/blender/sath/ges_objects.py`
- Modify (CRLF): `desktop/blender/sath/demo_plant.py:33-38` (`_add`)
- Create: `desktop/tests/sath_tests/kinds_mesh.py`
- Delete: `desktop/tests/sath_tests/engine.py`
- Modify: `desktop/tests/sath_tests/objects.py`, `desktop/tests/sath_tests/demo_plant.py` (CRLF), `desktop/tests/sath_tests/e2e_server.py`, `desktop/tests/run_blender_tests.ps1`

**Interfaces:**
- Consumes: `shared.ges_kinds` (Task 3–5).
- Produces: `ges_objects.KIND_ITEMS` (11, eski tartib), `KIND_LABEL`, `set_mesh(me, verts, faces)`, `rebuild_mesh(obj)`, `write_ifc(obj)`, `rebuild(obj)` (= mesh + IFC), `add(context, kind, name=None, role="", **params)`, `_fill_schema(obj, kind, values=None)`; `SATH_OT_add_object` da `poll` yo'q (FreeCAD ga bog'liq emas). Task 8–9 shu funksiyalarni kengaytiradi.

- [ ] **Step 1: Headless test** — `desktop/tests/sath_tests/kinds_mesh.py` (avvalgi `engine` o'rnida)

```python
"""ges_kinds → Blender mesh (numpy foreach_set), FreeCAD siz: 11 tur, mesh yaroqli (validate), manifold, bmesh hajmi
analitik hajmga mos; generator sinxron tezligi; egri quvur pastga tushadi (avvalgi `engine` testi o'rnida)."""

import time

import bmesh
import bpy


def run(ctx):
    from sath import ges_objects
    from sath.shared import ges_kinds

    assert [k for k, _, _ in ges_objects.KIND_ITEMS] == list(ges_kinds.ORDER)
    t0 = time.perf_counter()
    for kind in ges_kinds.ORDER:
        v, f = ges_kinds.build(kind, {})
        me = bpy.data.meshes.new(kind)
        ges_objects.set_mesh(me, v, f)
        assert (len(me.vertices), len(me.polygons)) == (len(v), len(f)), kind
        assert not me.validate(), f"{kind}: mesh yaroqsiz edi (validate tuzatdi)"
        bm = bmesh.new()
        bm.from_mesh(me)
        vol = bm.calc_volume(signed=True)
        bad = [e for e in bm.edges if not e.is_manifold]
        bm.free()
        q = ges_kinds.quantities(kind)["volume_m3"]
        assert not bad and abs(vol - q) / q < 5e-3, (kind, len(bad), vol, q)
    ms = (time.perf_counter() - t0) * 1000
    assert ms < 3000, f"11 tur {ms:.0f} ms"
    assert ges_kinds.psets("GES_Generator", {"Poles": 48})["Pset_GES_Generator"]["Aylanish_rpm"] == 125.0
    v, _ = ges_kinds.build("GES_Penstock", {"Length": 60.0, "Inclination": 40.0})
    assert v[:, 2].min() < -30, v[:, 2].min()
    print(f"KINDS_MESH: 11 tur {ms:.0f} ms", flush=True)
```

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test kinds_mesh 2>&1 | Select-String "OK|FAIL|KINDS_MESH|Error"`
Expected: `[FAIL] kinds_mesh` (`AttributeError: … 'set_mesh'`).

- [ ] **Step 2: `ges_objects.py` ni almashtiring** (fayl CRLF — yozgach Global Constraints dagi buyruq bilan CRLF ni tiklang)

```python
"""GES parametrik obyektlari Blender da: parametrlar obyektda (Object.ges), sxema va geometriya — sof Python
`shared/ges_kinds` (+ `shared/geom`, numpy; FreeCAD siz), IFC element + Pset_GES_* Bonsai da. Mesh Blender ga
numpy massivlari bilan (`foreach_set`) uzatiladi. Parametr o'zgarsa mesh va psetlar qayta quriladi."""

from __future__ import annotations

import os

import bpy
import numpy as np

from . import ifc
from .shared import ges_kinds

KIND_ITEMS = [(k, s.label, "") for k, s in ges_kinds.KINDS.items()]
KIND_LABEL = {k: s.label for k, s in ges_kinds.KINDS.items()}


def _enum_items(self, context):
    return [(x, x, "") for x in self.items.split(";") if x]


_pending: set[str] = set()
DEBOUNCE = 0.15


def flush_pending():
    """Kechiktirilgan qayta qurish: parametrni sudrab o'zgartirganda har qadamda emas, to'planib bir marta."""
    names = list(_pending)
    _pending.clear()
    for n in names:
        obj = bpy.data.objects.get(n)
        if obj is not None and obj.ges.kind:
            try:
                rebuild(obj)
            except Exception as e:  # noqa: BLE001 — bitta obyekt xatosi qolganini to'xtatmasin
                print("sath: qayta qurish xatosi", n, e)
    return None


def _changed(self, context):
    obj = self.id_data
    if getattr(obj, "ges", None) is None or not obj.ges.kind or obj.ges.busy:
        return
    if bpy.app.background:  # testlar: darhol
        rebuild(obj)
        return
    _pending.add(obj.name)
    if not bpy.app.timers.is_registered(flush_pending):
        bpy.app.timers.register(flush_pending, first_interval=DEBOUNCE)


class GesParam(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ptype: bpy.props.StringProperty()  # length | float | int | enum
    items: bpy.props.StringProperty()  # enum: "a;b;c"
    value_float: bpy.props.FloatProperty(precision=3, update=_changed)
    value_int: bpy.props.IntProperty(update=_changed)
    value_enum: bpy.props.EnumProperty(items=_enum_items, update=_changed)


class GesObject(bpy.types.PropertyGroup):
    kind: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty(default=False)
    role: bpy.props.StringProperty(description="Egizakdagi roli: unit:1, gen:1, draft:1, penstock:1, dam, tailrace…")
    params: bpy.props.CollectionProperty(type=GesParam)


def params_dict(obj) -> dict:
    out = {}
    for p in obj.ges.params:
        if p.ptype == "enum":
            out[p.name] = p.value_enum
        elif p.ptype == "int":
            out[p.name] = p.value_int
        else:
            out[p.name] = p.value_float
    return out


def set_params(obj, **values) -> None:
    """Bir nechta parametrni bir yo'la o'rnatib, bir marta qayta qurish (har birida rebuild emas)."""
    g = obj.ges
    g.busy = True
    try:
        for p in g.params:
            if p.name not in values:
                continue
            v = values[p.name]
            if p.ptype == "enum":
                p.value_enum = str(v)
            elif p.ptype == "int":
                p.value_int = int(v)
            else:
                p.value_float = float(v)
    finally:
        g.busy = False
    rebuild(obj)


def by_role(role: str):
    return next((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.role == role), None)


def by_kind_all() -> list:
    return [o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind]


def by_kind(kind: str) -> list:
    return sorted((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind == kind), key=lambda o: o.name)


def _fill_schema(obj, kind: str, values: dict | None = None) -> None:
    """Sxema (ges_kinds) → obj.ges.params; values — parametrlar (tekshiriladi), yo'q bo'lsa defaultlar."""
    vals = ges_kinds.normalize(kind, values)
    g = obj.ges
    g.busy = True
    try:
        g.kind = kind
        g.params.clear()
        for prm in ges_kinds.spec(kind).params:
            p = g.params.add()
            p.name, p.label, p.ptype = prm.name, prm.label, prm.ptype
            v = vals[prm.name]
            if prm.ptype == "enum":
                p.items = ";".join(prm.items)
                p.value_enum = v
            elif prm.ptype == "int":
                p.value_int = v
            else:
                p.value_float = v
    finally:
        g.busy = False


def set_mesh(me, verts: np.ndarray, faces: np.ndarray) -> None:
    """(V float64, F int64 uchburchak) → bpy Mesh, numpy foreach_set bilan (from_pydata Python ro'yxatlarisiz)."""
    me.clear_geometry()
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(faces, dtype=np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update(calc_edges=True)


def rebuild_mesh(obj) -> None:
    """Parametrlardan mesh (ges_kinds.build). Yaroqsiz parametr — ValueError (matn foydalanuvchiga)."""
    v, f = ges_kinds.build(obj.ges.kind, params_dict(obj))
    set_mesh(obj.data, v, f)


def write_ifc(obj) -> None:
    """IFC element (yo'q bo'lsa assign_class) yoki representation + Pset_GES_* yangilash."""
    g = obj.ges
    ps = ges_kinds.psets(g.kind, params_dict(obj))
    e = ifc.entity(obj)
    if e is None:
        ifc.assign_class(obj, ges_kinds.spec(g.kind).ifc_class, ps)
    else:
        ifc.update_representation(obj)
        ifc.write_psets(e, ps)


def rebuild(obj) -> None:
    """Mesh (ges_kinds) + IFC (representation, psetlar)."""
    rebuild_mesh(obj)
    write_ifc(obj)


def add(context, kind: str, name: str | None = None, role: str = "", **params):
    """GES obyekti: parametrlar darhol beriladi (keyin set_params bilan qayta qurish shart emas)."""
    ifc.ensure_project()  # avval: GUI da create_project sahnani qayta quradi (obyekt havolasi eskiradi)
    s = ges_kinds.spec(kind)
    me = bpy.data.meshes.new(kind)
    obj = bpy.data.objects.new(name or s.label, me)
    context.scene.collection.objects.link(obj)
    obj.color = (*s.color, 1.0)
    _fill_schema(obj, kind, params)
    obj.ges.role = role
    rebuild(obj)
    return obj


class SATH_OT_add_object(bpy.types.Operator):
    """GES obyekti qo'shish (sof Python geometriya, IFC element + Pset_GES_*)"""

    bl_idname = "sath.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    def execute(self, context):
        try:
            obj = add(context, self.kind)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Obyekt yaratilmadi: {e}")
            return {"CANCELLED"}
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"{KIND_LABEL[self.kind]} qo'shildi")
        return {"FINISHED"}


class SATH_OT_rebuild_object(bpy.types.Operator):
    """Tanlangan GES obyektlarini qayta hisoblash"""

    bl_idname = "sath.rebuild_object"
    bl_label = "Qayta qurish"

    def execute(self, context):
        n = 0
        for o in context.view_layer.objects:
            if o.select_get() and o.ges.kind:
                rebuild(o)
                n += 1
        self.report({"INFO"}, f"{n} obyekt qayta qurildi")
        return {"FINISHED"}


class SATH_PT_objects(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Sath"
    bl_label = "GES obyektlari"

    def draw(self, context):
        lay = self.layout
        s = context.scene.ges
        box = lay.box()
        row = box.row(align=True)
        row.prop(s, "demo_head")
        row.prop(s, "demo_units")
        row = box.row(align=True)
        row.prop(s, "demo_unit_mw")
        row.operator("sath.build_demo_plant", icon="ADD")
        if s.twin_note:
            box.label(text=s.twin_note, icon="INFO")
        grid = lay.grid_flow(columns=2, align=True)
        for k, label, _ in KIND_ITEMS:
            grid.operator("sath.add_object", text=label).kind = k
        obj = context.active_object
        if obj is None or not obj.ges.kind:
            return
        box = lay.box()
        box.label(text=f"{KIND_LABEL.get(obj.ges.kind, obj.ges.kind)}: {obj.name}", icon="MOD_BUILD")
        for p in obj.ges.params:
            row = box.row()
            if p.ptype == "enum":
                row.prop(p, "value_enum", text=p.label)
            elif p.ptype == "int":
                row.prop(p, "value_int", text=p.label)
            else:
                row.prop(p, "value_float", text=p.label + (", m" if p.ptype == "length" else ""))
        box.operator("sath.rebuild_object", icon="FILE_REFRESH")


CLASSES = (GesParam, GesObject, SATH_OT_add_object, SATH_OT_rebuild_object, SATH_PT_objects)


def register():
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi (ui.py bilan bir xil)
        SATH_PT_objects.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)


def unregister():
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 3: `demo_plant._add`** (CRLF) — parametrlar yaratishda beriladi (har obyekt uchun IFC bir marta yoziladi):

```python
def _add(context, kind: str, name: str, role: str, **params):
    return ges_objects.add(context, kind, name, role=role, **params)
```

- [ ] **Step 4: Testlarni FreeCAD dan ajrating**

- `desktop/tests/sath_tests/engine.py` — `git rm`.
- `objects.py`: `from _req import require_freecad` / `require_freecad()` qatorlarini o'chiring; `from sath import fc_engine, ges_objects, ifc` → `from sath import ges_objects, ifc`; `kinds = [k for k, _ in fc_engine.ges_kinds()]` → `kinds = [k for k, _, _ in ges_objects.KIND_ITEMS]`; docstring: «11 GES obyekt FreeCAD siz yaratiladi: …».
- `demo_plant.py` (CRLF): `from _req import require_freecad` va `require_freecad()` qatorlarini (va ulardan keyingi bo'sh qatorni) o'chiring.
- `e2e_server.py`: `from sath import fc_engine, ges_objects, …` → `from sath import ges_objects, …`; `assert fc_engine.doc() is not None` qatorini o'chiring; docstring «Bonsai + FreeCAD kerak» → «Bonsai kerak».
- `run_blender_tests.ps1`: `@("engine", "")` → `@("kinds_mesh", "")`.

- [ ] **Step 5: FreeCAD ko'rinmas holda headless**

```powershell
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; $env:GES_FC_HOME="C:\yoq"
foreach ($t in @(@("kinds_mesh",""),@("objects","--bonsai"),@("demo_plant","--bonsai"),@("ifc_bridge","--bonsai"),@("undo_rep","--bonsai"),@("import_ops",""))) { & $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test $t[0] $t[1] 2>&1 | Select-String "\[OK\]|\[FAIL\]|\[SKIP\]|KINDS_MESH|DEMO:" }
.\desktop\tests\run_blender_tests.ps1
Remove-Item Env:GES_FC_HOME
```
Expected: har biri `[OK]` (`KINDS_MESH: 11 tur ~100 ms`, `DEMO: 16 obyekt; …; gap <1`); to'plam: `FAIL soni: 0 · SKIP: 0` (19 test). `import_ops` FreeCAD siz ezdxf yo'liga o'tadi — yiqilsa bu Task 7 dan OLDIN tuzatilishi kerak (superpowers:systematic-debugging).

- [ ] **Step 6: EOL va ruff**

```powershell
git ls-files --eol desktop/blender/sath/ges_objects.py desktop/blender/sath/demo_plant.py desktop/tests/sath_tests/demo_plant.py desktop/tests/sath_tests/kinds_mesh.py
.venv\Scripts\python.exe -m ruff check desktop
```
Expected: birinchi uchtasi `w/crlf`, `kinds_mesh.py` `w/lf`; `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/ges_objects.py desktop/blender/sath/demo_plant.py desktop/tests/sath_tests desktop/tests/run_blender_tests.ps1
git commit -m "feat(P2): GES obyektlari va Namuna GES FreeCAD siz — sxema/mesh ges_kinds dan, mesh numpy foreach_set bilan; add_object.poll FreeCAD ga bog'liq emas; engine testi kinds_mesh bilan almashdi" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: FreeCAD ni olib tashlash va legacy trekni arxivlash (K1)

**Model:** sonnet — ko'p faylli tozalash, test/CI/bundle tekshiruvi bilan.

**Arxiv qarori — `archive/` papka emas, annotatsiyalangan teg `archive/freecad-legacy`:** (1) papkadagi arxiv kod ruff/pytest/sync/IDE qidiruvida qoladi va FreeCAD importlari bilan «tirikdek» ko'rinadi, `test_server_client`/`test_ifc43` unga yopishib qolgan; (2) `Namuna GES.FCStd` (LFS) va fork skriptlari klon hajmini oshiradi; (3) teg workbench + fork quvuri + sync + testlarning OXIRGI ishlagan holatini bitta commit da muzlatadi (tarmoqdan farqli tasodifan siljimaydi): `git checkout archive/freecad-legacy -- desktop/GesWorkbench` bilan tiklanadi. Spec (§6) «`archive/` ga yoki alohida tarmoqqa (git tarixida qoladi)» — teg tarmoqning o'zgarmas varianti.

**Files:**
- Delete: `desktop/blender/sath/fc_engine.py`, `desktop/blender/sath/wb/`, `desktop/GesWorkbench/`, `desktop/blender/spike/`, `desktop/build/sync_fork.py`, `desktop/build/build_portable.py`, `desktop/tests/fc_cad.py`, `desktop/tests/fc_gui.py`, `desktop/tests/fc_headless.py`, `desktop/tests/test_freecad_cad.py`, `desktop/tests/Namuna GES.FCStd`
- Modify: `desktop/build/sync_blender.py`, `desktop/blender/sath/ops_import.py`, `cad_read.py`, `converters.py`, `prefs.py`, `__init__.py` (CRLF), `blender_manifest.toml`, `desktop/build/build_blender_bundle.py` (CRLF), `desktop/tests/sath_tests/_req.py`, `import_ezdxf.py`, `import_ops.py`, `desktop/tests/blender_headless.py`, `blender_gui_check.py` (CRLF), `run_blender_tests.ps1`, `.github/workflows/ci.yml`, `desktop/tests/test_sath_pure.py`, `test_sath_import.py`, `test_server_client.py`, `server/tests/test_ifc43.py`, `ruff.toml`

**Interfaces:**
- Produces: teg `archive/freecad-legacy`; `ops_import.import_dxf(context, path, prepare=True, unit="AUTO", report=None, assign_ifc=False)` (`engine` parametri yo'q); `run_blender_tests.ps1` `SATH_REQUIRE_NO_SKIP=1` da SKIP > 0 → exit 1; bundle `freecad/` siz.

- [ ] **Step 1: Arxiv tegi (o'chirishdan OLDIN, HEAD = Task 6 commit)**

```bash
git tag -a archive/freecad-legacy -m "FreeCAD legacy trek (P2 dan oldingi oxirgi holat): desktop/GesWorkbench, Sath-FreeCAD fork quvuri (sync_fork, build_portable), sath/fc_engine + wb, FreeCAD testlari, Blender+FreeCAD spike, ges_golden generatori ishlaydigan holatda"
git show --stat archive/freecad-legacy | Select-Object -First 3
```

- [ ] **Step 2: O'chirish**

```powershell
git rm -r -q desktop/GesWorkbench desktop/blender/spike desktop/blender/sath/wb desktop/blender/sath/fc_engine.py desktop/build/sync_fork.py desktop/build/build_portable.py desktop/tests/fc_cad.py desktop/tests/fc_gui.py desktop/tests/fc_headless.py desktop/tests/test_freecad_cad.py "desktop/tests/Namuna GES.FCStd"
foreach ($d in "desktop/GesWorkbench","desktop/blender/spike","desktop/blender/sath/wb") { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }  # qolgan __pycache__
```

- [ ] **Step 3: `sync_blender.py`**

Docstring dagi `* FreeCAD workbench (legacy): desktop/GesWorkbench/ges_workbench/` va `FreeCAD ga bog'liq ges_objects.py ning manbasi GesWorkbench, nusxasi — sath/wb/.` qatorlarini o'chiring. `WB_SRC`, `WB_FILES`, `WB_DST`, `WB_INIT` qatorlarini va `EXTRA` dagi `WB_SRC: CORE_FILES,` ni o'chiring; `copies()` dagi `pairs += [(WB_SRC / f, WB_DST / f) for f in WB_FILES]` ni o'chiring; `sync()`:

```python
def sync() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    (DST / "__init__.py").write_text(INIT, encoding="utf-8")
    for src, dst in copies():
        shutil.copyfile(src, dst)
```

- [ ] **Step 4: `ops_import.py` — FreeCAD DXF yo'li**

1-qator docstring: `"""DXF/DWG (ezdxf, qatlam → collection; DWG — dwg2dxf/ODA orqali) va mesh (assimp) import."""`. `from . import cad_read, converters, fc_engine, flows, ifc` → `from . import cad_read, converters, flows, ifc`. `_edges_to_curve`, `_layer_of`, `ENGINE_ITEMS`, `_import_dxf_fc` ni butunlay o'chiring. `import_dxf`:

```python
def import_dxf(
    context,
    path: Path,
    prepare: bool = True,
    unit: str = "AUTO",
    report: list | None = None,
    assign_ifc: bool = False,
) -> int:
    """DWG/DXF → Blender (ezdxf; DWG avval dwg2dxf/ODA bilan DXF ga). Qaytaradi: obyekt soni. unit — "AUTO"
    ($INSUNITS) yoki UNITS kaliti; report — ogohlantirishlar; assign_ifc — 3D yuzalar IFC elementga aylantiriladi
    (chiziqlar IFC ga kirmaydi, commit da ogohlantiriladi)."""
    before = set(bpy.data.objects)
    work = Path(tempfile.mkdtemp(prefix="sath-dxf-"))  # har import o'z papkasida (CAD-06), oxirida o'chiriladi
    try:
        n = _import_dxf_ezdxf(Path(path), work, prepare, unit, report)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if assign_ifc:
        assign_imported([o for o in bpy.data.objects if o not in before], report)
    return n
```

`_import_dxf_ezdxf` docstring: `"""ezdxf → 3D yuzalar (qatlam bo'yicha mesh) va chiziqlar (qatlam bo'yicha egri chiziq)."""`. `SATH_OT_import_dxf`: docstring `"""DWG/DXF chizmani ochish (ezdxf, qatlamlar collection sifatida)"""`; `engine: bpy.props.EnumProperty(...)` qatorini o'chiring; `execute` dan `if self.engine == "FREECAD" …` blokini (3 qator) o'chiring; chaqiruv: `n = import_dxf(context, Path(self.filepath), self.prepare, self.unit, warnings, assign_ifc=self.assign_ifc)`.

`git grep -n "import_dxf(" desktop` — qolgan chaqiruvlar: `import_ezdxf.py` da ikkala `engine="EZDXF"` argumentini o'chiring; `import_ops.py` docstring: `"""DWG → DXF (dwg2dxf) → ezdxf → Blender curve/mesh (qatlam collection); FBX → assimp → mesh."""`.

- [ ] **Step 5: Qolgan addon fayllari**

`cad_read.py`: `freecad_dxf_factor` funksiyasini o'chiring. `test_sath_import.py`: test nomini `test_resolve_dxf_units` ga o'zgartiring va uchta `cad_read.freecad_dxf_factor(...)` assert qatorini hamda `# FreeCAD importDXF …` izohini o'chiring (`resolve` assertlari qoladi; oxirgi qator `r = cad_read.resolve(tmp_path / "u.dxf", unit="m")` dan keyin `assert r.scale == 1.0 and not r.warnings`).

`converters.py` — 1-qator docstring o'zgarmaydi; `_candidate_dirs` boshini almashtiring:

```python
def _bundle_dir() -> Path | None:
    """Sath bundle ildizi (Sath.exe yonida `tools/`) yoki None (bpy siz — pytest)."""
    try:
        import bpy

        root = Path(bpy.app.binary_path).resolve().parent
    except Exception:  # noqa: BLE001
        return None
    return root if (root / "tools").is_dir() else None


def _candidate_dirs() -> list[Path]:
    dirs = []
    v = os.environ.get("GES_TOOLS_DIR")
    if v:
        dirs += [Path(v), Path(v) / "tools", Path(v) / "tools" / "libredwg"]
    b = _bundle_dir()
    if b is not None:
        dirs += [b / "tools", b / "tools" / "libredwg"]  # Sath bundle
```
(`dirs += [Path(__file__)…` bilan boshlanadigan davomi o'zgarmaydi.)

`prefs.py`:

```python
"""Addon sozlamalari: server manzili, login, yangilanish kaliti. Parol saqlanmaydi (faqat sessiya)."""

from __future__ import annotations

import os

import bpy

PKG = __package__  # "bl_ext.user_default.sath" yoki headless da "sath"


class GesPrefs(bpy.types.AddonPreferences):
    bl_idname = PKG
    # HTTPS default (SEC-03): parol va yangilanish paketlari ochiq kanalda uzatilmasin; lokal dev — http://localhost:8000
    server: bpy.props.StringProperty(name="Server", default="https://ges-server")
    username: bpy.props.StringProperty(name="Login", default="")
    # SEC-03: desktop paketlari imzosini tekshirish uchun nashr qiluvchining Ed25519 ochiq kaliti (base64);
    # berilsa imzosiz/noto'g'ri imzoli paket o'rnatilmaydi
    update_public_key: bpy.props.StringProperty(
        name="Yangilanish kaliti",
        default=os.environ.get("SATH_UPDATE_PUBLIC_KEY", ""),
        description="Paket imzosini tekshirish uchun ochiq kalit (base64, administrator beradi)",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "server")
        col.prop(self, "username")
        col.prop(self, "update_public_key")
```
(`prefs()`, `register`, `unregister` o'zgarmaydi.)

`__init__.py` (CRLF) docstring: `"""Sath Blender addoni: server (versiyalar, taqriz, sim, monitoring), GES obyektlari (sof Python geometriya,` / `FreeCAD siz), DXF/DWG import. IFC — Bonsai."""`. `blender_manifest.toml` 12-qatordagi ` FreeCAD dvigateli ixtiyoriy.` ni o'chiring.

- [ ] **Step 6: `build_blender_bundle.py`** (CRLF)

- Docstring (1–8):
```python
"""Sath desktop bundle (kompilyatsiyasiz): rasmiy Blender 5.2 + Sath app template/splash + Sath.exe (ikonka)
+ portable prefs (Bonsai va sath extension lari yoqilgan) + libredwg. FreeCAD yo'q (P2: GES geometriyasi sof Python).

python desktop/build/build_blender_bundle.py [--blender ~/Tools/blender-5.2] [--bonsai <zip>] [--no-zip]
        [--installer] [--keep-stage]
Natija: desktop/dist/Sath-Blender-<ver>-Windows-x86_64.zip (+ -installer.exe, .build.json — product: sath-blender).
Stage: desktop/build/_work/sath-bundle/Sath.
"""
```
- `# FreeCAD conda muhitidan …` izohidan `FC_KEEP_EXE = ("freecad",)` gacha (32–52) o'chiring; `PRODUCT = "sath-blender"  # CODE-03: build metama'lumotidagi mahsulot`.
- `_fc_ignore` va `copy_freecad` funksiyalarini o'chiring.
- `write_readme`:
```python
def write_readme(ver: str) -> None:
    (STAGE / "Sath-VERSION.txt").write_text(f"Sath {ver}\n", encoding="utf-8")
    (STAGE / "Sath-README.txt").write_text(
        f"""Sath {ver} — gidroelektrostansiya BIM (Blender 5.2 + Bonsai)

Ishga tushirish: Sath.exe (yoki blender.exe). Sozlamalar va extension lar `portable\\` papkasida —
kompyuterdagi boshqa Blender bilan aralashmaydi. 3D Viewport → N panel → «Sath» yorlig'i.
Server: Sath → Server → manzil, login, parol → Ulanish.
DWG/DXF: tools\\libredwg (dwg2dxf).
""",
        encoding="utf-8",
    )
```
- `main()`: `--fc-home` va `--no-freecad` argumentlarini, `if not a.no_freecad: …` blokini (4 qator) o'chiring; `copy_libredwg()` dan oldin `shutil.rmtree(STAGE / "freecad", ignore_errors=True)  # eski stage (--keep-stage) dagi FreeCAD`; `write_readme(ver, not a.no_freecad)` → `write_readme(ver)`.

- [ ] **Step 7: Test infratuzilmasi**

`desktop/tests/sath_tests/_req.py`:
```python
"""Headless testlar uchun talablar: sharoit yo'q bo'lsa test yiqilmaydi, [SKIP] bo'ladi (K7). CI da SKIP taqiqlangan
(SATH_REQUIRE_NO_SKIP=1) — SkipTest faqat haqiqatan ixtiyoriy tashqi sharoit uchun."""

from __future__ import annotations


class SkipTest(Exception):
    """Test sharoiti yo'q — runner `[SKIP]` yozadi, exit 0."""
```
`blender_headless.py`: `# K7: FreeCAD yo'li …` izoh qatorini o'chiring. `blender_gui_check.py` (CRLF): `os.environ.setdefault("GES_FC_HOME", …)` qatorini o'chiring. `run_blender_tests.ps1` 1-qator: `# Sath Blender addoni headless testlari (Blender 5.2 + Bonsai; FreeCAD kerak emas).`; oxirgi `exit $fails` dan oldin:
```powershell
if ($fails -eq 0 -and $skips -gt 0 -and $env:SATH_REQUIRE_NO_SKIP -eq "1") { "SKIP taqiqlangan (SATH_REQUIRE_NO_SKIP=1)"; exit 1 }
```
`.github/workflows/ci.yml` `desktop-blender`: izoh (117–119):
```yaml
    # K7: Blender addoni headless testlari — Blender 5.2.2 + Bonsai 0.9.0 (sha256 pin); FreeCAD yo'q (P2) va SKIP
    # taqiqlangan (SATH_REQUIRE_NO_SKIP). Server talab qiladigan testlar (GES_TEST_SERVER) bu yerda ishlamaydi.
```
va «Headless testlar» qadamiga `env: { SATH_REQUIRE_NO_SKIP: "1" }`.

`ruff.toml`: `extend-exclude` dan `"desktop/blender/spike"` ni olib tashlang.

- [ ] **Step 8: pytest fayllari**

`test_sath_pure.py`:
- `from sath import fc_engine  # noqa: E402` va `test_parse_props_groups_by_pset_and_casts`, `test_ifc_class_from_freecad_type` ni o'chiring (IFC klass xaritasi endi `test_ges_kinds` da).
- `test_common_copies_byte_identical_to_canonical`: `assert f"desktop/GesWorkbench/ges_workbench/{f}" in dsts` qatorini o'chiring, docstring «(addon, server)».
- `test_legacy_parts_are_marked` o'rniga:
```python
def test_freecad_removed_from_desktop():
    """P2 (K1): FreeCAD desktopdan chiqdi — dvigatel, workbench nusxasi, legacy workbench/fork skriptlari, FreeCAD
    testlari repoda yo'q; addon kodida FreeCAD importi yo'q (legacy — `archive/freecad-legacy` tegida)."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git yo'q")
    gone = [
        "desktop/blender/sath/fc_engine.py", "desktop/blender/sath/wb", "desktop/GesWorkbench", "desktop/blender/spike",
        "desktop/build/sync_fork.py", "desktop/build/build_portable.py", "desktop/tests/test_freecad_cad.py",
    ]  # fmt: skip
    tracked = subprocess.run(["git", "ls-files", *gone], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert tracked.strip() == "", tracked
    for py in (ROOT / "desktop" / "blender" / "sath").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "import FreeCAD" not in src and "fc_engine" not in src, py
```
(`pytest` fayl boshida import qilinmagan bo'lsa — `import pytest` qo'shing.)
- `test_package_names_distinct_and_product_in_build_info` o'rniga:
```python
def test_package_name_and_product_in_build_info():
    """CODE-03: Blender bundle nomi va build metama'lumotidagi product (legacy FreeCAD paketi arxivlangan)."""
    import build_blender_bundle as bb

    assert bb.artifact_name("0.3.0") == "Sath-Blender-0.3.0-Windows-x86_64"
    assert bb.build_info("0.3.0")["product"] == "sath-blender"
```
`test_server_client.py`: `sys.path.insert(0, str(ROOT / "desktop" / "GesWorkbench"))` → `sys.path.insert(0, str(ROOT / "common"))`; `from ges_workbench.server_client import GesClient, ServerError` → `from sath_common.server_client import GesClient, ServerError`.
`server/tests/test_ifc43.py::test_desktop_class_list_matches_server`: `sys.path.insert(0, str(ROOT / "common"))`, `from sath_common import ifc_classes`.

- [ ] **Step 9: Qoldiq havolalar yo'q**

Run: `git grep -n -i "fc_engine\|GES_FC_HOME\|fc-py313\|GesWorkbench\|ges_workbench\|sync_fork\|build_portable" -- . ':!docs' ':!desktop/tests/gen_fc_golden.py' ':!desktop/blender/README.md' ':!desktop/README.md'`
Expected: bo'sh (README lar Task 10 da; `docs/` — tarixiy reja/spec lar).

- [ ] **Step 10: To'liq tekshiruv**

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m ruff check server sim desktop common
.venv\Scripts\python.exe -m pytest -q desktop/tests
.venv\Scripts\python.exe -m pytest -q server/tests/test_ifc43.py
$env:SATH_REQUIRE_NO_SKIP="1"; .\desktop\tests\run_blender_tests.ps1; Remove-Item Env:SATH_REQUIRE_NO_SKIP
```
Expected: sinxron; ruff toza; pytest failed 0; `FAIL soni: 0 · SKIP: 0`, exit 0.

- [ ] **Step 11: Bundle FreeCAD siz**

```powershell
.venv\Scripts\python.exe desktop/build/build_blender_bundle.py --no-zip
Test-Path desktop\build\_work\sath-bundle\Sath\freecad
"{0:N0} MB" -f ((Get-ChildItem desktop\build\_work\sath-bundle\Sath -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
& desktop\build\_work\sath-bundle\Sath\blender.exe -b --python-expr "import bpy; [bpy.ops.preferences.addon_enable(module=m) for m in ('bl_ext.user_default.bonsai', 'bl_ext.user_default.sath')]; print('BUNDLE_GES', bpy.ops.sath.add_object(kind='GES_Generator'), len(bpy.context.active_object.data.polygons))" 2>&1 | Select-String "BUNDLE_GES|Error"
```
Expected: «FreeCAD dvigatel nusxalanmoqda» chiqmaydi; `False`; hajm (yozib qo'ying — Task 10 README ga); `BUNDLE_GES {'FINISHED'} <N>`, N > 0 (generator default mesh — 1148 uchburchak; Bonsai representation dan qayta yuklasa son farq qilishi mumkin).

- [ ] **Step 12: Commit**

```bash
git add -A desktop/blender/sath desktop/build desktop/tests .github/workflows/ci.yml server/tests/test_ifc43.py ruff.toml
git commit -m "chore(K1): FreeCAD desktopdan olib tashlandi — fc_engine, sath/wb, FreeCAD DXF importeri, prefs papkasi, bundle freecad/; GesWorkbench, fork/portable quvuri, FreeCAD testlari va spike archive/freecad-legacy tegida; CI da SKIP taqiqlangan" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: K2 — `Pset_SathParametric`, `restore_from_ifc()`, `TwinBindingError`

**Model:** sonnet — Bonsai yuklash oqimi bilan integratsiya va headless round-trip testi.

**Files:**
- Modify (CRLF): `desktop/blender/sath/ifc.py` (`write_psets` — `text`)
- Modify (CRLF): `desktop/blender/sath/ges_objects.py` (parametrik pset yozish, `RestoreReport`, `restore_from_ifc`, `ifc.loaded` obunasi, `sath.restore_ges`)
- Modify (CRLF): `desktop/blender/sath/sim_anim.py` (`TwinBindingError`, `_bound`), `desktop/blender/sath/ops_sim.py` (`wait_job.apply`)
- Create: `desktop/tests/sath_tests/roundtrip_ges.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`roundtrip_ges`)

**Interfaces:**
- Consumes: `ges_kinds.parametric_pset/from_psets/infer_roles/UnknownKind` (Task 3), `core.events.subscribe` (P1), `ifc.load` → `ifc.loaded`.
- Produces: `ifc.write_psets(e, psets, text=())`; `ges_objects.RestoreReport(restored, inferred, unknown, warnings)` + `.text()`, `ges_objects.LAST_REPORT`, `ges_objects.restore_from_ifc() -> RestoreReport`, operator `sath.restore_ges`; `sim_anim.TwinBindingError(RuntimeError)`. Task 9 `write_ifc` va `restore_from_ifc` ni o'zgartirmasdan ishlatadi.

- [ ] **Step 1: Headless test** — `desktop/tests/sath_tests/roundtrip_ges.py`

```python
"""K2: namuna GES → IFC saqlash → yangi sessiyada ochish → har GES obyekti kind/role/params tiklanadi (mesh qayta
qurilmaydi, GUID saqlanadi) → animate_hydro rollar orqali keyframe qo'yadi; rol yo'qolsa TwinBindingError (jim emas).
Eski model (Pset_SathParametric siz, docs/samples/namuna_ges_v1.ifc): Pset_GES_* dan tur, X bo'yicha rollar."""

import tempfile
from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def _hydro(n: int, guids: list) -> tuple[dict, dict]:
    series = {
        "level": [43.0 - 0.1 * i for i in range(n)], "turbine_flow": [120.0] * n,
        "spill": [0.0] * (n - 1) + [15.0], "head_net": [42.0] * n,
    }  # fmt: skip
    result = {"series": series, "units": [{"power_mw": [0.0] + [20.0] * (n - 1)} for _ in guids]}
    units = [
        {"guid": g, "name": f"Agregat {k}", "type": "Francis", "rated_power_mw": 25.0, "rated_head_m": 42.75}
        for k, g in enumerate(guids, start=1)
    ]
    return result, {"units": units}


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import demo_plant, ges_objects, ifc, sim_anim

    out = demo_plant.build(bpy.context, head_m=45.0, units=2, unit_mw=25.0, zero_m=850.0)
    before = {ifc.guid(o): (o.ges.kind, o.ges.role, ges_objects.params_dict(o)) for o in out.values()}
    assert len(before) == 16 and all(before), before.keys()
    sp = ue.get_psets(ifc.entity(out["gen:1"]))["Pset_SathParametric"]
    assert (sp["Kind"], sp["Role"], sp["SchemaVersion"], sp["Units"]) == ("GES_Generator", "gen:1", 1, "m"), sp
    path = Path(tempfile.gettempdir()) / "sath_roundtrip.ifc"
    ifc.save(path)

    calls: list = []
    orig = ges_objects.rebuild_mesh
    ges_objects.rebuild_mesh = lambda o: calls.append(o.name)  # tiklash mesh ni qayta qurmasligi kerak
    try:
        assert ifc.load(path)  # loyiha ochiq edi → yangi sessiya: Object.ges yo'qoladi, ifc.loaded → restore_from_ifc
    finally:
        ges_objects.rebuild_mesh = orig
    rep = ges_objects.LAST_REPORT
    assert calls == [], calls
    assert len(rep.restored) == 16 and not rep.inferred and not rep.unknown, rep.text()
    for g, (kind, role, params) in before.items():
        o = ifc.object_for_guid(g)
        assert o is not None, g
        assert (o.ges.kind, o.ges.role) == (kind, role), (o.name, o.ges.kind, o.ges.role)
        got = ges_objects.params_dict(o)
        assert got.keys() == params.keys(), o.name
        for k, v in params.items():
            same = abs(got[k] - v) <= 1e-6 * max(1.0, abs(v)) if isinstance(v, float) else got[k] == v
            assert same, (o.name, k, got[k], v)

    result, params = _hydro(6, [ifc.guid(ges_objects.by_role(f"unit:{k}")) for k in (1, 2)])
    assert sim_anim.animate_hydro(bpy.context, result, params, zero_m=850.0) == 6
    gen = ges_objects.by_role("gen:1")
    cf = [f for f in sim_anim._fcurves(gen) if f.data_path == "color"]
    assert cf and len(cf[0].keyframe_points) == 6, "generator rangi keyframe lari yo'q"
    gen.ges.role = ""  # rol yo'qolsa — jim emas
    try:
        sim_anim.animate_hydro(bpy.context, result, params, zero_m=850.0)
        raise AssertionError("TwinBindingError kutilgan")
    except sim_anim.TwinBindingError as e:
        assert "gen:1" in str(e), e
    gen.ges.role = "gen:1"

    assert ifc.load(SAMPLE)  # eski model: faqat Pset_GES_* (FreeCAD davri)
    rep = ges_objects.LAST_REPORT
    assert len(rep.inferred) == 7 and not rep.restored and not rep.unknown, rep.text()
    assert ifc.entity(ges_objects.by_role("unit:1")).Name == "Turbina 1"
    assert ifc.entity(ges_objects.by_role("penstock:3")).Name == "Bosimli quvur 3"
    p = ges_objects.params_dict(ges_objects.by_role("dam"))
    assert (p["Height"], p["Length"], p["DamType"]) == (20.0, 60.0, "Gravitatsion"), p
    path.unlink(missing_ok=True)
    print("ROUNDTRIP:", rep.text(), flush=True)
```

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test roundtrip_ges --bonsai 2>&1 | Select-String "OK|FAIL|Error|assert"` → `[FAIL] roundtrip_ges` (`KeyError: 'Pset_SathParametric'`).

- [ ] **Step 2: `ifc.write_psets`** (CRLF)

```python
def write_psets(e, psets: dict[str, dict], text: tuple[str, ...] = ()) -> None:
    """{pset: {name: value}} → IfcPropertySet lar (mavjud bo'lsa yangilanadi). `text` dagi nomlar IfcText bo'lib
    yoziladi — IfcLabel 255 belgi bilan cheklangan (K2: Pset_SathParametric.Params JSON)."""
    import ifcopenshell.api.pset as api
    import ifcopenshell.util.element as ue

    f = file()
    existing = ue.get_psets(e)
    for name, values in psets.items():
        if name in existing:
            ps = f.by_id(existing[name]["id"])
        else:
            ps = api.add_pset(f, product=e, name=name)
        props = {k: (f.create_entity("IfcText", v) if k in text and isinstance(v, str) else v) for k, v in values.items()}
        api.edit_pset(f, pset=ps, properties=props)
```

- [ ] **Step 3: `ges_objects.py`** (CRLF)

Importlar:
```python
import os
from dataclasses import dataclass, field

import bpy
import numpy as np

from . import ifc
from .core import events, ui_tasks
from .shared import ges_kinds
```

`write_ifc` ni almashtiring:
```python
def write_ifc(obj) -> None:
    """IFC element (yo'q bo'lsa assign_class) yoki representation + Pset_GES_* + Pset_SathParametric (K2: tur, rol,
    barcha parametrlar — qayta ochilganda to'liq tiklanadi)."""
    g = obj.ges
    p = params_dict(obj)
    ps = {**ges_kinds.psets(g.kind, p), **ges_kinds.parametric_pset(g.kind, g.role, p)}
    e = ifc.entity(obj)
    if e is None:
        e = ifc.assign_class(obj, ges_kinds.spec(g.kind).ifc_class)
    else:
        ifc.update_representation(obj)
    ifc.write_psets(e, ps, text=("Params",))
```

`add()` dan keyin:
```python
@dataclass
class RestoreReport:
    restored: list[str] = field(default_factory=list)  # Pset_SathParametric dan (to'liq)
    inferred: list[str] = field(default_factory=list)  # Pset_GES_* dan (geometriya parametrlari qisman, rol taxminiy)
    unknown: list[tuple[str, str]] = field(default_factory=list)  # (obyekt, sabab)
    warnings: list[str] = field(default_factory=list)

    def text(self) -> str:
        s = f"GES: {len(self.restored)} tiklandi, {len(self.inferred)} taxminiy, {len(self.unknown)} noma'lum"
        if self.unknown:
            s += " — " + "; ".join(f"{n}: {why}" for n, why in self.unknown[:3])
        return s


LAST_REPORT = RestoreReport()


def _set_role(obj, role: str) -> None:
    g = obj.ges
    g.busy = True  # K4: rol o'zgarishi «ifc_dirty» qo'ymasin (tiklash IFC ni o'zgartirmaydi)
    try:
        g.role = role
    finally:
        g.busy = False


def restore_from_ifc() -> RestoreReport:
    """K2: IFC elementli obyektlar → obj.ges (kind, role, params) Pset_SathParametric dan, bo'lmasa Pset_GES_* dan
    (rollar X bo'yicha). Mesh qayta QURILMAYDI — GUID va geometriya IFC dagidek qoladi; tanilmaganlar hisobotda."""
    import ifcopenshell.util.element as ue

    global LAST_REPORT
    rep = RestoreReport()
    guess = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or getattr(obj, "ges", None) is None:
            continue
        e = ifc.entity(obj)
        if e is None:
            continue
        try:
            r = ges_kinds.from_psets(ue.get_psets(e))
        except ges_kinds.UnknownKind as err:
            rep.unknown.append((obj.name, str(err)))
            continue
        if r is None:
            continue
        _fill_schema(obj, r.kind, r.params)
        _set_role(obj, r.role)
        obj.color = (*ges_kinds.spec(r.kind).color, 1.0)
        rep.warnings += [f"{obj.name}: {w}" for w in r.warnings]
        if r.source == "parametric":
            rep.restored.append(obj.name)
        else:
            rep.inferred.append(obj.name)
            guess.append((obj.name, r.kind, obj.matrix_world.translation.x))
    if guess:
        taken = {o.ges.role for o in by_kind_all() if o.ges.role}
        for name, role in ges_kinds.infer_roles(guess).items():
            if role not in taken:
                _set_role(bpy.data.objects[name], role)
    LAST_REPORT = rep
    return rep


def _on_ifc_loaded(payload: dict) -> None:
    rep = restore_from_ifc()
    if rep.unknown or rep.warnings:
        ui_tasks.show_error("GES tiklash", rep.text() + ("; " + "; ".join(rep.warnings[:3]) if rep.warnings else ""))
    elif rep.restored or rep.inferred:
        ui_tasks.status(rep.text())


class SATH_OT_restore_ges(bpy.types.Operator):
    """GES obyektlarining tur, rol va parametrlarini IFC psetlaridan qayta tiklash (mesh o'zgarmaydi)"""

    bl_idname = "sath.restore_ges"
    bl_label = "IFC dan tiklash"

    def execute(self, context):
        rep = restore_from_ifc()
        self.report({"WARNING"} if rep.unknown else {"INFO"}, rep.text())
        return {"FINISHED"}
```

Panelda (`SATH_PT_objects.draw`, `grid` dan keyin): `lay.operator("sath.restore_ges", icon="FILE_REFRESH")`. `CLASSES` ga `SATH_OT_restore_ges` qo'shing. register/unregister:
```python
_off_loaded = None


def register():
    global _off_loaded
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi (ui.py bilan bir xil)
        SATH_PT_objects.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)
    _off_loaded = events.subscribe("ifc.loaded", _on_ifc_loaded)


def unregister():
    global _off_loaded
    if _off_loaded is not None:
        _off_loaded()
        _off_loaded = None
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 4: `sim_anim.py`** (CRLF) — `SIM_COLL`/`BASE_LOC` dan keyin:

```python
ROLE_KIND = {s.role: k for k, s in ges_objects.ges_kinds.KINDS.items()}  # "dam" → GES_Dam, "unit:" → GES_Turbine


class TwinBindingError(RuntimeError):
    """Egizak bog'lanmadi: modelda shu turdagi obyekt bor, lekin animatsiya uchun kerakli rol topilmadi (K2 — avval
    `if o is not None` bilan jim o'tkazib yuborilardi)."""


def _bound(role: str | None, kind: str, owner: str = ""):
    """Rol bo'yicha obyekt. Modelda `kind` turidagi obyekt bor-u, rol topilmasa — TwinBindingError; bu turdagi obyekt
    umuman yo'q bo'lsa — None (masalan transformatorsiz model)."""
    o = ges_objects.by_role(role) if role else None
    if o is None and ges_objects.by_kind(kind):
        who = f"«{owner}» uchun " if owner else ""
        raise TwinBindingError(
            f"Egizak: {who}'{role or '?'}' roli topilmadi, lekin modelda {ges_objects.KIND_LABEL[kind]} bor — "
            "rollar tiklanmagan (Sath → GES obyektlari → «IFC dan tiklash»)"
        )
    return o
```

`animate_hydro`: `tailrace = ges_objects.by_role("tailrace")` → `tailrace = _bound("tailrace", "GES_Tailrace")`; agregat sikli boshini almashtiring:
```python
    for k, u in enumerate(units):
        if k >= len(unit_series):
            continue
        g = u.get("guid") or ""
        obj = ifc.object_for_guid(g) if g else None
        if obj is None:
            raise TwinBindingError(f"Egizak: agregat «{u.get('name') or k + 1}» (GUID {g or '—'}) modelda topilmadi")
        obj.animation_data_clear()
        rated = float(u.get("rated_power_mw") or 0) or 1.0
        idx = _role_index(obj)
        gen = _bound(f"gen:{idx}" if idx else None, "GES_Generator", obj.name)
        tf = _bound(f"transformer:{idx}" if idx else None, "GES_Transformer", obj.name)
        draft = _bound(f"draft:{idx}" if idx else None, "GES_DraftTube", obj.name)
```
(keyingi `for o in (gen, tf, draft): …` va davomi o'zgarmaydi.) `animate_governor`: `u = ges_objects.by_role(f"unit:{k}") if k else None` → `u = _bound(f"unit:{k}" if k else None, "GES_Turbine", g.name)`. `animate_seismic` sikli:
```python
        objs = _objects_for(roles)
        if not objs:
            if any(ges_objects.by_kind(ROLE_KIND[r]) for r in roles if r in ROLE_KIND):
                raise TwinBindingError(f"Egizak: «{st.get('name', '')}» uchun rollar ({', '.join(roles)}) topilmadi")
            continue
        for o in objs:
```
(`for o in _objects_for(roles):` o'rniga; `sa, T, c` hisoblari `objs` dan oldin qoladi.) `ges_objects.ges_kinds` — `ges_objects.py` dagi `from .shared import ges_kinds` (alohida import kerak emas).

`ops_sim.wait_job.apply` (CRLF): `on_done(result)` atrofidagi `try` ga Exception dan oldin:
```python
            except sim_anim.TwinBindingError as e:  # K2: rol bog'lanmadi — natija bor, egizak sababi aniq
                s.sim_status = f"Tayyor, lekin egizak bog'lanmadi: {e}"
```

- [ ] **Step 5: Ro'yxat va testlar**

`run_blender_tests.ps1`: `@("demo_plant", "--bonsai")` dan keyin `@("roundtrip_ges", "--bonsai")`.

```powershell
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test roundtrip_ges --bonsai 2>&1 | Select-String "\[OK\]|\[FAIL\]|ROUNDTRIP|Error"
.\desktop\tests\run_blender_tests.ps1
.venv\Scripts\python.exe -m ruff check desktop
```
Expected: `ROUNDTRIP: GES: 0 tiklandi, 7 taxminiy, 0 noma'lum`, `[OK] roundtrip_ges`; `FAIL soni: 0 · SKIP: 0` (20 test); ruff toza. Server bilan (`$env:GES_TEST_SERVER`): `sim_hydro`, `sim_twin` OK (rolsiz agregatlar va generatorsiz model — xato yo'q).

- [ ] **Step 6: Commit**

```bash
git add desktop/blender/sath/ifc.py desktop/blender/sath/ges_objects.py desktop/blender/sath/sim_anim.py desktop/blender/sath/ops_sim.py desktop/tests/sath_tests/roundtrip_ges.py desktop/tests/run_blender_tests.ps1
git commit -m "fix(K2): GES obyektlari qayta ochilganda tur/rol/parametrlarni tiklaydi — Pset_SathParametric (IfcText JSON), eski modellarda Pset_GES_* dan teskari xaritalash va X bo'yicha rollar; mesh qayta qurilmaydi; rol yo'q bo'lsa TwinBindingError" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: K4 — `IfcOperator`, `sath.sync_ifc` + `ifc_dirty`, yetim entitylar

**Model:** opus — Bonsai IfcStore tranzaksiyalari, Blender undo bilan sinxronlik va batch o'chirish yamog'i ichma-ich ishlashi.

Bonsai 0.9.0 API (o'rnatilgan `bonsai/bim/ifc.py:389-497`, `tool/ifc.py:400-421` da tekshirilgan): `IfcStore.execute_ifc_operator(operator, context)` — yuqori darajada `ifc_file.begin_transaction()`, `_execute(context)`, `end_transaction()` + `IfcStore.add_transaction_operation(rollback=UNDO, commit=REDO)`, natija `_execute` qaytargani; istisno bo'lsa (IFC o'zgargan bo'lsa) `bpy.ops.ed.undo_push("Recover …")` va qayta `raise`. Ichma-ich `bim.*` operatorlari shu tranzaksiyaga qo'shiladi. `handler.undo_post` → `IfcStore.undo(until_key=props.last_transaction)`. `tool.Ifc.Operator.execute` `@final` va doim `{"FINISHED"}` — shuning uchun mixin uni meros qilmaydi, shartnomasini (`transaction_key`, `transaction_data`, `_execute`) takrorlaydi va natijani qaytaradi. `bim.create_project` esa `tool.Ifc.Operator` EMAS (`bonsai/bim/module/project/operator.py:137-150`: o'zi `IfcStore.begin_transaction` qiladi) — tranzaksiya ichida chaqirilsa joriy kalitni bosib ketadi; shuning uchun mixin `ifc.ensure_project()` ni tranzaksiyadan OLDIN chaqiradi (va bu `undo_ifc` dagi `key0` ni bo'sh qilmaydi).

**Files:**
- Create: `desktop/blender/sath/core/ifc_ops.py`
- Modify (CRLF): `desktop/blender/sath/ges_objects.py`, `desktop/blender/sath/demo_plant.py`, `desktop/blender/sath/ifc.py`
- Modify: `desktop/blender/sath/ops_import.py`, `desktop/blender/sath/ops_server.py`, `desktop/blender/sath/flows.py` (mixed — mavjud qatorlarga tegmang)
- Create: `desktop/tests/sath_tests/undo_ifc.py`
- Modify: `desktop/tests/sath_tests/objects.py`, `desktop/tests/test_sath_pure.py`, `desktop/tests/run_blender_tests.ps1`

**Interfaces:**
- Consumes: `ges_objects.write_ifc/restore_from_ifc` (Task 8).
- Produces: `core.ifc_ops.IfcOperator` (mixin; `_execute`, `sath_needs_project`), `SathOpError`, `last_key()`, `undo_to(key)`, `rebuild_maps()`; `ges_objects.GesObject.ifc_dirty`, `dirty_objects()`, `sync_ifc(objs=None) -> int`; operatorlar `sath.sync_ifc`, `sath.purge_orphans`, `sath.assign_ifc(names)`; `ifc.orphans() -> list[{"id","class","name","reason"}]`, `ifc.purge_orphans() -> int`; `flows.orphans_text(items) -> str`. P3 (`api.ifc.IfcOperator`) shuni qayta eksport qiladi.

- [ ] **Step 1: Headless test** — `desktop/tests/sath_tests/undo_ifc.py`

```python
"""K4: GES obyekt qo'shish, parametr sinxroni va «Namuna GES» — har biri bitta IFC tranzaksiyasi (Blender undo
qadami); orqaga qaytarilgach yetim entity qolmaydi (`ifc.orphans() == []`). Headless da Blender undo steki yo'q —
`ifc_ops.undo_to` (GUI da Ctrl+Z dan keyin Bonsai undo_post aynan IfcStore.undo ni chaqiradi) + yaratilgan Blender
obyektlarini o'chirish (Blender undo emulyatsiyasi). Qo'lda o'chirilgan obyektning IFC elementi — purge_orphans."""

import bpy


def _counts(f) -> tuple:
    return tuple(len(f.by_type(t)) for t in ("IfcElement", "IfcPropertySet", "IfcShapeRepresentation"))


def _undo(key: str, created: set) -> None:
    from sath.core import ifc_ops

    ifc_ops.undo_to(key)
    for n in created:
        o = bpy.data.objects.get(n)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)
    ifc_ops.rebuild_maps()


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import ges_objects, ifc
    from sath.core import ifc_ops

    ifc.ensure_project()
    f = ifc.file()
    base = _counts(f)
    assert ifc.orphans() == [], ifc.orphans()

    # 1) qo'shish → orqaga: element, psetlar, representation qolmaydi
    key0, names0 = ifc_ops.last_key(), set(bpy.data.objects.keys())
    assert key0, "ensure_project tranzaksiyasi kaliti bo'sh"
    assert bpy.ops.sath.add_object(kind="GES_Spillway") == {"FINISHED"}
    sp = bpy.context.view_layer.objects.active
    ps = ue.get_psets(ifc.entity(sp))
    assert "Pset_GES_Spillway" in ps and ps["Pset_SathParametric"]["Kind"] == "GES_Spillway", ps.keys()
    assert ifc_ops.last_key() != key0, "add_object IFC tranzaksiyasi yozilmadi"
    _undo(key0, set(bpy.data.objects.keys()) - names0)
    assert ifc.orphans() == [], ifc.orphans()
    assert _counts(f) == base, (_counts(f), base)

    # 2) Blender obyekti qo'lda o'chirildi, IFC qoldi → orphans topadi, purge tozalaydi
    assert bpy.ops.sath.add_object(kind="GES_Dam") == {"FINISHED"}
    bpy.data.objects.remove(bpy.context.view_layer.objects.active, do_unlink=True)
    ifc_ops.rebuild_maps()
    orph = ifc.orphans()
    assert any(o["class"] == "IfcWall" for o in orph), orph
    assert bpy.ops.sath.purge_orphans() == {"FINISHED"}
    assert ifc.orphans() == [] and _counts(f) == base, (ifc.orphans(), _counts(f), base)

    # 3) parametr → faqat mesh + dirty; sync_ifc → IFC; orqaga → eski pset, yetim representation yo'q
    assert bpy.ops.sath.add_object(kind="GES_Tailrace") == {"FINISHED"}
    tr = bpy.context.view_layer.objects.active
    after3 = _counts(f)
    next(p for p in tr.ges.params if p.name == "Depth").value_float = 9.0
    assert tr.ges.ifc_dirty and abs(tr.dimensions.z - 9.8) < 1e-3, tr.dimensions.z  # Depth + WallThickness
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 6.0  # IFC hali yozilmagan
    key1 = ifc_ops.last_key()
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not tr.ges.ifc_dirty
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 9.0
    _undo(key1, set())
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 6.0
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)

    # 4) Namuna GES (16 element, ichki bim.* operatorlari) → bitta qadam bilan orqaga
    key2, names2 = ifc_ops.last_key(), set(bpy.data.objects.keys())
    assert bpy.ops.sath.build_demo_plant() == {"FINISHED"}
    assert len(ges_objects.by_kind_all()) == 17
    _undo(key2, set(bpy.data.objects.keys()) - names2)
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)
    print("UNDO_IFC OK", _counts(f), flush=True)
```

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test undo_ifc --bonsai 2>&1 | Select-String "OK|FAIL|Error"` → `[FAIL] undo_ifc` (`ifc.orphans` yo'q).

- [ ] **Step 2: `core/ifc_ops.py`**

```python
"""K4: IFC o'zgartiradigan Sath operatorlari — Bonsai `tool.Ifc.Operator` shartnomasi ustidan mixin.

Bonsai IFC tranzaksiyalarini o'z tarixida (IfcStore.history) saqlaydi va Blender undo/redo dan keyin `undo_post`
handler orqali shu tarixni orqaga/oldinga suradi. Operator `IfcStore.execute_ifc_operator` orqali bajarilsa,
ichidagi barcha IFC o'zgarishlari (ichki bim.* operatorlari, ifcopenshell.api, ifc.write_psets) bitta tranzaksiya
— Blender ning bitta undo qadami bilan bog'lanadi. Bonsai ichki API faqat shu faylda (spec «Xavflar»); sinalgan:
Bonsai 0.9.0 (`bonsai.bim.ifc.IfcStore.execute_ifc_operator(op, context)` — `_execute` natijasini qaytaradi).
"""

from __future__ import annotations

import bpy


class SathOpError(RuntimeError):
    """Kutilgan foydalanuvchi xatosi: operator xabar beradi va {"CANCELLED"} qaytaradi (traceback siz)."""


def _store():
    """Bonsai IfcStore yoki None (Bonsai yoqilmagan — masalan `--bonsai` siz headless test)."""
    if not hasattr(bpy.types.Scene, "BIMProperties"):
        return None
    try:
        from bonsai.bim.ifc import IfcStore
    except ImportError:
        return None
    return IfcStore


class IfcOperator:
    """Mixin: `class SATH_OT_x(IfcOperator, bpy.types.Operator)`, ish `_execute(context)` da (execute emas).

    - `bl_options = {"REGISTER", "UNDO"}` — IFC tranzaksiyasi Blender undo qadami bilan bog'lanadi.
    - `sath_needs_project` (True) — tranzaksiyadan OLDIN `ifc.ensure_project()` (yangi loyiha o'z undo qadami;
      tranzaksiya o'rtasida fayl yaratilmaydi). Import kabi operatorlarda property bilan shartli qilinadi.
    - `_execute` xatoda istisno (`SathOpError` — kutilgan) ko'taradi, {"CANCELLED"} QAYTARMAYDI: IFC o'zgargan bo'lsa
      Bonsai «Recover» undo qadamini qo'yadi, biz xabar beramiz. CANCELLED qaytarilsa Blender undo qadami yo'q,
      IfcStore da tranzaksiya bor — tarixlar ajraladi.
    """

    bl_options = {"REGISTER", "UNDO"}
    transaction_key = ""
    transaction_data = None
    sath_needs_project = True

    def execute(self, context):
        from .. import ifc

        store = _store()
        try:
            if store is None:
                return self._execute(context) or {"FINISHED"}
            if self.sath_needs_project:
                ifc.ensure_project()
            return store.execute_ifc_operator(self, context) or {"FINISHED"}
        except SathOpError as e:
            self.report({"ERROR"}, str(e))
        except Exception as e:  # noqa: BLE001 — Blender da traceback o'rniga aniq xabar
            self.report({"ERROR"}, f"{self.bl_label}: {e}")
        return {"CANCELLED"}

    def _execute(self, context):
        raise NotImplementedError


def last_key() -> str:
    """Oxirgi IFC tranzaksiyasi kaliti (Bonsai yo'q — "")."""
    store = _store()
    return store.last_transaction if store is not None else ""


def undo_to(key: str) -> None:
    """Headless testlar uchun: IFC tranzaksiyalarini `key` gacha orqaga. GUI da Ctrl+Z dan keyin Bonsai `undo_post`
    aynan shuni qiladi (`IfcStore.undo(until_key=props.last_transaction)`); `-b` da Blender undo steki yo'q."""
    import bonsai.tool as tool

    store = _store()
    store.undo(until_key=key)
    store.last_transaction = key
    tool.Blender.get_bim_props().last_transaction = key


def rebuild_maps() -> None:
    """Blender obyektlari o'chirilgandan keyin Bonsai element xaritalarini (id/guid → obyekt) yangilash."""
    import bonsai.tool as tool

    tool.Ifc.rebuild_element_maps()
```

- [ ] **Step 3: `ifc.py`** (CRLF) — `sync_placement` dan oldin:

```python
def _alive(o) -> bool:
    try:
        return o is not None and bpy.data.objects.get(o.name) is o
    except ReferenceError:  # o'chirilgan obyekt (Bonsai xaritasi eskirgan)
        return False


def orphans() -> list[dict]:
    """K4: yetim IFC entitylar (commit oldidan; Ctrl+Z dan keyin bo'lmasligi kerak): (1) Blender obyekti yo'q Sath/GES
    elementlari (Pset_SathParametric yoki Pset_GES_* bor; boshqa elementlarga tegilmaydi — Bonsai ularni
    yuklamagan bo'lishi mumkin), (2) hech narsaga bog'lanmagan IfcPropertySet, (3) RelatedObjects bo'sh
    IfcRelDefinesByProperties, (4) hech narsaga kirmagan IfcShapeRepresentation. [{"id","class","name","reason"}]."""
    import ifcopenshell.util.element as ue

    f = file()
    if f is None:
        return []
    tool = _tool()
    out: list[dict] = []

    def add(e, reason: str) -> None:
        out.append({"id": e.id(), "class": e.is_a(), "name": getattr(e, "Name", None) or "", "reason": reason})

    for e in f.by_type("IfcElement"):
        if _alive(tool.Ifc.get_object(e)):
            continue
        names = ue.get_psets(e)
        if "Pset_SathParametric" in names or any(n.startswith("Pset_GES_") for n in names):
            add(e, "Blender obyekti yo'q")
    for ps in f.by_type("IfcPropertySet"):
        if f.get_total_inverses(ps) == 0:
            add(ps, "hech narsaga bog'lanmagan")
    for rel in f.by_type("IfcRelDefinesByProperties"):
        if not rel.RelatedObjects:
            add(rel, "bo'sh bog'lanish")
    for rep in f.by_type("IfcShapeRepresentation"):
        if f.get_total_inverses(rep) == 0:
            add(rep, "hech qaysi shaklga kirmagan")
    return out


def purge_orphans() -> int:
    """orphans() ni o'chiradi (sath.purge_orphans — IfcOperator ichida, undo bilan). 3 o'tish: element o'chirilganda
    uning pset/representation lari ham yetim bo'lib qolishi mumkin."""
    import ifcopenshell.api.geometry
    import ifcopenshell.api.root
    import ifcopenshell.util.element as ue

    f = file()
    n = 0
    for _ in range(3):
        items = orphans()
        if not items:
            break
        for it in items:
            try:
                e = f.by_id(it["id"])
            except RuntimeError:
                continue  # oldingi o'chirish bilan ketgan
            if e.is_a("IfcElement"):
                ifcopenshell.api.root.remove_product(f, product=e)
            elif e.is_a("IfcShapeRepresentation"):
                ifcopenshell.api.geometry.remove_representation(f, representation=e)
            elif e.is_a("IfcRelDefinesByProperties"):
                f.remove(e)
            else:
                ue.remove_deep2(f, e)
            n += 1
    return n
```

- [ ] **Step 4: `ges_objects.py`** (CRLF)

Importga `from .core.ifc_ops import IfcOperator`. `flush_pending` va `_changed` ni almashtiring, `_role_changed` qo'shing (GesParam dan oldin):
```python
def flush_pending():
    """Kechiktirilgan mesh qayta qurish (timer yoki darhol): FAQAT mesh — IFC ga yozish `sath.sync_ifc` da (K4: timer
    ichida bpy.ops/IFC tranzaksiyasi yo'q). Xatolar holat qatori va popup da (avval print ga yutilardi)."""
    names = sorted(_pending)
    _pending.clear()
    errors = []
    for n in names:
        obj = bpy.data.objects.get(n)
        if obj is not None and obj.ges.kind:
            try:
                rebuild_mesh(obj)
            except Exception as e:  # noqa: BLE001 — bitta obyekt xatosi qolganini to'xtatmasin
                errors.append(f"{n}: {e}")
    if errors:
        ui_tasks.show_error("GES qayta qurish", "; ".join(errors))
    return None


def _changed(self, context):
    obj = self.id_data
    if getattr(obj, "ges", None) is None or not obj.ges.kind or obj.ges.busy:
        return
    obj.ges.ifc_dirty = True
    _pending.add(obj.name)
    if bpy.app.background:  # testlar: darhol
        flush_pending()
        return
    if not bpy.app.timers.is_registered(flush_pending):
        bpy.app.timers.register(flush_pending, first_interval=DEBOUNCE)


def _role_changed(self, context):
    if self.kind and not self.busy:
        self.ifc_dirty = True  # rol Pset_SathParametric da — keyingi sync_ifc yozadi
```
`GesObject`:
```python
class GesObject(bpy.types.PropertyGroup):
    kind: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty(default=False)
    role: bpy.props.StringProperty(
        description="Egizakdagi roli: unit:1, gen:1, draft:1, penstock:1, dam, tailrace…", update=_role_changed
    )
    ifc_dirty: bpy.props.BoolProperty(default=False, description="Parametrlar IFC ga yozilmagan (sath.sync_ifc)")
    params: bpy.props.CollectionProperty(type=GesParam)
```
`set_params` oxiri: `rebuild(obj)` → `rebuild_mesh(obj)` va `obj.ges.ifc_dirty = True`. `write_ifc` oxiriga `g.ifc_dirty = False`. `rebuild()` dan keyin:
```python
def dirty_objects() -> list:
    return [o for o in by_kind_all() if o.ges.ifc_dirty]


def sync_ifc(objs=None) -> int:
    """Kechiktirilgan mesh larni qurib, IFC bilan sinxronlanmagan (yoki berilgan) GES obyektlarini IFC ga yozadi.
    IfcOperator ichida chaqiriladi (sath.sync_ifc, sath.rebuild_object, commit) — bitta undo qadami."""
    flush_pending()
    todo = dirty_objects() if objs is None else list(objs)
    for o in todo:
        write_ifc(o)
    return len(todo)
```
Operatorlar (`SATH_OT_add_object`, `SATH_OT_rebuild_object` o'rniga + yangilari):
```python
class SATH_OT_add_object(IfcOperator, bpy.types.Operator):
    """GES obyekti qo'shish (sof Python geometriya, IFC element + Pset_GES_*; bitta undo qadami)"""

    bl_idname = "sath.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    def _execute(self, context):
        obj = add(context, self.kind)
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"{KIND_LABEL[self.kind]} qo'shildi")
        return {"FINISHED"}


class SATH_OT_rebuild_object(IfcOperator, bpy.types.Operator):
    """Tanlangan GES obyektlarini qayta hisoblash va IFC ga yozish"""

    bl_idname = "sath.rebuild_object"
    bl_label = "Qayta qurish"
    bl_options = {"REGISTER", "UNDO"}

    def _execute(self, context):
        objs = [o for o in context.view_layer.objects if o.select_get() and o.ges.kind]
        for o in objs:
            rebuild_mesh(o)
        sync_ifc(objs)
        self.report({"INFO"}, f"{len(objs)} obyekt qayta qurildi")
        return {"FINISHED"}


class SATH_OT_sync_ifc(IfcOperator, bpy.types.Operator):
    """Parametrlari o'zgargan GES obyektlarini IFC ga yozish (representation, Pset_GES_*, Pset_SathParametric)"""

    bl_idname = "sath.sync_ifc"
    bl_label = "IFC ga qo'llash"
    bl_options = {"REGISTER", "UNDO"}
    sath_needs_project = False

    def _execute(self, context):
        n = sync_ifc()
        self.report({"INFO"}, f"{n} obyekt IFC ga yozildi" if n else "IFC sinxron")
        return {"FINISHED"}


class SATH_OT_purge_orphans(IfcOperator, bpy.types.Operator):
    """IFC dagi yetim entitylarni o'chirish (Blender obyekti yo'q GES elementlari, bog'lanmagan pset/representation)"""

    bl_idname = "sath.purge_orphans"
    bl_label = "Yetim IFC entitylarni o'chirish"
    bl_options = {"REGISTER", "UNDO"}
    sath_needs_project = False

    def _execute(self, context):
        n = ifc.purge_orphans()
        self.report({"INFO"}, f"{n} yetim entity o'chirildi")
        return {"FINISHED"}
```
Panel (`grid` dan keyin, `restore_ges` tugmasidan oldin):
```python
        n_dirty = len(dirty_objects())
        if n_dirty:
            row = lay.row(align=True)
            row.label(text=f"{n_dirty} obyekt IFC bilan sinxronlanmagan", icon="ERROR")
            row.operator("sath.sync_ifc", text="IFC ga qo'llash", icon="EXPORT")
```
`CLASSES = (GesParam, GesObject, SATH_OT_add_object, SATH_OT_rebuild_object, SATH_OT_sync_ifc, SATH_OT_purge_orphans, SATH_OT_restore_ges, SATH_PT_objects)`.

- [ ] **Step 5: `demo_plant.py`** (CRLF)

`from .core.ifc_ops import IfcOperator`; operator:
```python
class SATH_OT_build_demo_plant(IfcOperator, bpy.types.Operator):
    """Rasmdagi GES (9 komponent) egizagini qurish: to'g'on, suv qabul, egri bosh quvurlar, turbina+generator,
    chiqarish quvuri, kanal, zal, transformatorlar, boshqaruv xonasi, tashlama; IFC + Pset_GES_* (bitta undo qadami)"""

    bl_idname = "sath.build_demo_plant"
    bl_label = "Namuna GES qurish"
    bl_options = {"REGISTER", "UNDO"}

    def _execute(self, context):
        s = context.scene.ges
        out = build(context, s.demo_head, s.demo_units, s.demo_unit_mw, s.hydro_zero)
        frame_view(context)
        s.twin_note = f"{len(out)} obyekt: {s.demo_units} agregat, H = {s.demo_head:.0f} m"
        self.report({"INFO"}, s.twin_note)
        return {"FINISHED"}
```

- [ ] **Step 6: `ops_import.py`** — import va «assign» bitta undo qadami

`from .core.ifc_ops import IfcOperator, SathOpError`. `SATH_OT_import_dxf(IfcOperator, bpy.types.Operator, ImportHelper)` va `SATH_OT_import_mesh(IfcOperator, bpy.types.Operator, ImportHelper)`: `bl_options = {"REGISTER", "UNDO"}`;
```python
    @property
    def sath_needs_project(self):
        return bool(self.assign_ifc)  # IFC ga aylantirilmasa loyiha yaratilmaydi
```
`execute` → `_execute`; ichidagi `except … return {"CANCELLED"}` lar o'rniga `raise SathOpError(...) from e` (import_dxf: `f"Import xatosi: {e}"`; import_mesh ImportError: `str(e) or "assimp-py o'rnatilmagan (extension wheel)"`, boshqa: `f"Import xatosi: {e}"`). Yangi operator (`CLASSES` ga qo'shing):
```python
class SATH_OT_assign_ifc(IfcOperator, bpy.types.Operator):
    """Nomlari berilgan mesh obyektlarni IFC elementga aylantirish (bitta undo qadami)"""

    bl_idname = "sath.assign_ifc"
    bl_label = "IFC ga qo'shish"
    bl_options = {"REGISTER", "UNDO"}
    names: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def _execute(self, context):
        objs = [bpy.data.objects[n] for n in self.names.split(";") if n in bpy.data.objects]
        n = assign_imported(objs)
        self.report({"INFO"}, f"{n} obyekt IFC ga qo'shildi")
        return {"FINISHED"}
```

- [ ] **Step 7: Commit dialogi** — `flows.py` (oxiriga) va `ops_server.py`

```python
def orphans_text(items: list[dict], limit: int = 3) -> str:
    """K4: commit dialogi uchun — «Yetim IFC entitylar: 3 (IfcPropertySet ×2, IfcWall ×1)»; bo'sh — ""."""
    if not items:
        return ""
    counts: dict[str, int] = {}
    for it in items:
        counts[it["class"]] = counts.get(it["class"], 0) + 1
    parts = [f"{c} ×{n}" for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    head = ", ".join(parts[:limit]) + (f" … (+{len(parts) - limit})" if len(parts) > limit else "")
    return f"Yetim IFC entitylar: {len(items)} ({head})"
```
`test_sath_pure.py` (flows importidan keyin):
```python
def test_orphans_text():
    assert flows.orphans_text([]) == ""
    items = [{"class": "IfcPropertySet"}, {"class": "IfcWall"}, {"class": "IfcPropertySet"}]
    assert flows.orphans_text(items) == "Yetim IFC entitylar: 3 (IfcPropertySet ×2, IfcWall ×1)"
```
`SATH_OT_commit`: xususiyatlar —
```python
    purge_orphans: bpy.props.BoolProperty(
        name="Yetim IFC entitylarni o'chirish",
        description="Blender obyekti yo'q GES elementlari va bog'lanmagan pset/representation commit ga kirmasin",
        default=True,
        options={"SKIP_SAVE"},
    )
    orphan_note: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
```
`invoke` da `self.unassigned_note = …` dan keyin `self.orphan_note = flows.orphans_text(ifc.orphans())`; `draw` oxiriga:
```python
        if self.orphan_note:
            box = self.layout.box()
            box.label(text=self.orphan_note, icon="ORPHAN_DATA")
            box.prop(self, "purge_orphans")
```
`execute` dagi `try` bloki boshini almashtiring (`ges_objects.flush_pending()` va `assign_imported` chaqiruvi o'rniga):
```python
        try:  # bpy qismi (IFC ga yozish) — asosiy oqimda, yuborishdan oldin
            bpy.ops.sath.sync_ifc()  # K4: kechiktirilgan/sinxronlanmagan GES o'zgarishlari IFC ga (o'z undo qadami)
            if self.assign_missing:
                bpy.ops.sath.assign_ifc(names=";".join(unassigned(context)))
            if self.purge_orphans and ifc.orphans():
                bpy.ops.sath.purge_orphans()
            ifc.stamp_guids()  # sath_guid — Blender dan FBX/glTF eksportida GUID saqlansin (CAD-07)
```
(`from . import ges_objects` importi endi kerak emas — olib tashlang.)

- [ ] **Step 8: `objects.py` testi** — parametr o'zgarishi qismini almashtiring:

```python
    h.value_float = 35.0  # update callback → faqat mesh + ifc_dirty (K4)
    bpy.context.view_layer.update()
    assert abs(dam.dimensions.z - 35.0) < 1e-3, dam.dimensions.z
    assert dam.ges.ifc_dirty and ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 20.0
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not dam.ges.ifc_dirty
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    t = next(p for p in dam.ges.params if p.name == "DamType")
    assert t.ptype == "enum" and "Arkali" in t.items.split(";")
    t.value_enum = "Arkali"
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"}
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Turi"] == "Arkali"
```
`run_blender_tests.ps1`: `@("undo_rep", "--bonsai")` dan keyin `@("undo_ifc", "--bonsai")`.

- [ ] **Step 9: Tekshiruv**

```powershell
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test undo_ifc --bonsai 2>&1 | Select-String "\[OK\]|\[FAIL\]|UNDO_IFC|Error"
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test undo_rep --bonsai 2>&1 | Select-String "\[OK\]|\[FAIL\]|UNDO_REP"
$env:SATH_REQUIRE_NO_SKIP="1"; .\desktop\tests\run_blender_tests.ps1; Remove-Item Env:SATH_REQUIRE_NO_SKIP
.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_pure.py
.venv\Scripts\python.exe -m ruff check desktop
```
Expected: `UNDO_IFC OK …`, `[OK] undo_ifc`; `undo_rep` OK (batch yamog'i ichma-ich tranzaksiyada ham); `FAIL soni: 0 · SKIP: 0` (21 test); pytest o'tadi; ruff toza. Server bilan (`$env:GES_TEST_SERVER`): `e2e_server`, `commit_conflict`, `sim_twin` OK (commit sync/purge orqali).

Yiqilsa, eng ehtimoliy sabablar: (a) `IfcStore.undo` dan keyin qolgan `IfcPropertySet` — pset tranzaksiyadan tashqarida yozilgan (operator `IfcOperator` emas yoki `ensure_project` tranzaksiya ichida chaqirilgan); (b) `IfcShapeRepresentation` yetim — `update_representation` ichma-ich batch da `_linear_batch_delete` yozuvi; `ifc._record_batch_inverses` ni `undo_rep` dagi kabi kuzating (superpowers:systematic-debugging).

- [ ] **Step 10: Qo'lda (GUI) tekshiruv**

`blender.exe` ni oching (addon + Bonsai), Sath → GES obyektlari → «Suv tashlagich» → Ctrl+Z → Python konsolida `from sath import ifc; ifc.orphans()` → `[]`; Ctrl+Shift+Z → obyekt va IFC elementi qaytadi. To'g'on balandligini sudrab o'zgartiring → «1 obyekt IFC bilan sinxronlanmagan» → «IFC ga qo'llash» → Ctrl+Z → pset avvalgi qiymat. Natijani README «Sinalgan» qatoriga yozing (Task 10).

- [ ] **Step 11: Commit**

```bash
git add desktop/blender/sath/core/ifc_ops.py desktop/blender/sath/ges_objects.py desktop/blender/sath/demo_plant.py desktop/blender/sath/ifc.py desktop/blender/sath/ops_import.py desktop/blender/sath/ops_server.py desktop/blender/sath/flows.py desktop/tests/sath_tests/undo_ifc.py desktop/tests/sath_tests/objects.py desktop/tests/test_sath_pure.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(K4): IFC o'zgarishlari Blender undo bilan bitta qadam — IfcOperator (Bonsai IfcStore tranzaksiyasi), parametr o'zgarishi faqat mesh + ifc_dirty, sath.sync_ifc, yetim entitylar (orphans/purge) commit dialogida, timer xatolari ko'rinadi" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Hujjat va roadmap (K1, K2, K4)

**Model:** haiku — tayyor matnni ko'chirish va commit hash larini qo'yish.

**Files:**
- Modify (CRLF): `desktop/blender/README.md`
- Modify: `desktop/README.md` (to'liq almashtirish), `docs/admin.md` (~463–466, ~488–490), `docs/roadmap-bim-scada.md` (K1, K2, K4 sarlavhalari)

- [ ] **Step 1: `desktop/blender/README.md`** (CRLF)

- 3–6-qatorlar: `Sath desktop Blender 5.2 LTS ichida: server (loyiha/model/versiya, commit, tasdiqlash, issue lar, versiyalar farqi), GES parametrik obyektlari, simulyatsiya katalogi va xavfsizlik tekshiruvi, SCADA monitoring, DWG/DXF va mesh import. IFC — **Bonsai** da; GES geometriyasi — sof Python (`shared/geom`, `shared/ges_kinds`, numpy), FreeCAD kerak emas.`
- Talablar: FreeCAD bandini (12–14-qatorlar) o'chiring.
- Bundle bandi: `+ freecad/ (…)` ni o'chiring; «Kerak:» dan `~\Tools\fc-py313` ni olib tashlang; bundle hajmini (Task 7 Step 11) yozing.
- Jadval: «GES obyektlari» — «geometriya FreeCAD dan» → «geometriya sof Python (`ges_kinds`, FreeCAD bilan paritet ±0.5 %)»; qo'shing: «parametr o'zgarsa mesh darhol, IFC — «IFC ga qo'llash» (`sath.sync_ifc`) yoki commit da; qo'shish/«Namuna GES» — bitta undo qadami; qayta ochilganda tur/rol/parametrlar `Pset_SathParametric` dan tiklanadi (K2)». «Import» — «DWG/DXF (ezdxf, …)».
- Tuzilma: `fc_engine.py …` → `` `ifc.py` Bonsai ko'prigi (+ `orphans`) · `flows.py` bpy siz server oqimlari ``; `shared/` ro'yxatiga `geom`, `ges_kinds` qo'shing va «`wb/ges_objects.py` — workbench nusxasi» ni o'chiring; `core/` ga `` `ifc_ops.py` (IfcOperator — IFC undo, K4) ``.
- Testlar: `pytest desktop/tests` (… `geom`, `ges_kinds` FreeCAD etaloniga paritet — `data/ges_golden.json`); headless: 21 ta (`kinds_mesh`, `roundtrip_ges`, `undo_ifc` yangi), CI da SKIP taqiqlangan.
- «Sinalgan» qatori: `Sinalgan: <sana>, Blender 5.2.2, Bonsai 0.9.0, FreeCAD siz — headless 21/21, FAIL 0, SKIP 0; bundle <N> MB (freecad/ siz); GUI: Ctrl+Z dan keyin orphans() == [] (Task 9 Step 10 natijasi).`

- [ ] **Step 2: `desktop/README.md`** — to'liq:

```markdown
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
```

- [ ] **Step 3: `docs/admin.md`** — «Windows mashinada (o'rnatilgan FreeCAD 1.1.3, fork `../Sath-FreeCAD`, NSIS — `desktop/README.md`):» → «Windows mashinada (Blender 5.2 `~\Tools\blender-5.2`, NSIS — `desktop/blender/README.md`):»; `python desktop/build/build_portable.py …` qatorini o'chiring; «Versiya `desktop/GesWorkbench/package.xml` da — … «Sath build» ishlatiladi.» → «Versiya — `desktop/blender/sath/blender_manifest.toml` (`version`). Legacy FreeCAD paketi (`--product freecad`) endi yig'ilmaydi; manba `archive/freecad-legacy` tegida.»

- [ ] **Step 4: Roadmap belgilari (halol)** — hashlarni `git log --oneline -12` dan oling:

- `### K1 — Blender ni yagona trek qilish` → `… ◐ (<Task 7 hash>) — FreeCAD olib tashlandi, GES builderlari sof Python (geom/ges_kinds, paritet testlari); umumiy o'rnatiladigan sath-common paketi keyinroq`
- `### K2 — Round-trip da obyekt ma'lumotini saqlash` → `… ◐ headless (<Task 8 hash>) — lokal saqlash/ochish va eski model (roundtrip_ges); server orqali (commit → ochish → sim) tungi/qo'lda tekshiruv kutilmoqda`
- `### K4 — Undo/redo va IFC izchilligi` → `… ◐ headless (<Task 9 hash>) — undo_ifc (IfcStore.undo); GUI da Ctrl+Z qo'lda tekshiruvi <natija/kutilmoqda>`

(Task 9 Step 10 GUI tekshiruvi o'tgan bo'lsa K4 ni `✅ (<hash>)` qiling.)

- [ ] **Step 5: Commit**

```bash
git add desktop/blender/README.md desktop/README.md docs/admin.md docs/roadmap-bim-scada.md
git commit -m "docs(K1,K2,K4): README — FreeCAD siz geometriya, sync_ifc va undo, legacy archive/freecad-legacy tegida; roadmap K1/K2/K4 belgilari" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Yakuniy tekshiruv (P2 tayyor mezoni)

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m ruff check server sim desktop common
.venv\Scripts\python.exe -m pytest -q desktop/tests                 # geom, ges_kinds (FreeCAD etaloni), pure, import, tasks…
.venv\Scripts\python.exe -m pytest -q server/tests/test_ifc43.py
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; $env:SATH_REQUIRE_NO_SKIP="1"; .\desktop\tests\run_blender_tests.ps1
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test roundtrip_ges --bonsai
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test undo_ifc --bonsai
.venv\Scripts\python.exe desktop/build/build_blender_bundle.py --no-zip   # freecad/ yo'q, Sath.exe da GES obyekti
```
Mezonlar (spec «Bosqichlar» P2): golden paritet — hajm ±0.5 % (sinalgan ≤ 0.25 %); FreeCAD siz mashinada 11 GES obyekti va «Namuna GES» (`kinds_mesh`, `objects`, `demo_plant`, bundle `BUNDLE_GES`); `roundtrip_ges` (kind/role/params teng, `animate_hydro` > 0 keyframe); `undo_ifc` (`orphans() == []`); CI `desktop-blender` da SKIP 0.

## Spec qamrovi (o'z-o'zini tekshirish)

| Spec talabi | Task |
|---|---|
| §6 `gen_fc_golden.py` → `ges_golden.json` FreeCAD bor mashinada, birinchi | 1 |
| §6 `geom.py` (numpy, float64, bpy siz; box/cylinder/cone/torus/extrude/revolve/sweep/loft; chord tolerance; cut o'rniga to'g'ridan-to'g'ri) | 2, 4 |
| §6 `ges_kinds.py` 11 kind: parametr, birlik, default, pset, ifc_class, rang, build, quantities (analitik) | 3–5 |
| §6 paritet: hajm ±0.5 %, bbox ±tolerance, CI da FreeCAD kerak emas | 3–5 |
| §6 `ges_objects` sxemani `ges_kinds` dan, `add_object.poll` FreeCAD ga bog'liq emas, `foreach_set` | 6 |
| §6 olib tashlash: fc_engine, wb, FreeCAD DXF, prefs, bundle freecad/, sync wb; GesWorkbench + fork → arxiv | 7 |
| §4 K2: Pset_SathParametric, restore_from_ifc → RestoreReport, ifc.loaded, mesh qayta qurilmaydi, TwinBindingError | 8 |
| §4 K4: IfcOperator, sync_ifc + ifc_dirty, orphans + commit dialogi, flush_pending xatolari, objects testi | 9 |
| §7 / P2: engine testi golden paritet bilan almashadi, CI SKIP 0 | 6, 7 |
| Roadmap K1/K2/K4 belgilari, README | 10 |

## Keyingi rejalar (shu spec bo'yicha)

- **P3** — modul reyestri, `api.py` (`api.ifc.IfcOperator`, `restore_ges`, `geom`/`kinds` fasadi), server `permissions`, `SathPanel`; `add_object.poll` ga `perms.can("model.write")` (P2 da `poll` yo'q — FreeCAD sharti olib tashlandi).
- **P4** — workspace lar, tema, tokens, keymap, byudjetlar; bundle hajmi P2 da kichraygan (FreeCAD siz).
- Web: `draftKinds.ts` ni `ges_kinds` dan generatsiya qilish (hozir farqlar `test_web_draft_pset_fields_known_diff` da qayd etilgan).
