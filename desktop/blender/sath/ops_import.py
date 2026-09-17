"""DXF/DWG (FreeCAD Import/Draft orqali, qatlam → collection) va mesh (assimp) import."""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import converters, fc_engine

MM = 0.001


def _collection(name: str, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def _edges_to_curve(name: str, shape, coll):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for e in shape.Edges:
        pts = e.discretize(Deflection=0.5)
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p.x * MM, p.y * MM, p.z * MM, 1.0)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _layer_of(o):
    for p in o.InList:
        if p.TypeId == "App::FeaturePython" and "Layer" in p.Name:
            return p
    return None


def import_dxf(context, path: Path, prepare: bool = True) -> int:
    """DWG/DXF → FreeCAD (importDXF, ezdxf bilan tekislangan) → Blender. Qaytaradi: obyekt soni."""
    FreeCAD = fc_engine.load()
    path = Path(path)
    work = Path(tempfile.gettempdir()) / "sath" / "dxf"
    work.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".dwg":
        path = converters.dwg_to_dxf(path, work)
    if prepare:
        from .shared import dxf_prepare

        (work / "prep").mkdir(exist_ok=True)
        path = Path(dxf_prepare.prepare(str(path), str(work / "prep"))[0])
    import importDXF

    doc = FreeCAD.newDocument("GES_DXF")
    FreeCAD.setActiveDocument(doc.Name)
    n = 0
    try:
        importDXF.insert(str(path), doc.Name)
        doc.recompute()
        root = _collection(f"DXF {path.stem}")
        for o in doc.Objects:
            sh = getattr(o, "Shape", None)
            if sh is None or sh.isNull():
                continue
            layer = _layer_of(o)
            coll = _collection(f"{root.name} / {layer.Label}", root) if layer else root
            name = f"DXF_{o.Label}"
            if sh.Faces:
                me = bpy.data.meshes.new(name)
                fc_engine.shape_to_mesh(sh, me)
                ob = bpy.data.objects.new(name, me)
                coll.objects.link(ob)
            else:
                _edges_to_curve(name, sh, coll)
            n += 1
    finally:
        FreeCAD.closeDocument(doc.Name)
    return n


def import_mesh(context, path: Path) -> int:
    """FBX/3DS/OBJ/... → assimp → mesh (Y-up → Z-up)."""
    from .shared import assimp_load

    path = Path(path)
    tag = path.suffix[1:].upper()
    coll = _collection(f"{tag} {path.stem}")
    n = 0
    for m in assimp_load.load(str(path)):
        me = bpy.data.meshes.new(m["name"])
        verts = [(float(v[0]), -float(v[2]), float(v[1])) for v in m["vertices"]]  # Y-up → Z-up
        me.from_pydata(verts, [], [tuple(int(i) for i in f) for f in m["faces"]])
        me.update()
        ob = bpy.data.objects.new(f"{tag}_{m['name']}", me)
        if m.get("color"):
            ob.color = (*[float(c) for c in m["color"][:3]], 1.0)
        coll.objects.link(ob)
        n += 1
    return n


class SATH_OT_import_dxf(bpy.types.Operator, ImportHelper):
    """DWG/DXF chizmani ochish (FreeCAD importeri, qatlamlar collection sifatida)"""

    bl_idname = "sath.import_dxf"
    bl_label = "DWG/DXF import"
    filename_ext = ".dxf"
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={"HIDDEN"})
    prepare: bpy.props.BoolProperty(name="Tekislash (bloklar, o'lchamlar, shtrix)", default=True)

    @classmethod
    def poll(cls, context):
        return fc_engine.available()

    def execute(self, context):
        try:
            n = import_dxf(context, Path(self.filepath), self.prepare)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{n} obyekt import qilindi")
        return {"FINISHED"}


class SATH_OT_import_mesh(bpy.types.Operator, ImportHelper):
    """FBX/3DS/OBJ/LWO/X/DAE mesh import (assimp)"""

    bl_idname = "sath.import_mesh"
    bl_label = "Mesh import (assimp)"
    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.3ds;*.obj;*.lwo;*.x;*.dae;*.blend", options={"HIDDEN"}
    )

    def execute(self, context):
        try:
            n = import_mesh(context, Path(self.filepath))
        except ImportError:
            self.report({"ERROR"}, "assimp-py o'rnatilmagan (extension wheel)")
            return {"CANCELLED"}
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{n} mesh import qilindi")
        return {"FINISHED"}


def _menu_import(self, context):
    self.layout.operator("sath.import_dxf", text="Sath: DWG/DXF (.dwg, .dxf)")
    self.layout.operator("sath.import_mesh", text="Sath: Mesh (assimp)")


CLASSES = (SATH_OT_import_dxf, SATH_OT_import_mesh)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
