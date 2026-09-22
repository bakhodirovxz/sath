"""IFC sxemasi (G1): IFC4 va IFC4.3 (ISO 16739-1:2024, `IFC4X3_ADD2`) — GES obyektlarini sxemaga mos
entitylarga xaritalash, sinf nomini sxemaga nisbatan tekshirish.

IFC4.3 da infratuzilma entitylari bor: IfcFacility/IfcFacilityPartCommon (suv tashlagich, suv qabul qilgich —
USERDEFINED + ObjectType), IfcEarthworksFill (tuproqli/toshli to'g'on, EMBANKMENT), IfcAlignment (kanal, yo'l),
IfcGeographicElement TERRAIN (relyef); quvur/zatvor — IfcDistributionFlowElement oilasi (IfcPipeSegment,
IfcValve). IFC4 da bular yo'q — tessellatsiya + Pset_GES_* (mavjud xaritalash saqlanadi).
Mavjud IFC4 modellar o'qilishda davom etadi (ifcopenshell ikkalasini ochadi)."""

from __future__ import annotations

from functools import lru_cache

import ifcopenshell

SCHEMAS = ("IFC4", "IFC4X3_ADD2")
DEFAULT_CLASS = "IfcBuildingElementProxy"

# kind → (klass, PredefinedType, ObjectType) — sxema bo'yicha
_MAP = {
    "IFC4": {
        "dam": ("IfcWall", "SOLIDWALL", None),
        "penstock": ("IfcPipeSegment", None, None),
        "turbine": ("IfcFlowMovingDevice", None, "TURBINE"),
        "generator": ("IfcElectricGenerator", None, None),
        "spillway": ("IfcSlab", None, "SPILLWAY"),
        "powerhouse": ("IfcBuildingElementProxy", None, "POWERHOUSE"),
        "transformer": ("IfcTransformer", None, None),
        "intake": ("IfcBuildingElementProxy", None, "INTAKE"),
        "site": ("IfcGeographicElement", None, "TERRAIN"),
        "valve": ("IfcValve", None, None),
        "channel": ("IfcBuildingElementProxy", None, "CHANNEL"),
    },
    "IFC4X3_ADD2": {
        "dam": ("IfcWall", "SOLIDWALL", "DAM"),  # beton (gravitatsion/arkali); tuproqli — dam_embankment
        "dam_embankment": ("IfcEarthworksFill", "EMBANKMENT", "DAM"),
        "penstock": ("IfcPipeSegment", "RIGIDSEGMENT", "PENSTOCK"),
        "turbine": ("IfcFlowMovingDevice", None, "TURBINE"),
        "generator": ("IfcElectricGenerator", "ENGINEGENERATOR", None),
        "spillway": ("IfcFacilityPartCommon", "USERDEFINED", "SPILLWAY"),
        "powerhouse": ("IfcFacilityPartCommon", "USERDEFINED", "POWERHOUSE"),
        "transformer": ("IfcTransformer", "VOLTAGE", None),
        "intake": ("IfcFacilityPartCommon", "USERDEFINED", "INTAKE"),
        "site": ("IfcGeographicElement", "TERRAIN", None),
        "valve": ("IfcValve", "ISOLATION", None),
        "channel": ("IfcFacilityPartCommon", "USERDEFINED", "CHANNEL"),
    },
}

# IFC4 sxemasida (va 2X3 da) "IFC4X3" mos kelmaydigan nomlarni normallashtirish
_ALIASES = {"IFC4X3": "IFC4X3_ADD2", "IFC4X3_ADD1": "IFC4X3_ADD2", "IFC4X3_TC1": "IFC4X3_ADD2"}


def normalize(schema: str) -> str:
    s = (schema or "IFC4").upper()
    s = _ALIASES.get(s, s)
    if s not in SCHEMAS:
        raise ValueError(f"IFC sxemasi: {', '.join(SCHEMAS)} (berildi: {schema})")
    return s


def for_file(f: ifcopenshell.file) -> str:
    """Fayl sxemasi (ifcopenshell: 'IFC4' yoki 'IFC4X3') → bizning kalit."""
    ident = getattr(f, "schema_identifier", None) or f.schema
    if str(ident).upper().startswith("IFC4X3"):
        return "IFC4X3_ADD2"
    return "IFC4"


def map_kind(kind: str | None, schema: str, dam_type: str | None = None) -> tuple[str, str | None, str | None]:
    """GES turi → (klass, PredefinedType, ObjectType). Tuproqli/toshli to'g'on IFC4.3 da IfcEarthworksFill."""
    s = normalize(schema)
    k = kind or ""
    if k == "dam" and s == "IFC4X3_ADD2" and (dam_type or "").lower() in ("tuproqli", "toshli", "embankment", "rockfill"):
        k = "dam_embankment"
    return _MAP[s].get(k, (DEFAULT_CLASS, None, None))


@lru_cache(maxsize=4)
def element_classes(schema: str) -> frozenset[str]:
    """Sxemadagi IfcProduct sub-sinflari (element yaratish uchun ruxsat etilgan nomlar)."""
    s = normalize(schema)
    sch = ifcopenshell.schema_by_name(s)
    out = set()
    for d in sch.entities():
        if d.is_abstract():
            continue
        sup, ok = d, False
        while sup is not None:
            if sup.name() == "IfcProduct":
                ok = True
                break
            sup = sup.supertype()
        if ok:
            out.add(d.name())
    return frozenset(out)


def check_class(name: str, schema: str) -> str:
    """Sinf nomi sxemada mavjud va konkret IfcProduct bo'lsa nomni (to'g'ri registrda) qaytaradi, aks holda ValueError."""
    s = normalize(schema)
    classes = element_classes(s)
    lookup = {c.lower(): c for c in classes}
    c = lookup.get((name or "").strip().lower())
    if c is None:
        raise ValueError(f"IFC sinfi noto'g'ri yoki {s} sxemasida yo'q: {name}")
    return c


def from_freecad_type(ifc_type: str, schema: str = "IFC4") -> str:
    """FreeCAD IfcType («Pipe Segment») → «IfcPipeSegment», sxemaga nisbatan tekshirilgan."""
    return check_class("Ifc" + (ifc_type or "").replace(" ", ""), schema)
