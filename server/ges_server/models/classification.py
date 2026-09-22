"""Klassifikatsiya (G5): IfcClassification / IfcClassificationReference — Uniclass 2015 (buildingSMART/NBS
kodlari, GES uchun tegishli qismi) va mahalliy «SATH-KSI» (GES uskuna/inshoot klassifikatori; KKS/RDS-PP
uskuna kodlash H1 da alohida). GES turi (`kind`) → kod xaritasi; mavjud versiyani avtomatik
klassifikatsiyalash (yangi versiya)."""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api.classification
import ifcopenshell.util.classification
import ifcopenshell.util.element

# system → {kind: (code, name)}
SYSTEMS: dict[str, dict] = {
    "Uniclass2015": {
        "title": "Uniclass 2015",
        "source": "NBS / buildingSMART UK",
        "edition": "2024-01",
        "kinds": {
            "dam": ("Ss_20_05_15_25", "Dam systems (embankment and concrete)"),
            "spillway": ("Ss_20_05_15_80", "Spillway systems"),
            "intake": ("Ss_50_30_40_45", "Intake systems"),
            "penstock": ("Ss_50_30_40_60", "Penstock systems"),
            "turbine": ("Pr_60_70_35_91", "Water turbines"),
            "generator": ("Pr_70_60_36_31", "Generators (hydroelectric)"),
            "transformer": ("Pr_70_70_87_84", "Transformers (power)"),
            "powerhouse": ("En_20_30_40", "Hydroelectric power stations"),
            "site": ("EF_15_10", "Ground (terrain)"),
            "pipe": ("Ss_50_30_40_60", "Penstock systems"),
        },
    },
    "SATH-KSI": {
        "title": "SATH-KSI — GES inshoot va uskunalari klassifikatori",
        "source": "Sath (mahalliy, GES gidrotexnik inshoot va uskuna sinflari)",
        "edition": "1.0",
        "kinds": {
            "dam": ("GTS.01", "To'g'on"),
            "spillway": ("GTS.02", "Suv tashlagich"),
            "intake": ("GTS.03", "Suv qabul qilgich"),
            "penstock": ("GTS.04", "Bosimli quvur"),
            "powerhouse": ("GTS.05", "Mashina zali binosi"),
            "site": ("GTS.09", "Maydon / relyef"),
            "turbine": ("USK.01", "Gidroturbina"),
            "generator": ("USK.02", "Gidrogenerator"),
            "transformer": ("USK.03", "Kuch transformatori"),
            "pipe": ("GTS.04", "Bosimli quvur"),
        },
    },
}
DEFAULT_SYSTEM = "SATH-KSI"

# IFC klassi + Pset dan GES turini taxmin qilish (mavjud fayllarni avtomatik klassifikatsiyalash)
_CLASS_KIND = {
    "IfcPipeSegment": "penstock",
    "IfcFlowMovingDevice": "turbine",
    "IfcElectricGenerator": "generator",
    "IfcTransformer": "transformer",
    "IfcGeographicElement": "site",
}
_PSET_KIND = {"Pset_GES_Dam": "dam", "Pset_GES_Turbine": "turbine", "Pset_GES_Penstock": "penstock", "Pset_GES_Site": "site"}


def kind_of(el) -> str | None:
    """Element uchun GES turi: Pset_GES_Object.Turi, so'ng Pset nomlari, so'ng IFC klassi/nomi."""
    psets = ifcopenshell.util.element.get_psets(el) or {}
    t = (psets.get("Pset_GES_Object") or {}).get("Turi")
    if t and t in SYSTEMS[DEFAULT_SYSTEM]["kinds"]:
        return t
    for pname, k in _PSET_KIND.items():
        if pname in psets:
            return k
    if el.is_a() in _CLASS_KIND:
        return _CLASS_KIND[el.is_a()]
    ot = (getattr(el, "ObjectType", None) or "").upper()  # IFC4.3: IfcFacilityPartCommon USERDEFINED + ObjectType
    if ot in ("SPILLWAY", "INTAKE", "POWERHOUSE", "DAM", "PENSTOCK", "CHANNEL"):
        return {"SPILLWAY": "spillway", "INTAKE": "intake", "POWERHOUSE": "powerhouse", "DAM": "dam", "PENSTOCK": "penstock", "CHANNEL": "pipe"}[ot]
    name = (el.Name or "").lower()
    if "tashlag" in name or "spillway" in name:
        return "spillway"
    if "qabul" in name or "intake" in name:
        return "intake"
    if el.is_a("IfcWall") and ("to'g'on" in name or "togon" in name or "dam" in name):
        return "dam"
    return None


def code_for(kind: str | None, system: str = DEFAULT_SYSTEM) -> tuple[str, str] | None:
    if kind is None or system not in SYSTEMS:
        return None
    return SYSTEMS[system]["kinds"].get(kind)


def _classification(f: ifcopenshell.file, system: str):
    for c in f.by_type("IfcClassification"):
        if c.Name == system:
            return c
    meta = SYSTEMS[system]
    c = ifcopenshell.api.classification.add_classification(f, classification=system)
    c.Source = meta["source"]
    c.Edition = meta["edition"]
    if hasattr(c, "Description"):
        c.Description = meta["title"]
    return c


def assign(f: ifcopenshell.file, el, code: str, name: str, system: str = DEFAULT_SYSTEM) -> None:
    """Elementga IfcClassificationReference (bor bo'lsa takrorlanmaydi)."""
    for ref in ifcopenshell.util.classification.get_references(el):
        if ref.Identification == code and ref.ReferencedSource is not None and ref.ReferencedSource.Name == system:
            return
    c = _classification(f, system)
    ifcopenshell.api.classification.add_reference(f, products=[el], identification=code, name=name, classification=c)


def references(el) -> list[dict]:
    out = []
    for ref in ifcopenshell.util.classification.get_references(el):
        src = ref.ReferencedSource
        out.append({"system": getattr(src, "Name", None) if src is not None else None, "code": ref.Identification, "name": ref.Name})
    return out


def _candidates(f: ifcopenshell.file):
    """Klassifikatsiyalanadigan obyektlar: elementlar + IFC4.3 infratuzilma qismlari (IfcFacilityPart)."""
    out = list(f.by_type("IfcElement"))
    try:
        out += list(f.by_type("IfcFacilityPart"))
    except RuntimeError:  # IFC4 da bunday tur yo'q
        pass
    return out


def classify_file(f: ifcopenshell.file, system: str = DEFAULT_SYSTEM, overwrite: bool = False) -> dict:
    """Barcha elementlarni GES turi bo'yicha klassifikatsiyalaydi (mavjud havolalar saqlanadi).
    Qaytaradi: {"system", "assigned", "skipped", "by_code": {...}}"""
    if system not in SYSTEMS:
        raise ValueError(f"Klassifikator: {', '.join(SYSTEMS)}")
    assigned, skipped, by_code = 0, 0, {}
    for el in _candidates(f):
        if not overwrite and any(r["system"] == system for r in references(el)):
            skipped += 1
            continue
        cc = code_for(kind_of(el), system)
        if cc is None:
            skipped += 1
            continue
        assign(f, el, cc[0], cc[1], system)
        assigned += 1
        by_code[cc[0]] = by_code.get(cc[0], 0) + 1
    return {"system": system, "assigned": assigned, "skipped": skipped, "by_code": by_code}


def summary(f: ifcopenshell.file) -> dict:
    """ifc_meta uchun: klassifikatorlar va kodlar bo'yicha element soni."""
    systems = {c.Name: {"source": c.Source, "edition": c.Edition} for c in f.by_type("IfcClassification")}
    counts: dict[str, int] = {}
    classified = 0
    for el in _candidates(f):
        refs = references(el)
        if refs:
            classified += 1
        for r in refs:
            key = f"{r['system']}:{r['code']}"
            counts[key] = counts.get(key, 0) + 1
    return {"systems": systems, "classified": classified, "by_code": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:50])}
