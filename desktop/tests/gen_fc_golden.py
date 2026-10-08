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
