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


def file_guids(path: str | Path) -> dict[str, str]:
    """Obyekt nomi → GUID: FBX Custom Properties (sath_guid) yoki glTF extras (CAD-07)."""
    ext = Path(path).suffix.lower()
    if ext == ".fbx":
        out = {}
        for name, props in cad_common.fbx_info(path)["models"].items():
            g = cad_common.guid_from_props(props)
            if g:
                out[name] = g
        return out
    if ext in cad_common.GLTF_EXTS:
        return cad_common.gltf_node_guids(path)
    if ext == ".obj":
        return _obj_guids(Path(path))
    return {}


def _obj_guids(path: Path) -> dict[str, str]:
    """OBJ: assimp obyekt nomini birinchi bo'shliqgacha kesadi ("Devor [GUID]" → "Devor") — GUID ni `o`/`g`
    qatorlaridan olamiz; bir xil qisqa nomli bir nechta obyekt bo'lsa (noaniq) — olinmaydi."""
    found: dict[str, set[str]] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line[:2] in ("o ", "g "):
                    full = line[2:].strip()
                    clean, g = cad_common.split_guid(full)
                    if g and full.split():
                        found.setdefault(full.split()[0], set()).add(g)
    except OSError:
        return {}
    return {k: next(iter(v)) for k, v in found.items() if len(v) == 1}


def name_and_guid(name: str, guids: dict[str, str]) -> tuple[str, str | None]:
    """Sath eksportidagi "Nom [GUID]" → ("Nom", GUID); nomda bo'lmasa fayl xususiyatlaridan."""
    clean, g = cad_common.split_guid(name)
    return clean, g or guids.get(name) or guids.get(clean)
