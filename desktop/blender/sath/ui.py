"""N-panel «Sath» yorliqlari."""

from __future__ import annotations

import os

import bpy

from . import session


class GesPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sath"


class SATH_UL_simple(bpy.types.UIList):
    """name | state | col2 | col3 | col4 (bo'sh ustunlar ko'rsatilmaydi)."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text=item.name)
        for c in (item.state, item.col2, item.col3, item.col4):
            if c:
                row.label(text=c)


def _list(layout, s, coll, idx, rows=4, refresh_op=None):
    """UIList + yangilash tugmasi."""
    row = layout.row()
    row.template_list("SATH_UL_simple", coll, s, coll, s, idx, rows=rows)
    if refresh_op:
        row.operator(refresh_op, text="", icon="FILE_REFRESH")


def _cur(coll, idx):
    return coll[idx] if 0 <= idx < len(coll) else None


class SATH_PT_server(GesPanel, bpy.types.Panel):
    bl_label = "Server"

    def draw(self, context):
        from .prefs import prefs

        p, s = prefs(), context.scene.ges
        col = self.layout.column()
        if session.is_logged_in():
            u = session.user() or {}
            col.label(text=f"{u.get('username', '')} @ {p.server}", icon="LINKED")
            col.operator("sath.logout", icon="UNLINKED")
        else:
            col.prop(p, "server")
            col.prop(p, "username")
            col.prop(s, "password")
            col.operator("sath.connect", icon="LINKED")
        if s.status:
            col.label(text=s.status, icon="INFO")


class SATH_PT_model(GesPanel, bpy.types.Panel):
    bl_label = "Model"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.label(text="Loyihalar")
        _list(lay, s, "projects", "projects_index", 3, "sath.refresh_projects")
        lay.label(text="Modellar")
        _list(lay, s, "models", "models_index", 3, "sath.refresh_models")
        row = lay.row(align=True)
        row.prop(s, "new_model_name", text="")
        row.operator("sath.create_model", text="", icon="ADD")
        lay.label(text="Versiyalar")
        _list(lay, s, "versions", "versions_index", 4, "sath.refresh_versions")
        row = lay.row(align=True)
        row.operator("sath.open_version", icon="IMPORT")
        row.operator("sath.commit", icon="EXPORT")
        row = lay.row(align=True)
        row.operator("sath.submit", icon="CHECKMARK")
        row.operator("sath.open_web", icon="URL")
        if s.model_id:
            lay.label(text=f"Ochiq: {s.model_name} v{s.version_number}", icon="FILE_TICK")


class SATH_PT_review(GesPanel, bpy.types.Panel):
    bl_label = "Taqriz va issue lar"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        box = lay.box()
        box.label(text="Versiyalar farqi", icon="MOD_DIFFERENCE")
        row = box.row(align=True)
        row.operator("sath.diff")
        row.operator("sath.clear_diff", text="", icon="X")
        if s.diff_note:
            box.label(text=s.diff_note)

        box = lay.box()
        box.label(text="Issue lar", icon="ERROR")
        _list(box, s, "issues", "issues_index", 4, "sath.refresh_issues")
        for line in s.issue_detail.splitlines()[:8]:
            box.label(text=line)
        row = box.row(align=True)
        row.operator("sath.goto_view", icon="CAMERA_DATA")
        row.operator("sath.new_issue", icon="ADD")
        row = box.row(align=True)
        row.prop(s, "comment_text", text="")
        row.operator("sath.comment_issue", text="", icon="PLAY")

        box = lay.box()
        role = f" · {s.my_role}" if s.my_role else ""
        box.label(text=f"Tasdiqlash so'rovlari{role}", icon="CHECKMARK")
        _list(box, s, "crs", "crs_index", 4, "sath.refresh_crs")
        for line in s.cr_detail.splitlines()[:8]:
            box.label(text=line)
        cr = _cur(s.crs, s.crs_index)
        approver = s.my_role == "approver"
        st = cr.col4 if cr else ""
        open_ = st in ("open", "changes_requested", "approved")
        row = box.row(align=True)
        r1 = row.row()
        r1.enabled = approver and open_ and st != "approved"
        r1.operator("sath.decide", text="Ma'qullash").decision = "approve"
        r2 = row.row()
        r2.enabled = approver and open_
        r2.operator("sath.decide", text="O'zgartirish so'rash").decision = "request_changes"
        row = box.row(align=True)
        r1 = row.row()
        r1.enabled = approver and st == "approved"
        r1.operator("sath.merge_cr")
        r2 = row.row()
        r2.enabled = bool(cr) and st not in ("merged", "rejected")
        r2.operator("sath.reject_cr")
        box.operator("sath.decide", text="Faqat izoh qoldirish").decision = "comment"


class SATH_PT_sim(GesPanel, bpy.types.Panel):
    bl_label = "Simulyatsiya"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        row = lay.row(align=True)
        row.operator("sath.sim_catalog", icon="FILE_REFRESH")
        row.operator("sath.safety_check", icon="CHECKMARK")
        _list(lay, s, "sim_kinds", "sim_kind_index", 4)
        k = _cur(s.sim_kinds, s.sim_kind_index)
        if k and k.col4:
            lay.label(text=k.col4[:90])
        for f in s.sim_fields:
            if f.ftype == "bool":
                lay.prop(f, "value_bool", text=f.label)
            elif f.ftype == "select":
                lay.prop(f, "value_sel", text=f.label)
            else:
                lay.prop(f, "value_str", text=f.label)
        row = lay.row(align=True)
        row.operator("sath.sim_prefill", text="Pasportdan").src = "site"
        row.operator("sath.sim_prefill", text="Modeldan").src = "model"
        row.operator("sath.sim_run", icon="PLAY")
        if s.sim_status:
            lay.label(text=s.sim_status, icon="INFO")
        for r in s.sim_results:
            icon = "CHECKMARK" if r.state == "ok" else "ERROR" if r.state == "fail" else "DOT"
            lay.label(text=f"{r.name}: {r.col2}", icon=icon)
        row = lay.row(align=True)
        row.operator("sath.sim_water", icon="MOD_FLUIDSIM")
        row.operator("sath.open_web", text="Webda (grafik, hisobot)", icon="URL").tab = "sim"
        if s.safety_head:
            box = lay.box()
            box.label(text=s.safety_head, icon="SHIELD")
            for r in s.safety_rows:
                box.label(text=f"{r.name} — {r.state}: {r.col2}"[:100])


class SATH_PT_monitor(GesPanel, bpy.types.Panel):
    bl_label = "Monitoring (SCADA)"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.operator(
            "sath.monitor_toggle",
            text="To'xtatish" if s.monitor_on else "Boshlash",
            icon="PAUSE" if s.monitor_on else "PLAY",
            depress=s.monitor_on,
        )
        row = lay.row(align=True)
        row.prop(s, "monitor_color")
        row.prop(s, "monitor_water")
        if s.monitor_status:
            lay.label(text=s.monitor_status, icon="INFO")
        _list(lay, s, "sensors", "sensors_index", 6)
        row = lay.row(align=True)
        row.operator("sath.show_sensor", icon="RESTRICT_SELECT_OFF")
        row.operator("sath.open_web", text="Webda (HMI)", icon="URL").tab = "mon"


class SATH_PT_import(GesPanel, bpy.types.Panel):
    bl_label = "Import"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("sath.import_dxf", icon="GREASEPENCIL")
        col.operator("sath.import_mesh", icon="MESH_DATA")


class SATH_PT_notifications(GesPanel, bpy.types.Panel):
    bl_label = "Bildirishnomalar"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        _list(lay, s, "notifications", "notifications_index", 5, "sath.notifications")
        n = _cur(s.notifications, s.notifications_index)
        if n:
            lay.label(text=n.col4 or n.name)
        row = lay.row(align=True)
        row.operator("sath.mark_read", text="Tanlangan o'qildi").all = False
        row.operator("sath.mark_read", text="Hammasi").all = True


class SATH_MT_main(bpy.types.Menu):
    """3D View sarlavhasidagi «Sath» menyusi (Ctrl+Shift+G)."""

    bl_label = "Sath"
    bl_idname = "SATH_MT_main"

    def draw(self, context):
        lay = self.layout
        lay.operator("sath.logout" if session.is_logged_in() else "sath.connect")
        lay.separator()
        lay.operator("sath.open_version")
        lay.operator("sath.commit")
        lay.operator("sath.submit")
        lay.operator("sath.open_web")
        lay.separator()
        lay.operator_menu_enum("sath.add_object", "kind", text="GES obyekti")
        lay.operator("sath.import_dxf")
        lay.operator("sath.import_mesh")
        lay.separator()
        lay.operator("sath.sim_catalog")
        lay.operator("sath.safety_check")
        lay.operator("sath.monitor_toggle")
        lay.operator("sath.notifications")


def _menu_header(self, context):
    self.layout.menu("SATH_MT_main")


_keymaps: list = []


def _register_keymap():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # headless
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    kmi = km.keymap_items.new("wm.call_menu", "G", "PRESS", ctrl=True, shift=True)
    kmi.properties.name = "SATH_MT_main"
    _keymaps.append((km, kmi))


CLASSES = [SATH_MT_main, SATH_UL_simple, SATH_PT_server, SATH_PT_model, SATH_PT_review, SATH_PT_sim, SATH_PT_monitor, SATH_PT_import, SATH_PT_notifications]


def register():
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi: barcha panellar ochiq, «Item» yorlig'ida chizilsin
        for c in CLASSES:
            if hasattr(c, "bl_options") and "DEFAULT_CLOSED" in c.bl_options:
                c.bl_options = set(c.bl_options) - {"DEFAULT_CLOSED"}
            if getattr(c, "bl_category", None) == "Sath":
                c.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_editor_menus.append(_menu_header)
    _register_keymap()


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    bpy.types.VIEW3D_MT_editor_menus.remove(_menu_header)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
