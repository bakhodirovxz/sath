"""FreeCAD ni Blender jarayoniga yuklash (retsept: docs/spike-blender-freecad.md) va stateless geometriya.

Qoida: FreeCAD site-packages sys.path OXIRIDA (Blender numpy, Bonsai ifcopenshell ustun). QApplication yo'q.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MM = 1000.0
WB_DIR = Path(__file__).resolve().parent / "wb"
_fc = None
_doc = None
_last_shape = None


def fc_home() -> str:
    env = os.environ.get("GES_FC_HOME")
    if env:
        return env
    try:
        from .prefs import prefs

        return prefs().fc_home
    except Exception:  # noqa: BLE001 — bpy kontekstisiz (pytest)
        return os.path.join(os.path.expanduser("~"), "Tools", "fc-py313")


def _layout(home: str) -> tuple[str, str]:
    """(root, site-packages): conda-forge (`Library/bin`) yoki rasmiy installer (`bin/Lib/site-packages`)."""
    if os.path.isdir(os.path.join(home, "Library", "bin")):
        return os.path.join(home, "Library"), os.path.join(home, "Lib", "site-packages")
    return home, os.path.join(home, "bin", "Lib", "site-packages")


def available() -> bool:
    root, _ = _layout(fc_home())
    return os.path.isfile(os.path.join(root, "bin", "FreeCAD.pyd")) or os.path.isfile(
        os.path.join(root, "lib", "FreeCAD.so")
    )


def load():
    """`import FreeCAD` — bir marta. RuntimeError: topilmadi."""
    global _fc
    if _fc is not None:
        return _fc
    home = fc_home()
    if not available():
        raise RuntimeError(f"FreeCAD topilmadi: {home} (Sozlamalar → Sath → FreeCAD papkasi)")
    root, site = _layout(home)
    fc_bin, fc_lib = os.path.join(root, "bin"), os.path.join(root, "lib")
    if hasattr(os, "add_dll_directory"):
        for d in (fc_bin, fc_lib):
            os.add_dll_directory(d)
    for d in (fc_bin, fc_lib, os.path.join(root, "Ext"), site, str(WB_DIR)):
        if d not in sys.path:
            sys.path.append(d)
    import FreeCAD

    _fc = FreeCAD
    return _fc


def doc():
    """Yashirin ishchi hujjat (obyektlar build dan keyin o'chiriladi)."""
    global _doc
    FreeCAD = load()
    if _doc is None or _doc.Name not in FreeCAD.listDocuments():
        _doc = FreeCAD.newDocument("GES_Engine")
    FreeCAD.setActiveDocument(_doc.Name)
    return _doc


def last_shape():
    return _last_shape


def shape_to_mesh(shape, mesh, tol: float = 0.5) -> None:
    """Part.Shape (mm) → bpy Mesh (m)."""
    import numpy as np

    verts, faces = shape.tessellate(tol)
    co = np.array([(v.x, v.y, v.z) for v in verts], dtype=np.float64) / MM
    mesh.clear_geometry()
    mesh.from_pydata(co.tolist(), [], faces)
    mesh.update()


def _wb():
    load()
    import ges_objects  # sath/wb (workbench nusxasi)

    return ges_objects


def ges_kinds() -> list[tuple[str, str]]:
    return [(k, v[0]) for k, v in _wb().OBJECTS.items()]


def ifc_class(freecad_ifc_type: str) -> str:
    """FreeCAD IfcType ("Pipe Segment") → IFC klass ("IfcPipeSegment")."""
    return "Ifc" + freecad_ifc_type.replace(" ", "")


def ges_schema(kind: str) -> list[dict]:
    """GES guruhidagi xususiyatlar: nom, izoh, tur, sukut (uzunlik metrda), enum variantlari."""
    d = doc()
    obj = _wb().make(kind)
    try:
        out = []
        for p in obj.PropertiesList:
            if obj.getGroupOfProperty(p) != "GES":
                continue
            t = obj.getTypeIdOfProperty(p)
            f: dict = {"name": p, "label": obj.getDocumentationOfProperty(p) or p, "items": []}
            if t == "App::PropertyLength":
                f.update(type="length", default=float(getattr(obj, p).Value) / MM)
            elif t == "App::PropertyEnumeration":
                f.update(
                    type="enum",
                    default=str(getattr(obj, p)),
                    items=list(obj.getEnumerationsOfProperty(p)),
                )
            elif t == "App::PropertyInteger":
                f.update(type="int", default=int(getattr(obj, p)))
            else:
                f.update(type="float", default=float(getattr(obj, p)))
            out.append(f)
        return out
    finally:
        d.removeObject(obj.Name)


@dataclass
class GesBuild:
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    ifc_class: str = "IfcBuildingElementProxy"
    psets: dict = field(default_factory=dict)


def _parse_props(raw: dict) -> dict[str, dict]:
    """IfcProperties "Pset;;IfcType;;value" → {pset: {name: value}} (workbench ifc_io._write_psets kabi)."""
    grouped: dict[str, dict] = {}
    for name, s in dict(raw).items():
        parts = str(s).split(";;")
        if len(parts) != 3:
            continue
        pset, ptype, value = parts
        if ptype in ("IfcReal", "IfcLengthMeasure", "IfcPositiveLengthMeasure"):
            try:
                value = float(value)
            except ValueError:
                pass
        elif ptype in ("IfcInteger", "IfcCountMeasure"):
            try:
                value = int(float(value))
            except ValueError:
                pass
        elif ptype == "IfcBoolean":
            value = str(value).lower() in ("true", "1", "yes")
        grouped.setdefault(pset, {})[name] = value
    return grouped


def ges_build(kind: str, params: dict) -> GesBuild:
    """Parametrlar (metr) → FreeCAD obyekt → tessellate (metr) + IFC klass + psetlar. Hujjat bo'sh qoladi."""
    global _last_shape
    d = doc()
    obj = _wb().make(kind)
    try:
        for p, v in params.items():
            if p not in obj.PropertiesList:
                continue
            t = obj.getTypeIdOfProperty(p)
            if t == "App::PropertyLength":
                setattr(obj, p, float(v) * MM)
            elif t == "App::PropertyInteger":
                setattr(obj, p, int(v))
            elif t == "App::PropertyEnumeration":
                setattr(obj, p, str(v))
            else:
                setattr(obj, p, float(v))
        d.recompute()
        shape = obj.Shape.copy()
        _last_shape = shape
        verts, faces = shape.tessellate(0.5)
        return GesBuild(
            verts=[(v.x / MM, v.y / MM, v.z / MM) for v in verts],
            faces=[tuple(f) for f in faces],
            ifc_class=ifc_class(obj.IfcType),
            psets=_parse_props(obj.IfcProperties),
        )
    finally:
        d.removeObject(obj.Name)
