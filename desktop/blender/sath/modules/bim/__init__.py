"""BIM moduli: parametrik GES obyektlari (Object.ges, IFC + Pset_GES_*), «Namuna GES». O'chirilganda Object.ges
ro'yxatdan chiqadi, lekin obyektlardagi ma'lumot saqlanadi (qayta yoqilganda qaytadi). IFC ga yozilmagan GES
obyekti bo'lsa modulni o'chirish rad etiladi (disable_blocker) — avval «IFC ga qo'llash»."""

from __future__ import annotations

import bpy

from ... import demo_plant, ges_objects
from ...core.panels import SathPanel


class SATH_PT_objects(SathPanel, bpy.types.Panel):
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
        for k, label, _ in ges_objects.KIND_ITEMS:
            grid.operator("sath.add_object", text=label).kind = k
        n_dirty = len(ges_objects.dirty_objects())
        if n_dirty:
            row = lay.row(align=True)
            row.label(text=f"{n_dirty} obyekt IFC bilan sinxronlanmagan", icon="ERROR")
            row.operator("sath.sync_ifc", text="IFC ga qo'llash", icon="EXPORT")
        lay.operator("sath.restore_ges", icon="FILE_REFRESH")
        obj = context.active_object
        if obj is None or not obj.ges.kind:
            return
        box = lay.box()
        box.label(text=f"{ges_objects.KIND_LABEL.get(obj.ges.kind, obj.ges.kind)}: {obj.name}", icon="MOD_BUILD")
        if obj.ges.inferred:
            col = box.column(align=True)
            col.label(text="O'lchamlar taxminiy — geometriya IFC dan olingan", icon="ERROR")
            if obj.ges.geom_dirty:
                col.label(text="O'lchamlar o'zgardi — mesh tasdiqlanguncha eski")
            col.operator("sath.confirm_dimensions", icon="CHECKMARK")
        for p in obj.ges.params:
            row = box.row()
            if p.ptype == "enum":
                row.prop(p, "value_enum", text=p.label)
            elif p.ptype == "int":
                row.prop(p, "value_int", text=p.label)
            else:
                row.prop(p, "value_float", text=p.label + (", m" if p.ptype == "length" else ""))
        box.operator("sath.rebuild_object", icon="FILE_REFRESH")


def _menu(layout, context):
    layout.operator_menu_enum("sath.add_object", "kind", text="GES obyekti")


def register(api):
    api.adopt("bim", ges_objects, demo_plant)
    api.register_classes("bim", [SATH_PT_objects])
    api.ui.main_menu("bim", _menu)


def _unsynced() -> list:
    """IFC ga yozilmagan GES obyektlari: ifc_dirty, yoki geom_dirty (taxminiy obyektdan tashqari — unda geom_dirty
    «o'lchamlar tasdiqlanmagan» degani, parametrlar sync_ifc bilan IFC da; «IFC ga qo'llash» uni tozalamaydi)."""
    return [o for o in ges_objects.by_kind_all() if o.ges.ifc_dirty or (o.ges.geom_dirty and not o.ges.inferred)]


def disable_blocker(api) -> str | None:
    """core/host.py set_enabled/module_toggle o'chirishdan OLDIN so'raydi: sabab qaytsa modul yoqiq qoladi."""
    n = len(_unsynced())
    if n:
        return f"bim modulini o'chirib bo'lmaydi: {n} obyekt IFC ga yozilmagan — avval «IFC ga qo'llash»"
    return None


def unregister(api):
    """Registry avval shuni, keyin teardown ni (ges_objects.unregister -> del Object.ges) chaqiradi — Object.ges hali bor.
    Foydalanuvchi o'chirishi disable_blocker bilan himoyalangan; bu yerga IFC ga yozilmagan obyekt bilan faqat addon
    o'chirilganda yoki qayta skanerda kelinadi."""
    if bpy.app.timers.is_registered(ges_objects.flush_pending):
        bpy.app.timers.unregister(ges_objects.flush_pending)
    ges_objects.flush_pending()  # kechiktirilgan mesh qayta qurishlar yakunlansin (timer Object.ges siz yiqilmasin)
    n = len(ges_objects.dirty_objects())
    sc = getattr(bpy.context, "scene", None)
    if n and sc is not None:
        sc.ges.status = (
            f"BIM moduli o'chirildi: {n} ta GES obyekti IFC ga yozilmagan — modul qayta yoqilmaguncha commit ularni o'z ichiga olmaydi"
        )
