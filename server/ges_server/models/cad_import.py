"""CAD (B-rep) formatlar — STEP, IGES, BREP — OCP (OpenCASCADE, pip `cadquery-ocp`) bilan: har jism/qism
alohida obyekt (STEP/IGES dagi nomi va rangi bilan, XCAF), uchburchaklarga ajratiladi.
OCP ixtiyoriy (~100 MB): o'rnatilmagan bo'lsa `available()` False va foydalanuvchiga tushunarli xabar.
Birlik: OCCT STEP/IGES ni millimetrga keltiradi → "mm"."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

CAD_EXTS = {".step", ".stp", ".iges", ".igs", ".brep", ".brp"}


def available() -> bool:
    try:
        import OCP  # noqa: F401

        return True
    except ImportError:
        return False


def _name_of(label) -> str | None:
    from OCP.TDataStd import TDataStd_Name

    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        try:
            return attr.Get().ToExtString()
        except Exception:  # noqa: BLE001
            return str(attr.Get())
    return None


def _color_of(label, color_tool):
    from OCP.Quantity import Quantity_Color
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf

    c = Quantity_Color()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        try:
            if color_tool.GetColor_s(label, kind, c):
                return (float(c.Red()), float(c.Green()), float(c.Blue()))
        except Exception:  # noqa: BLE001
            continue
    return None


def _tessellate(shape, deflection: float) -> tuple[np.ndarray, np.ndarray]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    verts: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    base = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None and tri.NbTriangles() > 0:
            trsf = loc.Transformation()
            n = tri.NbNodes()
            pts = np.empty((n, 3))
            for i in range(1, n + 1):
                p = tri.Node(i).Transformed(trsf)
                pts[i - 1] = (p.X(), p.Y(), p.Z())
            m = tri.NbTriangles()
            idx = np.empty((m, 3), dtype=int)
            rev = face.Orientation() == TopAbs_REVERSED
            for i in range(1, m + 1):
                a, b, c = tri.Triangle(i).Get()
                idx[i - 1] = (a, c, b) if rev else (a, b, c)
            verts.append(pts)
            faces.append(idx - 1 + base)
            base += n
        exp.Next()
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    return np.vstack(verts), np.vstack(faces)


def _diag(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    if box.IsVoid():
        return 1000.0
    x0, y0, z0, x1, y1, z1 = box.Get()
    return float(np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)) or 1000.0


def _read_xcaf(path: Path):
    """STEP/IGES → XCAF hujjat (nomlar, ranglar, yig'ma daraxti)."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.InitDocument(doc)
    ext = path.suffix.lower()
    if ext in (".step", ".stp"):
        from OCP.STEPCAFControl import STEPCAFControl_Reader

        reader = STEPCAFControl_Reader()
        reader.SetColorMode(True)
        reader.SetNameMode(True)
        reader.SetLayerMode(True)
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Reader

        reader = IGESCAFControl_Reader()
        reader.SetColorMode(True)
        reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError(f"{ext.upper()} faylni o'qib bo'lmadi (OpenCASCADE)")
    if not reader.Transfer(doc):
        raise ValueError(f"{ext.upper()} geometriyasi o'tkazilmadi (OpenCASCADE)")
    return doc


def load(path: str | os.PathLike, max_objects: int = 5000) -> list[dict]:
    """→ [{name, vertices (mm), faces, color}] — har jism alohida (yig'ma daraxti bo'ylab)."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    path = Path(path)
    ext = path.suffix.lower()
    out: list[dict] = []
    if ext in (".brep", ".brp"):
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Shape

        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
            raise ValueError("BREP faylni o'qib bo'lmadi")
        defl = _diag(shape) * 0.002
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        solids = []
        while exp.More():
            solids.append(exp.Current())
            exp.Next()
        for i, s in enumerate(solids or [shape]):
            v, f = _tessellate(s, defl)
            if len(f):
                out.append(
                    {"name": f"{path.stem}_{i + 1}", "vertices": v, "faces": f, "color": None}
                )
        return out

    doc = _read_xcaf(path)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    seen: set[int] = set()

    def visit(label, inherited_name: str | None, depth: int) -> None:
        if len(out) >= max_objects or depth > 32:
            return
        name = _name_of(label) or inherited_name
        if shape_tool.IsAssembly_s(label) or (shape_tool.IsReference_s(label) and depth == 0):
            comps = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                visit(comps.Value(i), name, depth + 1)
            return
        if shape_tool.IsReference_s(label):
            ref = label.__class__()
            shape_tool.GetReferredShape_s(label, ref)
            # komponent shakli — joylashuvi bilan; nom/rang komponentdan yoki asl qismdan
            shape = shape_tool.GetShape_s(label)
            if shape_tool.IsAssembly_s(ref):
                comps = TDF_LabelSequence()
                shape_tool.GetComponents_s(ref, comps)
                for i in range(1, comps.Length() + 1):
                    visit(comps.Value(i), _name_of(ref) or name, depth + 1)
                return
            color = _color_of(label, color_tool) or _color_of(ref, color_tool)
            name = _name_of(label) or _name_of(ref) or inherited_name
        else:
            shape = shape_tool.GetShape_s(label)
            color = _color_of(label, color_tool)
        if shape.IsNull():
            return
        key = hash(shape)
        if key in seen:
            return
        seen.add(key)
        if shape.ShapeType() == TopAbs_COMPOUND:
            # bir label ostida bir nechta jism — har biri alohida
            exp = TopExp_Explorer(shape, TopAbs_SOLID)
            k = 0
            while exp.More() and len(out) < max_objects:
                s = exp.Current()
                v, f = _tessellate(s, _diag(s) * 0.002)
                if len(f):
                    k += 1
                    out.append(
                        {
                            "name": f"{name or path.stem}_{k}",
                            "vertices": v,
                            "faces": f,
                            "color": color,
                        }
                    )
                exp.Next()
            if k:
                return
        v, f = _tessellate(shape, _diag(shape) * 0.002)
        if len(f):
            out.append({"name": name or path.stem, "vertices": v, "faces": f, "color": color})

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        visit(free.Value(i), None, 0)
    if not out:
        raise ValueError("CAD faylda jism topilmadi")
    return out
