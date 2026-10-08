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


# --- DXF → Blender (FreeCAD siz, faqat ezdxf) ---------------------------------------------------------------------

LINEWORK_TYPES = {"LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE", "HELIX"}


@dataclass
class DxfScene:
    """DXF ning Blender ga tayyor geometriyasi (metrda, WCS): qatlam → uchburchaklar / polilinyalar."""

    faces: dict[str, list] = field(default_factory=dict)
    lines: dict[str, list] = field(default_factory=dict)
    colors: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _layer_rgb(doc, layer: str) -> tuple[float, float, float]:
    try:
        from ezdxf import colors as dxfcolors

        lay = doc.layers.get(layer)
        aci = lay.color if lay is not None and lay.color > 0 else 7
        if aci == 7:  # oq/qora (fonga qarab) → kulrang
            return (0.55, 0.55, 0.55)
        r, g, b = dxfcolors.aci2rgb(aci)
        return (r / 255, g / 255, b / 255)
    except Exception:  # noqa: BLE001
        return (0.55, 0.55, 0.55)


def read_dxf(path: str | Path, unit: str = "AUTO", prepare: bool = True, work: Path | None = None) -> DxfScene:
    """DXF → DxfScene, faqat ezdxf bilan (FreeCAD kerak emas). 3D yuzalar (3DFACE, SOLID, MESH, polyface; bloklar
    ichida ham) — uchburchaklar; 2D chiziqlar (bloklar, o'lchamlar, matn konturlari, shtrix — prepare bilan
    tekislangan) — polilinyalar. Birlik — $INSUNITS yoki `unit`. `work` — vaqtinchalik papka: buzuq DXF ni
    tuzatish nusxasi foydalanuvchi papkasiga emas, shu yerga yoziladi."""
    import shutil

    from ezdxf import path as dxfpath

    from .shared import dxf_prepare

    path = Path(path)
    res = resolve(path, unit, "Z", default_unit="mm")
    k = res.scale
    scene = DxfScene(warnings=list(res.warnings))
    if work is not None:
        src = Path(work) / path.name
        if src != path:
            shutil.copyfile(path, src)
        path = src
    doc = dxf_prepare._read(path)
    msp = doc.modelspace()
    walk: dict = {}
    for e in cad_common.iter_dxf_entities(msp, stats=walk):
        try:
            tris = cad_common.dxf_triangles(e)
        except Exception:  # noqa: BLE001 — buzuq element importni to'xtatmasin
            continue
        if tris:
            layer = str(e.dxf.get("layer", "0"))
            scene.faces.setdefault(layer, []).extend(
                [tuple(c * k for c in q) for q in tri] for tri in tris
            )
    if prepare:
        try:
            scene.stats.update(dxf_prepare.flatten(doc))  # bloklar, o'lchamlar, matn, shtrix → oddiy chiziqlar
        except Exception as e:  # noqa: BLE001
            scene.warnings.append(f"Tekislash to'liq bajarilmadi: {e}")
    for e in cad_common.iter_dxf_entities(msp):
        t = e.dxftype()
        if t not in LINEWORK_TYPES or (t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh)):
            continue
        try:
            pth = dxfpath.make_path(e)
            cv = list(pth.control_vertices())
            if len(cv) < 2:
                continue
            span = max(max(q[i] for q in cv) - min(q[i] for q in cv) for i in range(3))  # o'lcham
            pts = [(v.x * k, v.y * k, v.z * k) for v in pth.flattening(max(span, 1e-9) / 100)]
        except Exception:  # noqa: BLE001
            continue
        if len(pts) >= 2:  # nol/bitta nuqtali (degenerat) chiziqlar tashlanadi
            scene.lines.setdefault(str(e.dxf.get("layer", "0")), []).append(pts)
    for layer in {*scene.faces, *scene.lines}:
        scene.colors[layer] = _layer_rgb(doc, layer)
    scene.stats["insert"] = walk.get("insert", 0)
    if not scene.faces and not scene.lines:
        raise ValueError("DXF da geometriya topilmadi (3DFACE/MESH yoki chiziqlar)")
    return scene
