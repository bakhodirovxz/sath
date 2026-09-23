"""FreeCAD import moduli: assimp (assimp-py, Mod/Ges/vendor) o'qiydigan formatlar — FBX, LWO/LWS, X, ASE, AC,
MS3D, COB, OGEX, B3D, MD2/MD3/MD5, SMD, NFF, AMF, IRRMESH, X3D, eski .blend …

Init.py da FreeCAD.addImportType(...) bilan ro'yxatga olinadi → Fayl → Ochish / Import ishlaydi.
Har obyekt — alohida Mesh::Feature (Blender/3ds Max dagi nomi, material rangi); Mesh ish muhitida
tahrirlash, Part ga aylantirish (Part → Create shape from mesh) mumkin. Birlik va yuqori o'q —
cad_common.detect_units_and_axis (FBX UnitScaleFactor/UpAxis; aniqlanmasa format odati + ogohlantirish).
"""

from __future__ import annotations

import os
from pathlib import Path

import FreeCAD


def _ensure_vendor() -> None:
    import sys

    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.append(str(vendor))


def units_and_axis(filename: str, y_up: bool | None = None, unit: str | None = None) -> tuple[float, bool, list]:
    """(fayl birligi → mm ko'paytuvchisi, Y-up → Z-up kerakmi, ogohlantirishlar) — umumiy cad_common orqali.
    Birlik aniqlanmasa xom qiymat mm deb olinadi (FreeCAD odati) va ogohlantiriladi."""
    from ges_workbench import cad_common

    info = cad_common.detect_units_and_axis(filename)
    warnings = []
    if unit:
        factor = cad_common.UNITS[unit] * 1000.0
    elif info.scale:
        factor = info.scale * 1000.0
    else:
        factor = 1.0
        warnings.append(f"{info.note or 'birlik aniqlanmadi'} — qiymatlar mm deb olindi")
    if y_up is None:
        y_up = info.up_axis == "Y"
        if info.axis_uncertain and info.up_axis:
            warnings.append(f"yuqori o'q faylda yo'q — {info.up_axis} deb olindi")
    return factor, y_up, warnings


def load_into(doc, filename: str, y_up: bool | None = None, unit: str | None = None) -> list:
    """Faylni hujjatga Mesh obyektlar sifatida qo'shadi; obyektlar ro'yxatini qaytaradi."""
    import Mesh

    _ensure_vendor()
    from ges_workbench import assimp_load

    if not assimp_load.available():
        raise RuntimeError(
            "assimp-py topilmadi (Mod/Ges/vendor) — glTF/OBJ ga eksport qilib oching"
        )
    factor, y_up, warnings = units_and_axis(filename, y_up, unit)
    for w in warnings:
        FreeCAD.Console.PrintWarning(f"Sath: {Path(filename).name}: {w}\n")
    objs = []
    for o in assimp_load.load(filename):
        v = o["vertices"] * factor  # fayl birligi → mm
        if y_up:  # (x, y, z) → (x, −z, y)
            v = v[:, [0, 2, 1]] * [1, -1, 1]
        pts = [tuple(map(float, p)) for p in v]
        # Mesh.Mesh((pts, faces)) ba'zi versiyalarda qulaydi — uchburchaklar ro'yxati ishonchli
        m = Mesh.Mesh()
        m.addFacets([(pts[int(a)], pts[int(b)], pts[int(c)]) for a, b, c in o["faces"]])
        obj = doc.addObject("Mesh::Feature", "Mesh")
        obj.Mesh = m
        obj.Label = o["name"]
        if FreeCAD.GuiUp and o["color"] and getattr(obj, "ViewObject", None) is not None:
            try:
                obj.ViewObject.ShapeColor = tuple(o["color"])
            except Exception:  # noqa: BLE001
                pass
        objs.append(obj)
    doc.recompute()
    FreeCAD.Console.PrintMessage(
        f"Sath: {Path(filename).name} — {len(objs)} obyekt (assimp){', Y-up → Z-up' if y_up else ''}\n"
    )
    return objs


def open(filename: str):  # noqa: A001 — FreeCAD import moduli protokoli
    doc = FreeCAD.newDocument(Path(filename).stem)
    load_into(doc, filename)
    if FreeCAD.GuiUp:
        try:
            import FreeCADGui

            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001
            pass
    return doc


def insert(filename: str, docname: str):
    doc = (
        FreeCAD.getDocument(docname)
        if docname in FreeCAD.listDocuments()
        else FreeCAD.newDocument(docname)
    )
    load_into(doc, filename)
    return doc


# Init.py uchun: (kengaytma, tavsif)
TYPES = [
    ("fbx", "Autodesk FBX"),
    ("lwo", "LightWave"),
    ("lws", "LightWave sahna"),
    ("x", "DirectX"),
    ("ase", "3ds Max ASE"),
    ("ac", "AC3D"),
    ("ms3d", "Milkshape 3D"),
    ("cob", "TrueSpace"),
    ("ogex", "OpenGEX"),
    ("b3d", "Blitz3D"),
    ("md2", "Quake II"),
    ("md3", "Quake III"),
    ("md5mesh", "Doom 3"),
    ("smd", "Valve SMD"),
    ("nff", "Neutral File Format"),
    ("amf", "AMF"),
    ("irrmesh", "Irrlicht"),
    ("x3d", "X3D"),
    ("blend", "Blender (eski 2.7x; yangilari uchun glTF)"),
]


def register() -> None:
    for ext, title in TYPES:
        try:
            FreeCAD.addImportType(f"{title} (*.{ext})", "ges_workbench.mesh_open")
        except Exception:  # noqa: BLE001
            pass
    if os.environ.get("GES_DEBUG"):
        FreeCAD.Console.PrintMessage(
            f"Sath: {len(TYPES)} mesh format ro'yxatga olindi (assimp)\n"
        )
