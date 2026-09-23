"""Import mantig'i (bpy siz, pytest bilan tekshiriladi): birlik/o'q tanlovi — shared/cad_common asosida (CAD-04)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .shared import cad_common

# Operator EnumProperty lari uchun
UNIT_ITEMS = [
    ("AUTO", "Avto (fayldan)", "Fayldagi birlik ($INSUNITS, FBX UnitScaleFactor, glTF — metr)"),
    ("m", "Metr", ""),
    ("cm", "Santimetr", ""),
    ("mm", "Millimetr", ""),
    ("in", "Dyuym", ""),
    ("ft", "Fut", ""),
]
AXIS_ITEMS = [
    ("AUTO", "Avto (fayldan)", "Fayldagi yuqori o'q (glTF/FBX), bo'lmasa format odati"),
    ("Y", "Y yuqoriga", "Y-up → Z-up o'giriladi"),
    ("Z", "Z yuqoriga", "O'girilmaydi"),
]


@dataclass
class Resolved:
    """Tanlangan masshtab (1 fayl birligi necha metr) va Y → Z o'girish; ogohlantirishlar."""

    scale: float
    y_up: bool
    info: cad_common.UnitInfo
    warnings: list[str] = field(default_factory=list)


def resolve(path: str | Path, unit: str = "AUTO", axis: str = "AUTO", default_unit: str = "m") -> Resolved:
    """Foydalanuvchi tanlovi (unit/axis) ustun; AUTO — fayldagi ma'lumot; aniqlanmasa default_unit va ogohlantirish
    (jimgina taxmin emas — foydalanuvchi import oynasida birlik/o'qni tanlashi mumkin)."""
    info = cad_common.detect_units_and_axis(path)
    warnings: list[str] = []
    if unit != "AUTO":
        scale = cad_common.UNITS[unit]
    elif info.scale:
        scale = info.scale
    else:
        scale = cad_common.UNITS[default_unit]
        warnings.append(
            f"{info.note or 'Birlik aniqlanmadi'} — {default_unit} deb olindi (import oynasida birlikni tanlang)"
        )
    if axis != "AUTO":
        y_up = axis == "Y"
    else:
        y_up = info.up_axis == "Y"
        if info.axis_uncertain and info.up_axis:
            warnings.append(f"Yuqori o'q faylda yo'q — {info.up_axis} deb olindi (kerak bo'lsa o'qni tanlang)")
    return Resolved(scale, y_up, info, warnings)


def freecad_dxf_factor(res: Resolved) -> float:
    """FreeCAD importDXF $INSUNITS bo'yicha mm ga keltiradi (birliksiz — xom qiymat, ya'ni mm deb oladi).
    FreeCAD qiymati → metr ko'paytuvchisi, tanlangan birlikni hisobga olib."""
    file_scale = res.info.scale or 0.001  # FreeCAD ning o'z taxmini
    return res.scale * 0.001 / file_scale


def transform_vertices(verts, scale: float, y_up: bool) -> list[tuple[float, float, float]]:
    """Fayl birligi → metr, kerak bo'lsa Y-up → Z-up."""
    out = []
    for v in verts:
        x, y, z = float(v[0]) * scale, float(v[1]) * scale, float(v[2]) * scale
        out.append((x, -z, y) if y_up else (x, y, z))
    return out
