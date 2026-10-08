"""ges_kinds: FreeCAD etaloniga (desktop/tests/data/ges_golden.json) paritet — sxema, IFC klass, rang, Pset_GES_*,
analitik hajm (±0.1 %), mesh hajmi (±0.5 %), bbox, yuza (FreeCAD fuse qilmagan turlar, ±1 %), yopiq qobiqlar;
K2 teskari xaritalash; web qoralama turlari bilan ma'lum farqlar."""

import json
import re
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

WEB = ROOT / "web" / "src" / "viewer" / "draftKinds.ts"
# Web qoralama turlari ↔ desktop: ma'lum farqlar. O'zgarsa — ataylab (ikkala tomonni yoki shu ro'yxatni yangilang).
WEB_ONLY = {"Pset_GES_Penstock": {"DevorQalinligi_mm"}, "Pset_GES_Spillway": {"BetonKlassi"}}
DESKTOP_ONLY = {
    "Pset_GES_Penstock": {"Qiyalik_deg", "TirsakRadiusi_m", "ChiqishUzunligi_m"},
    "Pset_GES_Powerhouse": {"Uzunlik_m", "Kenglik_m", "Balandlik_m"},
}
# Etalon (FreeCAD) enum yozuvi → joriy kanonik qiymat. To'g'on turi IDS SATH-10 yozuviga keltirildi (M4): eski
# «Tuproq»/«Tosh-tuproq» o'qishda alias orqali qabul qilinadi; IDS dagi qo'shimcha turlar (Tayanchli, Kontrfors)
# etalonda yo'q — oxirida qo'shilgan. Boshqa enumlar etalon bilan aynan bir xil.
GOLDEN_ENUM_ALIAS = {("GES_Dam", "DamType"): {"Tuproq": "Tuproqli", "Tosh-tuproq": "Toshli"}}
GOLDEN_ENUM_EXTRA = {("GES_Dam", "DamType"): ["Tayanchli", "Kontrfors"]}
IDS_FILE = ROOT / "docs" / "ids" / "sath-ges.ids"


def _ported(kind):
    if kind not in ges_kinds.KINDS:
        pytest.skip(f"{kind} hali ko'chirilmagan")


def _same(a, b):
    if type(a) is not type(b) and not (isinstance(a, float) and isinstance(b, float)):
        return False  # JSON 2 va 2.0 ni farqlaydi: IfcInteger → IfcReal drifti ushlanadi
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
        alias = GOLDEN_ENUM_ALIAS.get((kind, f["name"]), {})
        items = [alias.get(x, x) for x in f["items"]] + GOLDEN_ENUM_EXTRA.get((kind, f["name"]), [])
        assert (p.label, p.ptype, list(p.items)) == (f["label"], f["type"], items), f["name"]
        for old, new in alias.items():  # eski yozuv hali ham qabul qilinadi (kanonikka keltiriladi)
            assert ges_kinds.normalize(kind, {f["name"]: old})[f["name"]] == new
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
        {"Pset_SathParametric": {"Kind": "GES_Dam", "SchemaVersion": "v1", "Params": "{}"}},
        {"Pset_SathParametric": {"Kind": "GES_Dam", "SchemaVersion": 1, "Params": 5}},
        {"Pset_SathParametric": {"Kind": "GES_Dam", "SchemaVersion": 1, "Params": "{}", "Units": "mm"}},
    ):
        with pytest.raises(ges_kinds.UnknownKind):
            ges_kinds.from_psets(bad)
    r = ges_kinds.from_psets({"Pset_GES_Dam": {"Turi": "beton og'irlik", "Balandlik_m": 25.0}})  # web qoralama
    assert r.params["Height"] == 25.0 and r.params["DamType"] == "Gravitatsion" and not r.warnings  # alias (M4)
    r = ges_kinds.from_psets({"Pset_GES_Dam": {"Turi": "yog'och", "Balandlik_m": 25.0}})
    assert r.params["DamType"] == "Gravitatsion" and r.warnings


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


# --- I1: geometrik bayroq; M2: chegaralar; I2: Pset_GES_* ustun; M4: IDS; M12: web devor qalinligi ----------------


def _toggles(prm, v):
    if prm.ptype == "enum":
        return [x for x in prm.items if x != v]
    if prm.ptype == "int":
        return [v + 1, v - 1]
    return [v * 0.5, v * 1.5, v + 0.5, v - 0.5]


def _build_or_none(kind, p):
    try:
        v, f = ges_kinds.build(kind, p)
    except ValueError:
        return None
    return v.tobytes() + f.tobytes()


@pytest.mark.parametrize("kind", ges_kinds.ORDER)
def test_geometric_flag_matches_build(kind):
    """Geometrik bo'lmagan parametr build() ni bayt-bayt o'zgartirmaydi; geometrik — kamida bitta holatda o'zgartiradi
    (etalon holatlari: masalan BendRadius faqat qiya quvurda, View — Kesim da)."""
    s = ges_kinds.spec(kind)
    bases = [ges_kinds.normalize(kind, c["params"]) for c in GOLDEN["kinds"][kind]["cases"]]
    geo = ges_kinds.geometric_params(kind)
    for prm in s.params:
        changed = False
        for base in bases:
            ref = _build_or_none(kind, base)
            for v in _toggles(prm, base[prm.name]):
                got = _build_or_none(kind, {**base, prm.name: v})
                if got is None:
                    continue  # chegaradan tashqari qiymat
                if prm.name not in geo:
                    assert got == ref, f"{kind}.{prm.name} geometrik emas deb belgilangan, lekin build() o'zgardi"
                changed |= got != ref
        assert changed == (prm.name in geo), f"{kind}.{prm.name}: geometric={prm.name in geo}, o'zgarish={changed}"


@pytest.mark.parametrize(
    "kind,name,bad,ok",
    [
        ("GES_Turbine", "Efficiency", [0.0, -0.1, 1.01], [1.0, 0.5]),
        ("GES_Generator", "EfficiencyMax", [0.0, 1.2], [1.0]),
        ("GES_Generator", "IronLossFrac", [-0.1, 1.1], [0.0, 1.0]),
        ("GES_Generator", "Poles", [0, 1], [2]),
        ("GES_Penstock", "Inclination", [-1.0, 90.0, 120.0], [0.0, 45.0]),
        ("GES_Spillway", "Gates", [-1], [0, 5]),
        ("GES_Intake", "Openings", [0, -2], [1]),
        ("GES_Powerhouse", "Units", [0], [1]),
        ("GES_ControlRoom", "Operators", [-1], [0]),
        ("GES_Tailrace", "Manning", [0.0], [0.013]),
    ],
)
def test_param_bounds(kind, name, bad, ok):
    for v in bad:
        with pytest.raises(ValueError, match=r"bo'lsin|bo'lmasin"):
            ges_kinds.validate(kind, {name: v})
    for v in ok:
        ges_kinds.validate(kind, {name: v})


def test_intake_openings_not_clamped_in_geometry():
    with pytest.raises(ValueError):
        ges_kinds.build("GES_Intake", {"Openings": 0})
    one = ges_kinds.build_parts("GES_Intake", {"Openings": 1})
    assert len(one) == 3 + 2  # 3 qatlam + (n + 1) ustun


def test_stale_parametric_overridden_by_pset_ges():
    p = ges_kinds.normalize("GES_Dam", {"Height": 20.0})
    ps = {**ges_kinds.psets("GES_Dam", p), **ges_kinds.parametric_pset("GES_Dam", "dam", p)}
    ps["Pset_GES_Dam"] = {**ps["Pset_GES_Dam"], "Balandlik_m": 25.0, "BetonKlassi": "B30"}  # web / Bonsai tahriri
    r = ges_kinds.from_psets(ps)
    assert (r.source, r.params["Height"], r.params["ConcreteClass"]) == ("parametric", 25.0, "B30")
    assert len(r.warnings) == 2 and any("Balandlik_m" in w for w in r.warnings), r.warnings
    assert r.params["Length"] == 60.0  # pset da yo'q parametr — JSON dan
    ps["Pset_GES_Dam"]["Balandlik_m"] = "baland"  # yaroqsiz — JSON qoladi, ogohlantirish
    r = ges_kinds.from_psets(ps)
    assert r.params["Height"] == 20.0 and any("yaroqsiz" in w for w in r.warnings)


def test_approximate_flag_roundtrip():
    p = ges_kinds.normalize("GES_Turbine")
    assert ges_kinds.parametric_pset("GES_Turbine", "unit:1", p)["Pset_SathParametric"]["Approximate"] is False
    for approx in (True, False):
        ps = {**ges_kinds.psets("GES_Turbine", p), **ges_kinds.parametric_pset("GES_Turbine", "unit:1", p, approx)}
        assert ges_kinds.from_psets(ps).approximate is approx
    assert ges_kinds.from_psets(ges_kinds.psets("GES_Turbine", p)).approximate is True  # faqat Pset_GES_* — taxminiy


def test_dam_types_match_ids_sath10():
    src = IDS_FILE.read_text(encoding="utf-8")
    block = src[src.index('identifier="SATH-10"') :]
    block = block[: block.index("</specification>")]
    ids = re.findall(r'<xs:enumeration value="([^"]+)"', block)
    assert set(ges_kinds.DAM_TYPES) == set(ids), (ges_kinds.DAM_TYPES, ids)
    for t in ("Tuproq", "Tosh-tuproq", "beton og'irlik", "TUPROQ"):
        assert ges_kinds.psets("GES_Dam", {"DamType": t})["Pset_GES_Dam"]["Turi"] in ids


def test_web_penstock_wall_thickness_mm():
    r = ges_kinds.from_psets({"Pset_GES_Penstock": {"Diametr_m": 3.0, "DevorQalinligi_mm": 25}})
    assert r.params["WallThickness"] == pytest.approx(0.025) and r.params["Diameter"] == 3.0
    p = ges_kinds.normalize("GES_Penstock", {"WallThickness": 0.02})
    ps = {**ges_kinds.psets("GES_Penstock", p), **ges_kinds.parametric_pset("GES_Penstock", "penstock:1", p)}
    ps["Pset_GES_Penstock"]["DevorQalinligi_mm"] = 20  # web qoralama maydoni — JSON bilan bir xil, ogohlantirish yo'q
    assert ges_kinds.from_psets(ps).warnings == []
