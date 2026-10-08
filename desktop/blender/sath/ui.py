"""N-panel «Sath» yorliqlari."""

from __future__ import annotations

import os

import bpy

from . import session
from .core import host, keys, perms
from .core.panels import cur, draw_list


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


class SATH_PT_server(GesPanel, bpy.types.Panel):
    bl_order = 0
    bl_label = "Server"

    def draw(self, context):
        from .prefs import prefs

        p, s = prefs(), context.scene.ges
        col = self.layout.column()
        if session.is_logged_in():
            u = session.user() or {}
            col.label(text=f"{u.get('username', '')} @ {p.server}", icon="LINKED")
            col.operator("sath.logout", icon="UNLINKED")
            if s.update_version:
                box = col.box()
                box.label(text=f"Yangi versiya: {s.update_version}", icon="IMPORT")
                row = box.row(align=True)
                row.operator("sath.download_update", text="Installer").kind = "installer"
                row.operator("sath.download_update", text="Zip").kind = "zip"
        else:
            col.prop(p, "server")
            col.prop(p, "username")
            sec = context.window_manager.sath_secret  # .blend ga saqlanmaydi (CODE-05)
            col.prop(sec, "password")
            col.prop(sec, "otp")
            col.operator("sath.connect", icon="LINKED")
        if s.status:
            col.label(text=s.status, icon="INFO")


class SATH_PT_model(GesPanel, bpy.types.Panel):
    bl_order = 1
    bl_label = "Model"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.label(text="Loyihalar")
        draw_list(lay, s, "projects", "projects_index", 3, "sath.refresh_projects")
        lay.label(text="Modellar")
        draw_list(lay, s, "models", "models_index", 3, "sath.refresh_models")
        row = lay.row(align=True)
        row.prop(s, "new_model_name", text="")
        row.operator("sath.create_model", text="", icon="ADD")
        lay.label(text="Versiyalar")
        draw_list(lay, s, "versions", "versions_index", 4, "sath.refresh_versions")
        row = lay.row(align=True)
        row.operator("sath.open_version", icon="IMPORT")
        if perms.can("model.write", context):  # spec §2: viewer da commit ko'rinmaydi
            row.operator("sath.commit", icon="EXPORT")
        if s.head_conflict_id >= 0:  # VCS-01: commit 409 — model serverda yangilangan
            box = lay.box()
            box.label(text="Model serverda yangilangan — commit qabul qilinmadi", icon="ERROR")
            box.operator("sath.pull_head", icon="IMPORT")
        row = lay.row(align=True)
        if perms.can("cr.create", context):
            row.operator("sath.submit", icon="CHECKMARK")
        row.operator("sath.open_web", icon="URL")
        if s.model_id:
            lay.label(text=f"Ochiq: {s.model_name} v{s.version_number}", icon="FILE_TICK")


class SATH_PT_notifications(GesPanel, bpy.types.Panel):
    bl_order = 1000
    bl_label = "Bildirishnomalar"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        draw_list(lay, s, "notifications", "notifications_index", 5, "sath.notifications")
        n = cur(s.notifications, s.notifications_index)
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
        lay.operator("sath.notifications")
        if hasattr(bpy.types, "SATH_OT_reset_workspaces"):  # Sath app template (bundle) faol bo'lsa
            lay.operator("sath.reset_workspaces", icon="WORKSPACE")
        host.draw_menus(lay, context)  # modul bandlari (bim: «GES obyekti», io, sim …) — har biri separator bilan


def _menu_header(self, context):
    self.layout.menu("SATH_MT_main")


_keymap_offs: list = []


def _register_keymap():
    """Ctrl+Shift+G → «Sath» menyusi: «3D View» va «Object Mode» da. Rejim keymapi 3D View dan oldin ishlaydi,
    u yerdagi standart collection.objects_add_active ni ataylab yopamiz (core/keys.ALLOWED)."""
    for km_name, space in (("3D View", "VIEW_3D"), ("Object Mode", "EMPTY")):
        _kmi, off = keys.add("core", "wm.call_menu", "G", km_name=km_name, space_type=space,
                             ctrl=True, shift=True, name="SATH_MT_main")  # fmt: skip
        _keymap_offs.append(off)


CLASSES = [SATH_MT_main, SATH_UL_simple, SATH_PT_server, SATH_PT_model, SATH_PT_notifications]


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
    for off in reversed(_keymap_offs):
        off()
    _keymap_offs.clear()
    bpy.types.VIEW3D_MT_editor_menus.remove(_menu_header)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
