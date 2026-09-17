"""GES parametrik obyektlari Blender da: parametrlar obyektda (Object.ges), geometriya FreeCAD dan (fc_engine),
IFC element + Pset_GES_* Bonsai da. Parametr o'zgarsa mesh va psetlar qayta quriladi."""

from __future__ import annotations

import os

import bpy

from . import fc_engine, ifc

KIND_ITEMS = [
    ("GES_Dam", "To'g'on", ""),
    ("GES_Penstock", "Bosimli quvur", ""),
    ("GES_Turbine", "Turbina agregati", ""),
    ("GES_Spillway", "Suv tashlagich", ""),
    ("GES_Powerhouse", "Mashina zali", ""),
    ("GES_Transformer", "Transformator", ""),
    ("GES_Intake", "Suv qabul qilgich", ""),
]
KIND_LABEL = {k: v for k, v, _ in KIND_ITEMS}


def _enum_items(self, context):
    return [(x, x, "") for x in self.items.split(";") if x]


def _changed(self, context):
    obj = self.id_data
    if getattr(obj, "ges", None) is not None and obj.ges.kind and not obj.ges.busy:
        rebuild(obj)


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


def _fill_schema(obj, kind: str) -> None:
    g = obj.ges
    g.busy = True
    try:
        g.kind = kind
        g.params.clear()
        for f in fc_engine.ges_schema(kind):
            p = g.params.add()
            p.name, p.label, p.ptype = f["name"], f["label"], f["type"]
            if f["type"] == "enum":
                p.items = ";".join(f["items"])
                p.value_enum = f["default"]
            elif f["type"] == "int":
                p.value_int = f["default"]
            else:
                p.value_float = f["default"]
    finally:
        g.busy = False


def rebuild(obj) -> None:
    """FreeCAD dan geometriya, mesh ni almashtirish, IFC representation + psetlarni yangilash."""
    g = obj.ges
    b = fc_engine.ges_build(g.kind, params_dict(obj))
    me = obj.data
    me.clear_geometry()
    me.from_pydata(b.verts, [], b.faces)
    me.update()
    e = ifc.entity(obj)
    if e is None:
        ifc.assign_class(obj, b.ifc_class, b.psets)
    else:
        ifc.update_representation(obj)
        ifc.write_psets(e, b.psets)


def add(context, kind: str, name: str | None = None):
    me = bpy.data.meshes.new(kind)
    obj = bpy.data.objects.new(name or KIND_LABEL[kind], me)
    context.scene.collection.objects.link(obj)
    _fill_schema(obj, kind)
    rebuild(obj)
    return obj


class SATH_OT_add_object(bpy.types.Operator):
    """GES obyekti qo'shish (FreeCAD geometriya, IFC element + Pset_GES_*)"""

    bl_idname = "sath.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    @classmethod
    def poll(cls, context):
        return fc_engine.available()

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
        if not fc_engine.available():
            lay.label(text="FreeCAD topilmadi — Sozlamalar → Sath", icon="ERROR")
            return
        grid = lay.grid_flow(columns=2, align=True)
        for k, label, _ in KIND_ITEMS:
            grid.operator("sath.add_object", text=label).kind = k
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


CLASSES = (GesParam, GesObject, SATH_OT_add_object, SATH_OT_rebuild_object, SATH_PT_objects)


def register():
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi (ui.py bilan bir xil)
        SATH_PT_objects.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)


def unregister():
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
