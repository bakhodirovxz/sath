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
