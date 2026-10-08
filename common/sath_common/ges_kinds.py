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
import math
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
    # True — build() natijasini o'zgartiradi (mesh + IFC representation qayta quriladi); False — faqat psetlar.
    # Har tur uchun aniq belgilangan; test_ges_kinds har parametrni o'zgartirib build() bilan tekshiradi.
    geometric: bool = False
    lo: float | None = None  # pastki chegara (validate); lo_open — qat'iy (x > lo), aks holda x ≥ lo
    hi: float | None = None  # yuqori chegara; hi_open — qat'iy (x < hi), aks holda x ≤ hi
    lo_open: bool = False
    hi_open: bool = False
    aliases: tuple[tuple[str, str], ...] = ()  # enum: eski/web yozuv → kanonik qiymat (kichik harf bilan solishtiriladi)


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
    """Uzunlik (m) — har doim geometrik va > 0."""
    return Param(name, label, "length", float(default), geometric=True, lo=0.0, lo_open=True)


def _flt(name: str, label: str, default: float, **kw) -> Param:
    return Param(name, label, "float", float(default), **kw)


def _int(name: str, label: str, default: int, **kw) -> Param:
    return Param(name, label, "int", int(default), **kw)


def _enum(name: str, label: str, items: tuple[str, ...], default: str | None = None, **kw) -> Param:
    return Param(name, label, "enum", default or items[0], tuple(items), **kw)


_FRACTION = {"lo": 0.0, "hi": 1.0, "lo_open": True}  # FIK: (0, 1]


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


# To'g'on turi — IDS SATH-10 (docs/ids/sath-ges.ids) ro'yxati bilan bir xil yozuv. FreeCAD davri «Tuproq»/«Tosh-tuproq»
# va web qoralama «beton og'irlik» o'qishda (va yozishda) kanonik qiymatga keltiriladi (eski modellar ochiladi).
DAM_TYPES = ("Gravitatsion", "Arkali", "Tuproqli", "Toshli", "Tayanchli", "Kontrfors")
DAM_TYPE_ALIASES = (
    ("tuproq", "Tuproqli"), ("tosh-tuproq", "Toshli"), ("beton og'irlik", "Gravitatsion"),
    ("gravity", "Gravitatsion"), ("arch", "Arkali"), ("embankment", "Tuproqli"), ("rockfill", "Toshli"),
    ("buttress", "Kontrfors"),
)  # fmt: skip

_register(KindSpec(
    kind="GES_Dam", label="To'g'on", ifc_class="IfcWall", pset="Pset_GES_Dam", role="dam", color=(0.72, 0.70, 0.66),
    params=(
        _len("Length", "Gerbi uzunligi", 60), _len("Height", "Balandligi", 20),
        _len("CrestWidth", "Gerbi kengligi", 6), _len("BaseWidth", "Asos kengligi", 16),
        _enum("DamType", "Turi", DAM_TYPES, aliases=DAM_TYPE_ALIASES),
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
        _flt("DischargeCoefficient", "Sarf koeffitsienti m (Q = m·b·√(2g)·H^1.5)", 0.49, lo=0.0, lo_open=True),
        _int("Gates", "Darvozalar soni", 2, lo=0),
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
        _int("Units", "Agregatlar soni", 2, lo=1), _flt("FloorElevation", "Pol belgisi, m (abs)", 0),
        _enum("ConcreteClass", "Beton klassi (karkas)", CONCRETE, "B25"),
        _enum("View", "Ko'rinish", ("Yopiq", "Kesim"), geometric=True),
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
        _len("WallThickness", "Devor/tag qalinligi", 0.8), _flt("BedSlope", "Tag nishabi S", 0.001, lo=0.0),
        _flt("Manning", "Manning g'adir-budirligi n", 0.03, lo=0.0, lo_open=True),
        _flt("BedElevation", "Tag belgisi, m (abs)", 0),
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
        _flt("Roughness", "G'adir-budirlik, mm (Darcy-Weisbach)", 0.1, lo=0.0),
        _enum("Material", "Material", ("Po'lat", "Temir-beton", "GRP")),
        _flt("Inclination", "Qiyalik, ° (gorizontaldan pastga; 0 — to'g'ri)", 0, geometric=True, lo=0.0, hi=90.0,
             hi_open=True),
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
        _flt("RatedFlow", "Hisobiy sarf, m3/s", 62), _flt("Efficiency", "Maksimal FIK, 0..1", 0.92, **_FRACTION),
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
        _flt("EfficiencyMax", "Nominal FIK, 0..1", 0.985, **_FRACTION),
        _flt("IronLossFrac", "Temir (doimiy) yo'qotish ulushi, 0..1", 0.4, lo=0.0, hi=1.0),
        _int("Poles", "Qutblar soni", 24, lo=2), _flt("Frequency", "Chastota, Hz", 50, lo=0.0, lo_open=True),
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
    n = int(p["Openings"])  # ≥ 1 — validate (geometriyada qisilmaydi: pset bilan bir xil son)
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
        _int("Openings", "Teshiklar soni", 2, geometric=True, lo=1), _flt("ScreenBarSpacing", "Panjara oralig'i, mm", 100),
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
        _flt("FloorElevation", "Pol belgisi, m (abs)", 0), _int("Operators", "Dispetcherlar soni", 2, lo=0),
        _int("ScadaChannels", "SCADA kanallari soni", 256, lo=0),
    ),
    fields=(
        _real("Uzunlik_m", "Length"), _real("Kenglik_m", "Width"), _real("Balandlik_m", "Height"),
        _real("PolBelgisi_m", "FloorElevation"), _count("Dispetcherlar", "Operators"), _count("SCADA_Kanallar", "ScadaChannels"),
    ),
    parts=_controlroom_parts,
    volume=lambda p: p["Length"] * p["Width"] * p["Height"] - 0.8 * p["Length"] * (0.1 * p["Width"] - EPS) * 0.45 * p["Height"],
    check=_controlroom_check,
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
            v = dict(p.aliases).get(v.strip().lower(), v)  # eski/web yozuv → kanonik (IDS)
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


def _bound_error(prm: Param, v) -> str | None:
    """Param chegarasi buzilgan bo'lsa — matn (NaN ham rad etiladi), aks holda None."""
    if prm.lo is not None and not (v > prm.lo if prm.lo_open else v >= prm.lo):
        return f"{prm.lo:g} dan katta bo'lsin" if prm.lo_open else f"{prm.lo:g} dan kichik bo'lmasin"
    if prm.hi is not None and not (v < prm.hi if prm.hi_open else v <= prm.hi):
        return f"{prm.hi:g} dan kichik bo'lsin" if prm.hi_open else f"{prm.hi:g} dan katta bo'lmasin"
    return None


def validate(kind: str, params: dict | None = None) -> dict:
    """normalize + chegaralar (Param.lo/hi: uzunliklar > 0, sonlar, FIK, qiyalik) + turga xos geometrik cheklovlar.
    Xato — ValueError (foydalanuvchiga matn)."""
    s = spec(kind)
    p = normalize(kind, params)
    for prm in s.params:
        if prm.ptype != "enum" and (err := _bound_error(prm, p[prm.name])):
            raise ValueError(f"{s.label}: «{prm.label}» {err}")
    s.check(p)
    return p


def geometric_params(kind: str) -> frozenset[str]:
    """build() natijasini o'zgartiradigan parametr nomlari (qolganlari — faqat psetlar)."""
    return frozenset(p.name for p in spec(kind).params if p.geometric)


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


def parametric_pset(kind: str, role: str, params: dict | None = None, approximate: bool = False) -> dict[str, dict]:
    """K2: to'liq round-trip uchun {Pset_SathParametric: Kind, Role, SchemaVersion, Params (JSON, metr), Units,
    Approximate}. Approximate=True — geometrik parametrlar eski Pset_GES_* dan taxmin qilingan (mesh IFC dagidek;
    qayta ochilganda ham «taxminiy» bo'lib qoladi, foydalanuvchi o'lchamlarni tasdiqlamaguncha qayta qurilmaydi)."""
    p = normalize(kind, params)
    return {
        PARAMETRIC_PSET: {
            "Kind": kind, "Role": role or "", "SchemaVersion": SCHEMA_VERSION,
            "Params": json.dumps(p, ensure_ascii=False, sort_keys=True), "Units": "m", "Approximate": bool(approximate),
        }
    }  # fmt: skip


@dataclass
class Restored:
    kind: str
    role: str
    params: dict
    source: str  # "parametric" — Pset_SathParametric dan; "pset" — Pset_GES_* dan teskari xaritalangan
    warnings: list[str] = field(default_factory=list)
    approximate: bool = False  # geometrik parametrlar taxminiy (pset dan yoki Pset_SathParametric.Approximate)


# Pset_GES_* dagi qo'shimcha (web qoralama) maydonlar: {tur: {maydon: (parametr, ko'paytuvchi)}} — faqat o'qishda
PSET_EXTRA: dict[str, dict[str, tuple[str, float]]] = {
    "GES_Penstock": {"DevorQalinligi_mm": ("WallThickness", 0.001)},  # mm → m
}


def _pset_raw(kind: str, values: dict) -> dict[str, tuple[str, object]]:
    """Pset_GES_<X> qiymatlari → {parametr: (maydon, xom qiymat)} (to'g'ridan-to'g'ri maydonlar + PSET_EXTRA)."""
    out = {f.param: (f.name, values[f.name]) for f in spec(kind).fields if f.param and f.name in values}
    for name, (param, scale) in PSET_EXTRA.get(kind, {}).items():
        if name in values and param not in out:
            v = values[name]
            try:
                v = float(v) * scale
            except (TypeError, ValueError):
                pass  # _coerce / overlay yaroqsiz deb xabar beradi
            out[param] = (name, v)
    return out


def _same_value(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)), abs(float(b)))
        except (TypeError, ValueError):
            return False
    return a == b


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
        except (TypeError, ValueError, OverflowError):
            warns.append(f"{k}={v!r} yaroqsiz — default {by[k].default!r}")
    return out, warns


def _overlay_pset(kind: str, values: dict, params: dict, warns: list[str]) -> None:
    """I2: Pset_SathParametric eskirgan bo'lishi mumkin (web qoralama, Bonsai pset muharriri Pset_GES_* ni o'zgartiradi,
    JSON ni emas) — to'g'ridan-to'g'ri xaritalangan Pset_GES_* qiymati JSON dagidan farq qilsa, Pset_GES_* ustun;
    har farq ogohlantirishda maydon nomi bilan. Yaroqsiz Pset_GES_* qiymati e'tiborsiz (JSON qoladi)."""
    s = spec(kind)
    by = {p.name: p for p in s.params}
    for param, (fname, v) in _pset_raw(kind, values).items():
        try:
            val = _cast_param(by[param], v)
        except (TypeError, ValueError, OverflowError):
            warns.append(f"{s.pset}.{fname}={v!r} yaroqsiz — {PARAMETRIC_PSET} dagi {params[param]!r} qoldi")
            continue
        if not _same_value(val, params[param]):
            warns.append(
                f"{s.pset}.{fname}={val!r} {PARAMETRIC_PSET} dagi {param}={params[param]!r} o'rniga olindi "
                "(IFC boshqa joyda tahrirlangan)"
            )
            params[param] = val


def from_psets(ps: dict) -> Restored | None:
    """IFC element psetlari ({nom: {xususiyat: qiymat}}) → Restored; GES elementi bo'lmasa None, tanib bo'lmasa
    UnknownKind. Avval Pset_SathParametric (tur, rol, barcha parametrlar; farq qilgan Pset_GES_* maydonlari ustun —
    `_overlay_pset`), bo'lmasa Pset_GES_<X> nomidan tur va maydonlardan parametrlar (pset da yo'q geometriya
    parametrlari — default, `approximate=True`; rol — bo'sh; `infer_roles`)."""
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
        _overlay_pset(kind, ps.get(spec(kind).pset) or {}, params, warns)
        approx = sp.get("Approximate") is True or str(sp.get("Approximate")).lower() == "true"
        return Restored(kind, str(sp.get("Role") or ""), params, "parametric", warns, approximate=approx)
    for name, values in ps.items():
        kind = KIND_BY_PSET.get(name)
        if kind is None:
            continue
        raw = {param: v for param, (_, v) in _pset_raw(kind, values).items()}
        params, warns = _coerce(kind, raw)
        return Restored(kind, "", params, "pset", warns, approximate=True)
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
