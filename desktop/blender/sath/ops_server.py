"""Server operatorlari: ulanish, loyiha/model/versiya ro'yxatlari, ochish, commit, tasdiqqa yuborish, web,
bildirishnomalar."""

from __future__ import annotations

import webbrowser

import bpy

from . import flows, ifc, props, session, viewpoint
from .prefs import prefs
from .shared.server_client import ServerError


def guard(op, fn):
    """ServerError/RuntimeError → op.report; muvaffaqiyat → True."""
    try:
        fn()
        return True
    except (ServerError, RuntimeError) as e:
        op.report({"ERROR"}, str(getattr(e, "message", e)))
        return False


def _sel(coll, index):
    return coll[index] if 0 <= index < len(coll) else None


class SATH_OT_connect(bpy.types.Operator):
    """Sath serveriga kirish"""

    bl_idname = "sath.connect"
    bl_label = "Ulanish"

    def execute(self, context):
        p, s = prefs(), context.scene.ges

        def do():
            u = session.login(p.server, p.username, s.password)
            s.password = ""
            s.status = f"{u['username']} sifatida kirildi"
            pkg = flows.newer_package(session.client(), flows.ADDON_VERSION)
            s.update_version = pkg["version"] if pkg else ""
            if pkg:
                self.report({"WARNING"}, flows.check_update(session.client(), flows.ADDON_VERSION) or "")
            n = flows.unread_summary(session.client())
            if n:
                s.status += f" · {n}"
            props.fill(s.projects, flows.project_rows(session.client()))
            s.projects_index = 0 if len(s.projects) else -1  # update → modellar

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_download_update(bpy.types.Operator):
    """Serverdagi yangi Sath paketini brauzerda yuklab olish (installer yoki zip)"""

    bl_idname = "sath.download_update"
    bl_label = "Yangilanishni yuklab olish"
    kind: bpy.props.EnumProperty(items=[("installer", "Installer", ""), ("zip", "Zip", "")])

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        def do():
            latest = session.client().desktop_latest()
            if not latest:
                raise RuntimeError("Serverda desktop paketi yo'q")
            pkg = next((f for f in latest.get("files", []) if f["kind"] == self.kind), latest)
            webbrowser.open(flows.download_url(session.client(), prefs().server, pkg))
            self.report({"INFO"}, f"Yuklab olinmoqda: {pkg.get('name', latest['version'])}")

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_logout(bpy.types.Operator):
    bl_idname = "sath.logout"
    bl_label = "Chiqish"

    def execute(self, context):
        session.logout()
        s = context.scene.ges
        for c in (s.projects, s.models, s.versions):
            c.clear()
        s.status = ""
        return {"FINISHED"}


class SATH_OT_refresh_projects(bpy.types.Operator):
    bl_idname = "sath.refresh_projects"
    bl_label = "Loyihalarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        ok = guard(self, lambda: props.fill(s.projects, flows.project_rows(session.client())))
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_refresh_models(bpy.types.Operator):
    bl_idname = "sath.refresh_models"
    bl_label = "Modellarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        s.models.clear()
        s.versions.clear()
        if p is None:
            return {"FINISHED"}
        ok = guard(self, lambda: props.fill(s.models, flows.model_rows(session.client(), p.item_id)))
        s.models_index = 0 if len(s.models) else -1  # update → versiyalar
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_refresh_versions(bpy.types.Operator):
    bl_idname = "sath.refresh_versions"
    bl_label = "Versiyalarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        m = _sel(s.models, s.models_index)
        s.versions.clear()
        if m is None:
            return {"FINISHED"}
        ok = guard(
            self, lambda: props.fill(s.versions, flows.version_rows(session.client(), m.item_id))
        )
        s.versions_index = 0 if len(s.versions) else -1
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_create_model(bpy.types.Operator):
    """Tanlangan loyihada yangi model"""

    bl_idname = "sath.create_model"
    bl_label = "Yangi model"

    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        if p is None or not s.new_model_name.strip():
            self.report({"ERROR"}, "Loyiha va model nomini tanlang")
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().create_model(p.item_id, s.new_model_name.strip()))
        if ok:
            s.new_model_name = ""
            bpy.ops.sath.refresh_models()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_open_version(bpy.types.Operator):
    """Tanlangan versiyani yuklab, Bonsai da ochish"""

    bl_idname = "sath.open_version"
    bl_label = "Ochish"

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and _sel(s.versions, s.versions_index) is not None

    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        m = _sel(s.models, s.models_index)
        v = _sel(s.versions, s.versions_index)

        info = {
            "project_id": p.item_id, "model_id": m.item_id, "version_id": v.item_id,
            "version_number": v.number, "model_name": m.name,
            "status": f"{p.name} — {m.name} v{v.number} ochildi",
        }  # fmt: skip
        snap = props.snapshot(s)  # Bonsai fresh session sahnani almashtiradi

        def do():
            path = flows.download_version(
                session.client(), {"id": m.item_id}, {"id": v.item_id, "number": v.number}
            )
            if ifc.load(path):
                props.restore(bpy.context.scene.ges, snap)
            sc = bpy.context.scene.ges
            for k, val in info.items():
                setattr(sc, k, val)

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_commit(bpy.types.Operator):
    """Joriy IFC ni serverga yangi versiya sifatida yuklash"""

    bl_idname = "sath.commit"
    bl_label = "Commit (yangi versiya)"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and ifc.file() is not None

    def invoke(self, context, event):
        s = context.scene.ges
        if not s.model_id:
            m = _sel(s.models, s.models_index)
            if m is None:
                self.report({"ERROR"}, "Qaysi modelga yuklash? Model panelida modelni tanlang")
                return {"CANCELLED"}
            s.model_id, s.model_name = m.item_id, m.name
            p = _sel(s.projects, s.projects_index)
            s.project_id = p.item_id if p else 0
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        s = context.scene.ges
        parent = f" (ota: v{s.version_number})" if s.version_id else ""
        self.layout.label(text=f"Model: {s.model_name}{parent}")
        self.layout.prop(s, "commit_message")
        self.layout.prop(s, "submit_after_commit")

    def execute(self, context):
        s = context.scene.ges

        def do():
            path = ifc.save(flows.cache_dir() / f"commit_m{s.model_id}.ifc")
            r = flows.commit(
                session.client(),
                s.model_id,
                path,
                s.commit_message.strip(),
                s.version_id or None,
                s.submit_after_commit,
            )
            v = r["version"]
            s.version_id, s.version_number = v["id"], v["number"]
            s.status = f"v{v['number']} yuklandi" + (" va tasdiqqa yuborildi" if r["cr"] else "")
            s.commit_message = ""
            self.report({"INFO"}, s.status)

        if not guard(self, do):
            return {"CANCELLED"}
        bpy.ops.sath.refresh_versions()
        return {"FINISHED"}


class SATH_OT_submit(bpy.types.Operator):
    """Joriy versiya uchun tasdiqlash so'rovi"""

    bl_idname = "sath.submit"
    bl_label = "Tasdiqqa yuborish"
    title: bpy.props.StringProperty(name="Sarlavha")

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and bool(s.model_id and s.version_id)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        s = context.scene.ges
        if not self.title.strip():
            self.report({"ERROR"}, "Sarlavha kiriting")
            return {"CANCELLED"}

        def do():
            cr = session.client().create_change_request(s.model_id, s.version_id, self.title.strip())
            self.report({"INFO"}, f"So'rov #{cr['id']} ochildi. Tasdiqlovchi webda ko'rib chiqadi.")

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_open_web(bpy.types.Operator):
    """Joriy model (tanlangan element bilan) brauzerda"""

    bl_idname = "sath.open_web"
    bl_label = "Webda ochish"
    tab: bpy.props.StringProperty(default="")

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def execute(self, context):
        s = context.scene.ges
        q = f"?v={s.version_id}" if s.version_id else "?"
        if self.tab:
            q += f"&tab={self.tab}"
        sel = [g for g in (ifc.guid(o) for o in viewpoint._selected(context)) if g]
        if sel:
            q += f"&sel={sel[0]}"
        webbrowser.open(flows.web_url(session.client(), prefs().server, f"/models/{s.model_id}{q}"))
        return {"FINISHED"}


class SATH_OT_notifications(bpy.types.Operator):
    bl_idname = "sath.notifications"
    bl_label = "Bildirishnomalar"

    def execute(self, context):
        s = context.scene.ges
        ok = guard(
            self, lambda: props.fill(s.notifications, flows.notification_rows(session.client()))
        )
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_mark_read(bpy.types.Operator):
    """Hammasini (yoki tanlanganini) o'qilgan qilish"""

    bl_idname = "sath.mark_read"
    bl_label = "O'qilgan"
    all: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        s = context.scene.ges
        n = _sel(s.notifications, s.notifications_index)
        ids = None if self.all or n is None else [n.item_id]
        ok = guard(self, lambda: session.client().mark_notifications_read(ids))
        if ok:
            bpy.ops.sath.notifications()
        return {"FINISHED"} if ok else {"CANCELLED"}


CLASSES = (
    SATH_OT_connect, SATH_OT_download_update, SATH_OT_logout, SATH_OT_refresh_projects, SATH_OT_refresh_models,
    SATH_OT_refresh_versions, SATH_OT_create_model, SATH_OT_open_version, SATH_OT_commit,
    SATH_OT_submit, SATH_OT_open_web, SATH_OT_notifications, SATH_OT_mark_read,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
