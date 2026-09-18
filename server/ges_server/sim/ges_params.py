"""IFC modeldan GES parametrlarini olish (Pset_GES_* xususiyatlari) → simulyatsiya formasi uchun taklif.

Desktop GES obyektlari va namunaviy modellar shu Pset larni yozadi:
  Pset_GES_Turbine:  Turi, Quvvat_MW, Napor_m, Sarf_m3s, FIK
  Pset_GES_Penstock: Diametr_m, Uzunlik_m, Gadirbudirlik_mm, Material
  Pset_GES_Spillway: Kenglik_m, OstonaBelgisi_m, SarfKoeff, Darvozalar
  Pset_GES_Dam:      Balandlik_m, Uzunlik_m, GerbBelgisi_m, Turi, GerbKengligi_m, TagKengligi_m, TagBelgisi_m
  Pset_GES_Tailrace: Kenglik_m, Nishab, Manning_n, TagBelgisi_m, HisobiyQuyiByef_m, HisobiySarf_m3s
  Pset_GES_Generator: Quvvat_MVA, FIK, TemirUlushi, Qutblar, Aylanish_rpm
"""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _psets(el) -> dict[str, dict]:
    return ifcopenshell.util.element.get_psets(el) or {}


def extract(path: Path) -> dict:
    f = ifcopenshell.open(str(path))
    units, penstocks, spillways, dams, tailraces, generators = [], [], [], [], [], []
    for el in f.by_type("IfcProduct"):
        ps = _psets(el)
        if "Pset_GES_Turbine" in ps:
            p = ps["Pset_GES_Turbine"]
            units.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or f"Agregat {len(units) + 1}",
                    "type": str(p.get("Turi") or "Francis"),
                    "rated_power_mw": _num(p.get("Quvvat_MW"), 25.0),
                    "rated_head_m": _num(p.get("Napor_m"), 45.0),
                    "rated_flow_m3s": _num(p.get("Sarf_m3s"), 62.0),
                    "max_efficiency": _num(p.get("FIK"), 0.92),
                }
            )
        if "Pset_GES_Penstock" in ps:
            p = ps["Pset_GES_Penstock"]
            penstocks.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or "",
                    "length_m": _num(p.get("Uzunlik_m"), 100.0),
                    "diameter_m": _num(p.get("Diametr_m"), 3.0),
                    "roughness_mm": _num(p.get("Gadirbudirlik_mm"), 0.1),
                    "material": str(p.get("Material") or ""),
                }
            )
        if "Pset_GES_Spillway" in ps:
            p = ps["Pset_GES_Spillway"]
            spillways.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or "",
                    "crest_m": _num(p.get("OstonaBelgisi_m"), 0.0),
                    "width_m": _num(p.get("Kenglik_m"), 10.0),
                    "coefficient": _num(p.get("SarfKoeff"), 0.49),
                    "gates": int(_num(p.get("Darvozalar"), 1) or 1),
                }
            )
        if "Pset_GES_Dam" in ps:
            p = ps["Pset_GES_Dam"]
            dams.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or "",
                    "type": str(p.get("Turi") or ""),
                    "height_m": _num(p.get("Balandlik_m")),
                    "length_m": _num(p.get("Uzunlik_m")),
                    "crest_elevation_m": _num(p.get("GerbBelgisi_m")),
                    "crest_width_m": _num(p.get("GerbKengligi_m")),
                    "base_width_m": _num(p.get("TagKengligi_m")),
                    "base_elevation_m": _num(p.get("TagBelgisi_m")),
                }
            )
        if "Pset_GES_Tailrace" in ps:
            p = ps["Pset_GES_Tailrace"]
            tailraces.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or "",
                    "width_m": _num(p.get("Kenglik_m"), 20.0),
                    "slope": _num(p.get("Nishab"), 0.001),
                    "manning": _num(p.get("Manning_n"), 0.03),
                    "bed_elevation_m": _num(p.get("TagBelgisi_m")),
                    "design_tailwater_m": _num(p.get("HisobiyQuyiByef_m")),
                    "design_flow_m3s": _num(p.get("HisobiySarf_m3s")),
                }
            )
        if "Pset_GES_Generator" in ps:
            p = ps["Pset_GES_Generator"]
            generators.append(
                {
                    "guid": el.GlobalId,
                    "name": el.Name or "",
                    "rated_mva": _num(p.get("Quvvat_MVA"), 30.0),
                    "eta_max": _num(p.get("FIK"), 0.985),
                    "iron_frac": _num(p.get("TemirUlushi"), 0.4),
                    "poles": int(_num(p.get("Qutblar"), 24) or 24),
                    "rpm": _num(p.get("Aylanish_rpm")),
                }
            )
    return {
        "units": units, "penstocks": penstocks, "spillways": spillways, "dams": dams,
        "tailraces": tailraces, "generators": generators,
    }  # fmt: skip
