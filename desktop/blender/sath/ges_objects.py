"""GES parametrik obyektlari Blender da: parametrlar obyektda (Object.ges), sxema va geometriya — sof Python
`shared/ges_kinds` (+ `shared/geom`, numpy; FreeCAD siz), IFC element + Pset_GES_* Bonsai da. Mesh Blender ga
numpy massivlari bilan (`foreach_set`) uzatiladi. Parametr o'zgarsa mesh va psetlar qayta quriladi."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import bpy
import numpy as np

from . import ifc
from .core import events, ui_tasks
from .shared import ges_kinds

KIND_ITEMS = [(k, s.label, "") for k, s in ges_kinds.KINDS.items()]
KIND_LABEL = {k: s.label for k, s in ges_kinds.KINDS.items()}


def _enum_items(self, context):
    return [(x, x, "") for x in self.items.split(";") if x]


_pending: set[str] = set()
DEBOUNCE = 0.15


def flush_pending():
    """Kechiktirilgan qayta qurish: parametrni sudrab o'zgartirganda har qadamda emas, to'planib bir marta."""
    names = list(_pending)
    _pending.clear()
    for n in names:
        obj = bpy.data.objects.get(n)
        if obj is not None and obj.ges.kind:
            try:
                rebuild(obj)
            except Exception as e:  # noqa: BLE001 — bitta obyekt xatosi qolganini to'xtatmasin
                print("sath: qayta qurish xatosi", n, e)
    return None


def _changed(self, context):
    obj = self.id_data
    if getattr(obj, "ges", None) is None or not obj.ges.kind or obj.ges.busy:
        return
    if bpy.app.background:  # testlar: darhol
        rebuild(obj)
        return
    _pending.add(obj.name)
    if not bpy.app.timers.is_registered(flush_pending):
        bpy.app.timers.register(flush_pending, first_interval=DEBOUNCE)


class GesParam(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ptype: bpy.props.StringProperty()  # length | float | int | enum
    items: bpy.props.StringProperty()  # enum: "a;b;c"
    value_float: bpy.props.FloatProperty(precision=3, update=_changed)
    value_int: bpy.props.IntProperty(update=_changed)
    value_enum: bpy.props.EnumProperty(items=_enum_items, update=_changed)


class GesObject(bpy.types.PropertyGroup):
    kind: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty(default=False)
    role: bpy.props.StringProperty(description="Egizakdagi roli: unit:1, gen:1, draft:1, penstock:1, dam, tailrace…")
    params: bpy.props.CollectionProperty(type=GesParam)


def params_dict(obj) -> dict:
    out = {}
    for p in obj.ges.params:
        if p.ptype == "enum":
            out[p.name] = p.value_enum
        elif p.ptype == "int":
            out[p.name] = p.value_int
        else:
            out[p.name] = p.value_float
    return out


def set_params(obj, **values) -> None:
    """Bir nechta parametrni bir yo'la o'rnatib, bir marta qayta qurish (har birida rebuild emas)."""
    g = obj.ges
    g.busy = True
    try:
        for p in g.params:
            if p.name not in values:
                continue
            v = values[p.name]
            if p.ptype == "enum":
                p.value_enum = str(v)
            elif p.ptype == "int":
                p.value_int = int(v)
            else:
                p.value_float = float(v)
    finally:
        g.busy = False
    rebuild(obj)


def by_role(role: str):
    return next((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.role == role), None)


def by_kind_all() -> list:
    return [o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind]


def by_kind(kind: str) -> list:
    return sorted((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind == kind), key=lambda o: o.name)


def _fill_schema(obj, kind: str, values: dict | None = None) -> None:
    """Sxema (ges_kinds) → obj.ges.params; values — parametrlar (tekshiriladi), yo'q bo'lsa defaultlar."""
    vals = ges_kinds.normalize(kind, values)
    g = obj.ges
    g.busy = True
    try:
        g.kind = kind
        g.params.clear()
        for prm in ges_kinds.spec(kind).params:
            p = g.params.add()
            p.name, p.label, p.ptype = prm.name, prm.label, prm.ptype
            v = vals[prm.name]
            if prm.ptype == "enum":
                p.items = ";".join(prm.items)
                p.value_enum = v
            elif prm.ptype == "int":
                p.value_int = v
            else:
                p.value_float = v
    finally:
        g.busy = False


def set_mesh(me, verts: np.ndarray, faces: np.ndarray) -> None:
    """(V float64, F int64 uchburchak) → bpy Mesh, numpy foreach_set bilan (from_pydata Python ro'yxatlarisiz)."""
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"set_mesh: yuzlar (N, 3) uchburchak bo'lishi kerak, berilgan shakl {faces.shape}")
    me.clear_geometry()
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(faces, dtype=np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update(calc_edges=True)


def rebuild_mesh(obj) -> None:
    """Parametrlardan mesh (ges_kinds.build). Yaroqsiz parametr — ValueError (matn foydalanuvchiga)."""
    v, f = ges_kinds.build(obj.ges.kind, params_dict(obj))
    set_mesh(obj.data, v, f)


def write_ifc(obj) -> None:
    """IFC element (yo'q bo'lsa assign_class) yoki representation + Pset_GES_* + Pset_SathParametric (K2: tur, rol,
    barcha parametrlar — qayta ochilganda to'liq tiklanadi)."""
    g = obj.ges
    p = params_dict(obj)
    ps = {**ges_kinds.psets(g.kind, p), **ges_kinds.parametric_pset(g.kind, g.role, p)}
    e = ifc.entity(obj)
    if e is None:
        e = ifc.assign_class(obj, ges_kinds.spec(g.kind).ifc_class)
    else:
        ifc.update_representation(obj)
    ifc.write_psets(e, ps, text=("Params",))


def rebuild(obj) -> None:
    """Mesh (ges_kinds) + IFC (representation, psetlar)."""
    rebuild_mesh(obj)
    write_ifc(obj)


def default_role(kind: str) -> str:
    """Rol berilmagan qo'lda qo'shilgan obyekt uchun: yagona tur — o'z roli (band bo'lmasa), indeksli tur (unit:, gen:, …) —
    birinchi bo'sh raqam (demo_plant sxemasi). Band bo'lsa — "" (egizak bog'lamaydi, lekin jim ham emas)."""
    role = ges_kinds.spec(kind).role
    taken = {o.ges.role for o in by_kind_all() if o.ges.role}
    if not role.endswith(":"):
        return "" if role in taken else role
    n = 1
    while f"{role}{n}" in taken:
        n += 1
    return f"{role}{n}"


def add(context, kind: str, name: str | None = None, role: str = "", **params):
    """GES obyekti: parametrlar darhol beriladi (keyin set_params bilan qayta qurish shart emas). `role` berilmasa —
    turning birinchi bo'sh roli (`default_role`)."""
    s = ges_kinds.spec(kind)
    ges_kinds.validate(kind, params)  # avval tekshiruv: yaroqsiz parametrda data-block yaratilmaydi
    ifc.ensure_project()  # GUI da create_project sahnani qayta quradi (obyekt havolasi eskiradi)
    me = bpy.data.meshes.new(kind)
    obj = bpy.data.objects.new(name or s.label, me)
    try:
        context.scene.collection.objects.link(obj)
        obj.color = (*s.color, 1.0)
        _fill_schema(obj, kind, params)
        obj.ges.role = role or default_role(kind)
        rebuild(obj)
    except Exception:
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(me)
        raise
    return obj


@dataclass
class RestoreReport:
    restored: list[str] = field(default_factory=list)  # Pset_SathParametric dan (to'liq)
    inferred: list[str] = field(default_factory=list)  # Pset_GES_* dan (geometriya parametrlari qisman, rol taxminiy)
    unknown: list[tuple[str, str]] = field(default_factory=list)  # (obyekt, sabab)
    warnings: list[str] = field(default_factory=list)

    def text(self) -> str:
        s = f"GES: {len(self.restored)} tiklandi, {len(self.inferred)} taxminiy, {len(self.unknown)} noma'lum"
        if self.unknown:
            s += " — " + "; ".join(f"{n}: {why}" for n, why in self.unknown[:3])
        return s


LAST_REPORT = RestoreReport()


def _set_role(obj, role: str) -> None:
    g = obj.ges
    g.busy = True  # K4: rol o'zgarishi «ifc_dirty» qo'ymasin (tiklash IFC ni o'zgartirmaydi)
    try:
        g.role = role
    finally:
        g.busy = False


def restore_from_ifc() -> RestoreReport:
    """K2: IFC elementli obyektlar → obj.ges (kind, role, params) Pset_SathParametric dan, bo'lmasa Pset_GES_* dan
    (rollar X bo'yicha). Mesh qayta QURILMAYDI — GUID va geometriya IFC dagidek qoladi; tanilmaganlar hisobotda."""
    import ifcopenshell.util.element as ue

    global LAST_REPORT
    rep = RestoreReport()
    guess = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or getattr(obj, "ges", None) is None:
            continue
        e = ifc.entity(obj)
        if e is None:
            continue
        try:
            r = ges_kinds.from_psets(ue.get_psets(e))
        except ges_kinds.UnknownKind as err:
            rep.unknown.append((obj.name, str(err)))
            continue
        except Exception as err:  # noqa: BLE001 — bitta buzuq element butun faylni to'xtatmasin
            rep.unknown.append((obj.name, f"{type(err).__name__}: {err}"))
            continue
        if r is None:
            continue
        try:
            _fill_schema(obj, r.kind, r.params)
            _set_role(obj, r.role)
            obj.color = (*ges_kinds.spec(r.kind).color, 1.0)
        except Exception as err:  # noqa: BLE001
            rep.unknown.append((obj.name, f"{type(err).__name__}: {err}"))
            continue
        rep.warnings += [f"{obj.name}: {w}" for w in r.warnings]
        if r.source == "parametric":
            rep.restored.append(obj.name)
        else:
            rep.inferred.append(obj.name)
            guess.append((obj.name, r.kind, obj.matrix_world.translation.x))
    if guess:
        taken = {o.ges.role for o in by_kind_all() if o.ges.role}
        for name, role in ges_kinds.infer_roles(guess).items():
            if role not in taken:
                _set_role(bpy.data.objects[name], role)
    LAST_REPORT = rep
    return rep


def _on_ifc_loaded(payload: dict) -> None:
    rep = restore_from_ifc()
    if rep.unknown or rep.warnings:
        ui_tasks.show_error("GES tiklash", rep.text() + ("; " + "; ".join(rep.warnings[:3]) if rep.warnings else ""))
    elif rep.restored or rep.inferred:
        ui_tasks.status(rep.text())


class SATH_OT_restore_ges(bpy.types.Operator):
    """GES obyektlarining tur, rol va parametrlarini IFC psetlaridan qayta tiklash (mesh o'zgarmaydi). Bonsai ning o'z File → Open i bilan ochilgan modelda shu tugmani bosing"""

    bl_idname = "sath.restore_ges"
    bl_label = "IFC dan tiklash"

    def execute(self, context):
        rep = restore_from_ifc()
        self.report({"WARNING"} if rep.unknown else {"INFO"}, rep.text())
        return {"FINISHED"}


class SATH_OT_add_object(bpy.types.Operator):
    """GES obyekti qo'shish (sof Python geometriya, IFC element + Pset_GES_*)"""

    bl_idname = "sath.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    def execute(self, context):
        try:
            obj = add(context, self.kind)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Obyekt yaratilmadi: {e}")
            return {"CANCELLED"}
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"{KIND_LABEL[self.kind]} qo'shildi")
        return {"FINISHED"}


class SATH_OT_rebuild_object(bpy.types.Operator):
    """Tanlangan GES obyektlarini qayta hisoblash"""

    bl_idname = "sath.rebuild_object"
    bl_label = "Qayta qurish"

    def execute(self, context):
        n = 0
        for o in context.view_layer.objects:
            if o.select_get() and o.ges.kind:
                rebuild(o)
                n += 1
        self.report({"INFO"}, f"{n} obyekt qayta qurildi")
        return {"FINISHED"}


class SATH_PT_objects(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Sath"
    bl_label = "GES obyektlari"

    def draw(self, context):
        lay = self.layout
        s = context.scene.ges
        box = lay.box()
        row = box.row(align=True)
        row.prop(s, "demo_head")
        row.prop(s, "demo_units")
        row = box.row(align=True)
        row.prop(s, "demo_unit_mw")
        row.operator("sath.build_demo_plant", icon="ADD")
        if s.twin_note:
            box.label(text=s.twin_note, icon="INFO")
        grid = lay.grid_flow(columns=2, align=True)
        for k, label, _ in KIND_ITEMS:
            grid.operator("sath.add_object", text=label).kind = k
        lay.operator("sath.restore_ges", icon="FILE_REFRESH")
        obj = context.active_object
        if obj is None or not obj.ges.kind:
            return
        box = lay.box()
        box.label(text=f"{KIND_LABEL.get(obj.ges.kind, obj.ges.kind)}: {obj.name}", icon="MOD_BUILD")
        for p in obj.ges.params:
            row = box.row()
            if p.ptype == "enum":
                row.prop(p, "value_enum", text=p.label)
            elif p.ptype == "int":
                row.prop(p, "value_int", text=p.label)
            else:
                row.prop(p, "value_float", text=p.label + (", m" if p.ptype == "length" else ""))
        box.operator("sath.rebuild_object", icon="FILE_REFRESH")


CLASSES = (GesParam, GesObject, SATH_OT_add_object, SATH_OT_rebuild_object, SATH_OT_restore_ges, SATH_PT_objects)


_off_loaded = None


def register():
    global _off_loaded
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi (ui.py bilan bir xil)
        SATH_PT_objects.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)
    _off_loaded = events.subscribe("ifc.loaded", _on_ifc_loaded)


def unregister():
    global _off_loaded
    if _off_loaded is not None:
        _off_loaded()
        _off_loaded = None
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
