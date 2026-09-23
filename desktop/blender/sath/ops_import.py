"""DXF/DWG (FreeCAD Import/Draft orqali, qatlam → collection) va mesh (assimp) import."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import cad_read, converters, fc_engine


def _collection(name: str, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def _edges_to_curve(name: str, shape, coll, k: float = 0.001):
    """FreeCAD qirralari → Blender egri chizig'i; k — FreeCAD qiymati (mm) → metr ko'paytuvchisi."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for e in shape.Edges:
        pts = e.discretize(Deflection=0.5)
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p.x * k, p.y * k, p.z * k, 1.0)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _layer_of(o):
    for p in o.InList:
        if p.TypeId == "App::FeaturePython" and "Layer" in p.Name:
            return p
    return None


def import_dxf(
    context, path: Path, prepare: bool = True, unit: str = "AUTO", report: list | None = None
) -> int:
    """DWG/DXF → FreeCAD (importDXF, ezdxf bilan tekislangan) → Blender. Qaytaradi: obyekt soni.
    unit — "AUTO" ($INSUNITS) yoki UNITS kaliti; report — ogohlantirishlar ro'yxati (CAD-04)."""
    FreeCAD = fc_engine.load()
    work = Path(tempfile.mkdtemp(prefix="sath-dxf-"))  # har import o'z papkasida (CAD-06), oxirida o'chiriladi
    try:
        return _import_dxf_fc(FreeCAD, Path(path), work, prepare, unit, report)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _import_dxf_fc(FreeCAD, path: Path, work: Path, prepare: bool, unit: str, report: list | None) -> int:
    if path.suffix.lower() == ".dwg":
        path = converters.dwg_to_dxf(path, work)
    res = cad_read.resolve(path, unit, "Z", default_unit="mm")
    k = cad_read.freecad_dxf_factor(res)  # FreeCAD mm → metr (tanlangan birlik bilan)
    if report is not None:
        report.extend(res.warnings)
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
                fc_engine.shape_to_mesh(sh, me)  # mm → m (×0.001)
                if abs(k - 0.001) > 1e-12:
                    from mathutils import Matrix

                    me.transform(Matrix.Scale(k / 0.001, 4))
                ob = bpy.data.objects.new(name, me)
                coll.objects.link(ob)
            else:
                _edges_to_curve(name, sh, coll, k)
            n += 1
    finally:
        FreeCAD.closeDocument(doc.Name)
    return n


def import_mesh(
    context, path: Path, unit: str = "AUTO", axis: str = "AUTO", report: list | None = None
) -> int:
    """FBX/3DS/OBJ/... → assimp → mesh. Birlik va yuqori o'q — fayldan (FBX UnitScaleFactor/UpAxis) yoki
    foydalanuvchi tanlovi; aniqlanmasa ogohlantirish (CAD-04)."""
    from .shared import assimp_load

    path = Path(path)
    res = cad_read.resolve(path, unit, axis, default_unit="m")
    if report is not None:
        report.extend(res.warnings)
    tag = path.suffix[1:].upper()
    coll = _collection(f"{tag} {path.stem}")
    n = 0
    for m in assimp_load.load(str(path)):
        me = bpy.data.meshes.new(m["name"])
        verts = cad_read.transform_vertices(m["vertices"], res.scale, res.y_up)
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
    unit: bpy.props.EnumProperty(name="Birlik", items=cad_read.UNIT_ITEMS, default="AUTO")

    @classmethod
    def poll(cls, context):
        return fc_engine.available()

    def execute(self, context):
        warnings: list[str] = []
        try:
            n = import_dxf(context, Path(self.filepath), self.prepare, self.unit, warnings)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        for w in warnings:
            self.report({"WARNING"}, w)
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
    unit: bpy.props.EnumProperty(name="Birlik", items=cad_read.UNIT_ITEMS, default="AUTO")
    axis: bpy.props.EnumProperty(name="Yuqori o'q", items=cad_read.AXIS_ITEMS, default="AUTO")

    def execute(self, context):
        warnings: list[str] = []
        try:
            n = import_mesh(context, Path(self.filepath), self.unit, self.axis, warnings)
        except ImportError:
            self.report({"ERROR"}, "assimp-py o'rnatilmagan (extension wheel)")
            return {"CANCELLED"}
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        for w in warnings:
            self.report({"WARNING"}, w)
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
