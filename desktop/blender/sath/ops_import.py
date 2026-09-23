"""DXF/DWG (ezdxf yoki FreeCAD importeri orqali, qatlam → collection) va mesh (assimp) import."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import cad_read, converters, fc_engine, flows, ifc
from .shared import cad_common


def _collection(name: str, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def _polylines_to_curve(name: str, polylines, coll):
    """Polilinyalar (metrda) → Blender egri chizig'i. 2 nuqtadan kam (degenerat, nol uzunlikdagi) qirralar
    tashlanadi — `points.add(-1)` xatosi bo'lmaydi. Birorta ham chiziq bo'lmasa obyekt yaratilmaydi (None)."""
    polylines = [p for p in polylines if len(p) >= 2]
    if not polylines:
        return None
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for pts in polylines:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (float(p[0]), float(p[1]), float(p[2]), 1.0)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _edges_to_curve(name: str, shape, coll, k: float = 0.001):
    """FreeCAD qirralari → Blender egri chizig'i; k — FreeCAD qiymati (mm) → metr ko'paytuvchisi."""
    polylines = []
    for e in shape.Edges:
        try:
            pts = e.discretize(Deflection=0.5)
        except Exception:  # noqa: BLE001 — nol uzunlikdagi qirra
            continue
        polylines.append([(p.x * k, p.y * k, p.z * k) for p in pts])
    return _polylines_to_curve(name, polylines, coll)


def _layer_of(o):
    for p in o.InList:
        if p.TypeId == "App::FeaturePython" and "Layer" in p.Name:
            return p
    return None


ENGINE_ITEMS = [
    ("AUTO", "Avto", "FreeCAD o'rnatilgan bo'lsa FreeCAD importeri, aks holda ezdxf"),
    ("EZDXF", "ezdxf (FreeCAD siz)", "Addon ichidagi ezdxf: 3D yuzalar → mesh, chiziqlar → egri chiziq"),
    ("FREECAD", "FreeCAD importeri", "FreeCAD importDXF (FreeCAD kerak)"),
]


def assign_imported(objs, report: list | None = None) -> int:
    """Import qilingan MESH obyektlarni IFC elementga aylantiradi (Bonsai), aks holda commit ga tushmaydi (CAD-01).
    IFC sinfi nom bo'yicha (to'g'on → IfcWall, quvur → IfcPipeSegment, …; topilmasa IfcBuildingElementProxy).
    `sath_guid` joriy IFC dagi elementga to'g'ri kelsa — yangi element emas, o'sha element geometriyasi
    yangilanadi; bo'lmasa yangi element shu GUID ni oladi (CAD-07). Qaytaradi: IFC ga kirgan obyektlar soni."""
    report = report if report is not None else []
    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        return 0
    try:
        ifc._tool()
    except RuntimeError:
        report.append(f"Bonsai yoqilmagan — {len(meshes)} obyekt IFC ga biriktirilmadi (commit ga kirmaydi)")
        return 0
    n, failed = 0, []
    for ob in meshes:
        name = ob.name
        g = ob.get("sath_guid")
        existing = ifc.object_for_guid(g) if g else None
        if existing is not None and existing.type == "MESH" and existing.name != name:
            # Bonsai representatsiyasi mesh datablock ga bog'langan — joyida yangilaymiz (ges_objects kabi)
            m = existing.matrix_world.inverted() @ ob.matrix_world
            verts = [tuple(m @ v.co) for v in ob.data.vertices]
            faces = [tuple(p.vertices) for p in ob.data.polygons]
            old = ob.data
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(old)
            me = existing.data
            me.clear_geometry()
            me.from_pydata(verts, [], faces)
            me.update()
            ifc.update_representation(existing)
            n += 1
            continue
        cls = cad_common.classify_name(name.split("_", 1)[-1])[0]
        e = None
        for c in dict.fromkeys((cls, "IfcBuildingElementProxy")):
            try:
                e = ifc.assign_class(bpy.data.objects[name], c)
                break
            except Exception:  # noqa: BLE001 — sxemada yo'q sinf → proxy
                continue
        if e is None:
            failed.append(name)
            continue
        if g and existing is None:
            try:
                e.GlobalId = g
            except Exception:  # noqa: BLE001
                pass
        n += 1
    if failed:
        report.append(flows.unassigned_text(failed))
    return n


def import_dxf(
    context,
    path: Path,
    prepare: bool = True,
    unit: str = "AUTO",
    report: list | None = None,
    engine: str = "AUTO",
    assign_ifc: bool = False,
) -> int:
    """DWG/DXF → Blender. Qaytaradi: obyekt soni. engine — "AUTO" (FreeCAD bo'lsa FreeCAD, aks holda ezdxf),
    "EZDXF" (FreeCAD siz), "FREECAD". unit — "AUTO" ($INSUNITS) yoki UNITS kaliti; report — ogohlantirishlar;
    assign_ifc — 3D yuzalar IFC elementga aylantiriladi (chiziqlar IFC ga kirmaydi, commit da ogohlantiriladi)."""
    use_fc = engine == "FREECAD" or (engine == "AUTO" and fc_engine.available())
    before = set(bpy.data.objects)
    work = Path(tempfile.mkdtemp(prefix="sath-dxf-"))  # har import o'z papkasida (CAD-06), oxirida o'chiriladi
    try:
        if use_fc:
            n = _import_dxf_fc(fc_engine.load(), Path(path), work, prepare, unit, report)
        else:
            n = _import_dxf_ezdxf(Path(path), work, prepare, unit, report)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if assign_ifc:
        assign_imported([o for o in bpy.data.objects if o not in before], report)
    return n


def _import_dxf_ezdxf(path: Path, work: Path, prepare: bool, unit: str, report: list | None) -> int:
    """FreeCAD siz: ezdxf → 3D yuzalar (qatlam bo'yicha mesh) va chiziqlar (qatlam bo'yicha egri chiziq)."""
    from .shared import dxf_prepare

    if not dxf_prepare.ensure_ezdxf():
        raise RuntimeError("ezdxf topilmadi (extension wheel)")
    if path.suffix.lower() == ".dwg":
        path = converters.dwg_to_dxf(path, work)
    scene = cad_read.read_dxf(path, unit, prepare, work=work)
    if report is not None:
        report.extend(scene.warnings)
    root = _collection(f"DXF {path.stem}")
    n = 0
    for layer in sorted({*scene.faces, *scene.lines}):
        coll = _collection(f"{root.name} / {layer}", root)
        rgba = (*scene.colors.get(layer, (0.55, 0.55, 0.55)), 1.0)
        tris = scene.faces.get(layer)
        if tris:
            index: dict[tuple, int] = {}
            verts: list[tuple] = []
            faces = []
            for tri in tris:
                f = []
                for q in tri:
                    key = tuple(round(c, 9) for c in q)
                    if key not in index:
                        index[key] = len(verts)
                        verts.append(key)
                    f.append(index[key])
                if len(set(f)) == 3:
                    faces.append(tuple(f))
            me = bpy.data.meshes.new(f"DXF_{layer}")
            me.from_pydata(verts, [], faces)
            me.update()
            ob = bpy.data.objects.new(f"DXF_{layer}", me)
            ob.color = rgba
            coll.objects.link(ob)
            n += 1
        ob = _polylines_to_curve(f"DXF_{layer}_chiziq", scene.lines.get(layer, []), coll)
        if ob is not None:
            ob.color = rgba
            n += 1
    return n


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
            elif _edges_to_curve(name, sh, coll, k) is None:
                continue  # faqat degenerat qirralar
            n += 1
    finally:
        FreeCAD.closeDocument(doc.Name)
    return n


def import_mesh(
    context,
    path: Path,
    unit: str = "AUTO",
    axis: str = "AUTO",
    report: list | None = None,
    assign_ifc: bool = False,
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
    guids = cad_read.file_guids(path)
    created = []
    n = 0
    for m in assimp_load.load(str(path)):
        name, guid = cad_read.name_and_guid(str(m["name"]), guids)  # Sath eksporti: "Nom [GUID]" (CAD-07)
        me = bpy.data.meshes.new(name)
        verts = cad_read.transform_vertices(m["vertices"], res.scale, res.y_up)
        me.from_pydata(verts, [], [tuple(int(i) for i in f) for f in m["faces"]])
        me.update()
        ob = bpy.data.objects.new(f"{tag}_{name}", me)
        if guid:
            ob["sath_guid"] = guid
        if m.get("color"):
            ob.color = (*[float(c) for c in m["color"][:3]], 1.0)
        coll.objects.link(ob)
        created.append(ob)
        n += 1
    if assign_ifc:
        assign_imported(created, report)
    return n


class SATH_OT_import_dxf(bpy.types.Operator, ImportHelper):
    """DWG/DXF chizmani ochish (ezdxf yoki FreeCAD importeri, qatlamlar collection sifatida)"""

    bl_idname = "sath.import_dxf"
    bl_label = "DWG/DXF import"
    filename_ext = ".dxf"
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={"HIDDEN"})
    prepare: bpy.props.BoolProperty(name="Tekislash (bloklar, o'lchamlar, shtrix)", default=True)
    unit: bpy.props.EnumProperty(name="Birlik", items=cad_read.UNIT_ITEMS, default="AUTO")
    engine: bpy.props.EnumProperty(name="Importer", items=ENGINE_ITEMS, default="AUTO")
    assign_ifc: bpy.props.BoolProperty(
        name="IFC elementga aylantirish",
        description="3D yuzalar Bonsai orqali IFC elementi bo'ladi (aks holda commit ga kirmaydi)",
        default=True,
    )

    def execute(self, context):
        warnings: list[str] = []
        if self.engine == "FREECAD" and not fc_engine.available():
            self.report({"ERROR"}, "FreeCAD topilmadi — «ezdxf (FreeCAD siz)» importerini tanlang")
            return {"CANCELLED"}
        try:
            n = import_dxf(
                context, Path(self.filepath), self.prepare, self.unit, warnings, self.engine, self.assign_ifc
            )
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
    assign_ifc: bpy.props.BoolProperty(
        name="IFC elementga aylantirish",
        description="Obyektlar Bonsai orqali IFC elementi bo'ladi (aks holda commit ga kirmaydi)",
        default=True,
    )

    def execute(self, context):
        warnings: list[str] = []
        try:
            n = import_mesh(context, Path(self.filepath), self.unit, self.axis, warnings, self.assign_ifc)
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
