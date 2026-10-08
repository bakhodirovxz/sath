"""DXF/DWG (ezdxf, qatlam → collection; DWG — dwg2dxf/ODA orqali) va mesh (assimp) import."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import cad_read, converters, flows, ifc
from .core.ifc_ops import IfcOperator, SathOpError
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
    assign_ifc: bool = False,
) -> int:
    """DWG/DXF → Blender (ezdxf; DWG avval dwg2dxf/ODA bilan DXF ga). Qaytaradi: obyekt soni. unit — "AUTO"
    ($INSUNITS) yoki UNITS kaliti; report — ogohlantirishlar; assign_ifc — 3D yuzalar IFC elementga aylantiriladi
    (chiziqlar IFC ga kirmaydi, commit da ogohlantiriladi)."""
    before = set(bpy.data.objects)
    work = Path(tempfile.mkdtemp(prefix="sath-dxf-"))  # har import o'z papkasida (CAD-06), oxirida o'chiriladi
    try:
        n = _import_dxf_ezdxf(Path(path), work, prepare, unit, report)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if assign_ifc:
        assign_imported([o for o in bpy.data.objects if o not in before], report)
    return n


def _import_dxf_ezdxf(path: Path, work: Path, prepare: bool, unit: str, report: list | None) -> int:
    """ezdxf → 3D yuzalar (qatlam bo'yicha mesh) va chiziqlar (qatlam bo'yicha egri chiziq)."""
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
    if not assimp_load.available():  # CAD-09: assimp-py wheel faqat Windows uchun — boshqa platformada
        return _import_mesh_native(context, path, report, assign_ifc)
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


NATIVE_IMPORTERS = {".fbx": "import_scene.fbx", ".obj": "wm.obj_import"}


def _import_mesh_native(context, path: Path, report: list | None, assign_ifc: bool) -> int:
    """assimp-py yo'q (Linux/macOS): FBX/OBJ — Blender ning o'z importeri (birlik/o'qni o'zi hisoblaydi), nomdagi
    "[GUID]" → sath_guid; boshqa formatlar — tushunarli xato."""
    op = NATIVE_IMPORTERS.get(path.suffix.lower())
    if op is None:
        raise ImportError(
            f"assimp-py bu platformada yo'q — {path.suffix.upper()} ni FBX/OBJ/glTF ga eksport qilib oching"
        )
    before = set(bpy.data.objects)
    mod, name = op.split(".")
    getattr(getattr(bpy.ops, mod), name)(filepath=str(path))
    guids = cad_read.file_guids(path)
    created = []
    for ob in [o for o in bpy.data.objects if o not in before]:
        clean, guid = cad_read.name_and_guid(ob.name, guids)
        if guid:
            ob["sath_guid"] = guid
            ob.name = clean
        created.append(ob)
    if report is not None:
        report.append("assimp-py yo'q — Blender importeri ishlatildi")
    if assign_ifc:
        assign_imported(created, report)
    return len([o for o in created if o.type == "MESH"])


class SATH_OT_import_dxf(IfcOperator, bpy.types.Operator, ImportHelper):
    """DWG/DXF chizmani ochish (ezdxf, qatlamlar collection sifatida; import va IFC ga aylantirish — bitta undo qadami)"""

    bl_idname = "sath.import_dxf"
    bl_label = "DWG/DXF import"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".dxf"
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={"HIDDEN"})
    prepare: bpy.props.BoolProperty(name="Tekislash (bloklar, o'lchamlar, shtrix)", default=True)
    unit: bpy.props.EnumProperty(name="Birlik", items=cad_read.UNIT_ITEMS, default="AUTO")
    assign_ifc: bpy.props.BoolProperty(
        name="IFC elementga aylantirish",
        description="3D yuzalar Bonsai orqali IFC elementi bo'ladi (aks holda commit ga kirmaydi)",
        default=True,
    )

    @property
    def sath_needs_project(self):
        return bool(self.assign_ifc)  # IFC ga aylantirilmasa loyiha yaratilmaydi

    def _execute(self, context):
        warnings: list[str] = []
        try:
            n = import_dxf(context, Path(self.filepath), self.prepare, self.unit, warnings, assign_ifc=self.assign_ifc)
        except Exception as e:  # noqa: BLE001
            raise SathOpError(f"Import xatosi: {e}") from e
        for w in warnings:
            self.report({"WARNING"}, w)
        self.report({"INFO"}, f"{n} obyekt import qilindi")
        return {"FINISHED"}


class SATH_OT_import_mesh(IfcOperator, bpy.types.Operator, ImportHelper):
    """FBX/3DS/OBJ/LWO/X/DAE mesh import (assimp; import va IFC ga aylantirish — bitta undo qadami)"""

    bl_idname = "sath.import_mesh"
    bl_label = "Mesh import (assimp)"
    bl_options = {"REGISTER", "UNDO"}
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

    @property
    def sath_needs_project(self):
        return bool(self.assign_ifc)  # IFC ga aylantirilmasa loyiha yaratilmaydi

    def _execute(self, context):
        warnings: list[str] = []
        try:
            n = import_mesh(context, Path(self.filepath), self.unit, self.axis, warnings, self.assign_ifc)
        except ImportError as e:
            raise SathOpError(str(e) or "assimp-py o'rnatilmagan (extension wheel)") from e
        except Exception as e:  # noqa: BLE001
            raise SathOpError(f"Import xatosi: {e}") from e
        for w in warnings:
            self.report({"WARNING"}, w)
        self.report({"INFO"}, f"{n} mesh import qilindi")
        return {"FINISHED"}


class SATH_OT_assign_ifc(IfcOperator, bpy.types.Operator):
    """Nomlari berilgan mesh obyektlarni IFC elementga aylantirish (bitta undo qadami)"""

    bl_idname = "sath.assign_ifc"
    bl_label = "IFC ga qo'shish"
    bl_options = {"REGISTER", "UNDO"}
    names: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def _execute(self, context):
        objs = [bpy.data.objects[n] for n in self.names.split(";") if n in bpy.data.objects]
        n = assign_imported(objs)
        self.report({"INFO"}, f"{n} obyekt IFC ga qo'shildi")
        return {"FINISHED"}


def _menu_import(self, context):
    self.layout.operator("sath.import_dxf", text="Sath: DWG/DXF (.dwg, .dxf)")
    self.layout.operator("sath.import_mesh", text="Sath: Mesh (assimp)")


CLASSES = (SATH_OT_import_dxf, SATH_OT_import_mesh, SATH_OT_assign_ifc)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
