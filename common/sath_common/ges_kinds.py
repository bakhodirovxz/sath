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
    """Analitik miqdorlar: volume_m3, mass_t (zichlik ma'lum bo'lsa, aks holda None). Mashina zali «Yopiq» da hajm/massa
    qattiq blokniki (FreeCAD pariteti), bino qobig'iniki emas."""
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
        try:
            ver = int(sp.get("SchemaVersion") or 0)
        except (TypeError, ValueError):
            raise UnknownKind(f"{kind}: SchemaVersion yaroqsiz ({sp.get('SchemaVersion')!r})") from None
        if ver > SCHEMA_VERSION:
            raise UnknownKind(f"{kind}: sxema v{ver} — bu ilova v{SCHEMA_VERSION} gacha biladi (Sath ni yangilang)")
        try:
            raw = json.loads(sp.get("Params") or "{}")
        except (TypeError, ValueError) as e:
            raise UnknownKind(f"{kind}: Params JSON buzilgan ({e})") from None
        units = sp.get("Units")
        if units is not None and units != "m":
            raise UnknownKind(f"{kind}: birlik {units!r} — faqat metr ('m') qo'llab-quvvatlanadi")
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
