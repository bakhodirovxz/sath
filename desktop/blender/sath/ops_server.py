"""Server operatorlari: ulanish, loyiha/model/versiya ro'yxatlari, ochish, commit, tasdiqqa yuborish, web,
bildirishnomalar."""

from __future__ import annotations

import webbrowser

import bpy

from . import flows, ifc, props, session, update, viewpoint
from .core import perms
from .core.tasks import TASKS
from .core.ui_tasks import run_op
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
        p, sec = prefs(), props.secret(context)
        server, username, password, otp = p.server, p.username, sec.password, sec.otp
        sec.password = ""  # CODE-05: parol/MFA kodi xotirada qolmaydi — ish boshlanishidan oldin tozalanadi
        sec.otp = ""

        def work(ctx):
            c, u = session.connect_client(server, username, password, otp)
            pkg = flows.newer_package(c, flows.ADDON_VERSION)
            note = flows.check_update(c, flows.ADDON_VERSION) if pkg else None
            return c, u, pkg, note, flows.unread_summary(c), flows.project_rows(c)

        def apply(res):
            c, u, pkg, note, unread, rows = res
            session.set_session(c, u)
            session.remember(server, username)
            s = bpy.context.scene.ges
            s.status = f"{u['username']} sifatida kirildi" + (f" · {unread}" if unread else "")
            s.update_version = pkg["version"] if pkg else ""
            if note:
                s.status += f" · {note}"
            props.fill(s.projects, rows)
            s.projects_index = 0 if len(s.projects) else -1  # update → modellar

        return run_op(self, "Ulanish", work, apply, key="server.connect")


class SATH_OT_download_update(bpy.types.Operator):
    """Serverdagi yangi Sath paketini yuklab olish va tekshirish (hajm, sha256, imzo) — installer yoki zip"""

    bl_idname = "sath.download_update"
    bl_label = "Yangilanishni yuklab olish"
    kind: bpy.props.EnumProperty(items=[("installer", "Installer", ""), ("zip", "Zip", "")])

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        kind, pubkey = self.kind, prefs().update_public_key
        dest_dir = flows.cache_dir() / "updates"

        def work(ctx):
            # SEC-03: paket brauzerda ochilmaydi — addon o'zi yuklab, hajm/sha256/imzoni tekshiradi
            client = session.client()
            latest = update.latest(client)
            if not latest:
                raise RuntimeError("Serverda desktop paketi yo'q")
            pkg = next((f for f in latest.get("files", []) if f["kind"] == kind), None)
            if pkg is None:
                raise RuntimeError(f"Serverda {kind} paketi yo'q")

            def prog(got, total):
                ctx.check()
                ctx.progress(got / total if total else None, f"{got / 2**20:.0f} MB")

            try:
                return update.download_and_verify(client, pkg, dest_dir, pubkey, progress=prog)
            except update.UpdateError as e:
                raise RuntimeError(str(e)) from None

        def apply(path):
            bpy.ops.wm.path_open(filepath=str(path.parent))
            signed = "imzo ✓" if pubkey.strip() else "imzo tekshirilmadi (kalit sozlanmagan)"
            bpy.context.scene.ges.status = f"Tekshirildi (hajm, sha256 ✓, {signed}): {path.name} — o'rnatish uchun ishga tushiring"

        return run_op(self, "Yangilanish", work, apply, key="server.update")


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

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        return session.is_logged_in() and p is not None and perms.poll(cls, "model.write", context, project_id=p.item_id)

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
            "project_id": p.item_id if p else 0, "model_id": m.item_id, "version_id": v.item_id,
            "version_number": v.number, "model_name": m.name,
            "status": f"{p.name if p else ''} — {m.name} v{v.number} ochildi",
        }  # fmt: skip
        model, version = {"id": m.item_id}, {"id": v.item_id, "number": v.number}

        def work(ctx):
            return flows.download_version(
                session.client(), model, version,
                progress=lambda got, total: ctx.progress(got / total if total else None, f"{got / 2**20:.1f} MB"),
                cancelled=lambda: ctx.cancelled,
            )  # fmt: skip

        def apply(path):
            snap = props.snapshot_scene(bpy.context.scene)  # Bonsai fresh session sahnani almashtiradi
            if ifc.load(path):
                props.restore_scene(bpy.context.scene, snap)
            sc = bpy.context.scene.ges
            for k, val in info.items():
                setattr(sc, k, val)

        return run_op(self, f"v{v.number} ni ochish", work, apply, key="server.open")


class SATH_OT_pull_head(bpy.types.Operator):
    """Commit rad etildi (model serverda yangilangan): joriy IFC zaxira nusxaga saqlanadi, eng oxirgi versiya
    ochiladi — o'zgarishlarni qayta kiritib commit qiling (VCS-01)"""

    bl_idname = "sath.pull_head"
    bl_label = "Eng oxirgi versiyani yuklab olish"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.head_conflict_id >= 0 and bool(context.scene.ges.model_id)

    def execute(self, context):
        import time

        s = context.scene.ges
        model_id, head_id = s.model_id, s.head_conflict_id
        backup = None
        if ifc.file() is not None:  # lokal o'zgarishlar yo'qolmasin (bpy — asosiy oqimda, ishdan oldin)
            backup = ifc.save(flows.cache_dir() / f"lokal_m{model_id}_{time.strftime('%Y%m%d_%H%M%S')}.ifc")

        def work(ctx):
            c = session.client()
            versions = c.versions(model_id)
            head = next((v for v in versions if v["id"] == head_id), None) if head_id else None
            head = head or max(versions, key=lambda v: v["number"])
            path = flows.download_version(
                c, {"id": model_id}, {"id": head["id"], "number": head["number"]}, cancelled=lambda: ctx.cancelled
            )
            return head, path

        def apply(res):
            head, path = res
            snap = props.snapshot_scene(bpy.context.scene)
            if ifc.load(path):
                props.restore_scene(bpy.context.scene, snap)
            sc = bpy.context.scene.ges
            sc.version_id, sc.version_number, sc.head_conflict_id = head["id"], head["number"], -1
            sc.status = f"v{head['number']} ochildi" + (f"; lokal nusxa: {backup}" if backup else "")
            bpy.ops.sath.refresh_versions()

        return run_op(self, "Eng oxirgi versiya", work, apply, key="server.open")


def unassigned(context) -> list[str]:
    """Sahnadagi IFC ga kirmagan (commit ga tushmaydigan) MESH/CURVE obyektlar; yordamchilar (suv tekisligi,
    yer, sim animatsiyasi, `sath_aux`) hisobga olinmaydi (CAD-01)."""
    from . import demo_plant, sim_anim, water

    rows = []
    for o in context.scene.objects:
        if o.type not in ("MESH", "CURVE"):
            continue
        aux = (
            bool(o.get(flows.AUX_PROP))
            or o.name in water.PLANES
            or o.name == demo_plant.GROUND
            or any(c.name == sim_anim.SIM_COLL for c in o.users_collection)
        )
        rows.append((o.name, o.type, ifc.entity(o) is not None, aux))
    return flows.unassigned_objects(rows)


class SATH_OT_commit(bpy.types.Operator):
    """Joriy IFC ni serverga yangi versiya sifatida yuklash"""

    bl_idname = "sath.commit"
    bl_label = "Commit (yangi versiya)"

    assign_missing: bpy.props.BoolProperty(
        name="IFC ga kirmagan mesh larni qo'shish",
        description="IFC elementi bo'lmagan mesh obyektlar IfcBuildingElementProxy (yoki nom bo'yicha GES turi) bo'ladi",
        default=False,
        options={"SKIP_SAVE"},
    )
    unassigned_note: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    purge_orphans: bpy.props.BoolProperty(
        name="Yetim IFC entitylarni o'chirish",
        description="Blender obyekti yo'q GES elementlari va bog'lanmagan pset/representation commit ga kirmasin",
        default=False,  # Bonsai yuklamagan GES elementi jimgina o'chmasin — foydalanuvchi ro'yxatni ko'rib tanlaydi
        options={"SKIP_SAVE"},
    )
    orphan_note: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and ifc.file() is not None and perms.poll(cls, "model.write", context)

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
        # CAD-01: IFC ga kirmagan obyektlar commit ga tushmaydi — dialogda ogohlantiramiz (davom / bekor qilish)
        self.unassigned_note = flows.unassigned_text(unassigned(context))
        self.orphan_note = flows.orphans_text(ifc.orphans())  # K4: yetim IFC entitylar (commit ga kiradi)
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        s = context.scene.ges
        parent = f" (ota: v{s.version_number})" if s.version_id else ""
        self.layout.label(text=f"Model: {s.model_name}{parent}")
        self.layout.prop(s, "commit_message")
        self.layout.prop(s, "submit_after_commit")
        if self.unassigned_note:
            box = self.layout.box()
            box.label(text=self.unassigned_note, icon="ERROR")
            box.label(text="Ular yangi versiyaga kirmaydi. Davom etish — OK, to'xtatish — Bekor.")
            box.prop(self, "assign_missing")
        if self.orphan_note:
            box = self.layout.box()
            for i, line in enumerate(self.orphan_note.splitlines()):
                box.label(text=line, icon="ORPHAN_DATA" if i == 0 else "NONE")
            box.prop(self, "purge_orphans")

    def execute(self, context):
        if TASKS.running("server.commit"):  # ikkinchi bosish commit_m{id}.ifc ni yuklash o'rtasida qayta yozmasin
            self.report({"WARNING"}, "Commit: allaqachon bajarilmoqda")
            return {"CANCELLED"}
        s = context.scene.ges
        try:  # bpy qismi (IFC ga yozish) — asosiy oqimda, yuborishdan oldin
            # K4: kechiktirilgan/sinxronlanmagan GES o'zgarishlari IFC ga (har biri o'z undo qadami). Xato bo'lsa
            # commit to'xtaydi — eskirgan IFC serverga ketmasin (sabab operator xabarida/holat qatorida).
            if bpy.ops.sath.sync_ifc() != {"FINISHED"}:
                raise RuntimeError("GES o'zgarishlarini IFC ga yozib bo'lmadi («IFC ga qo'llash» xabarini ko'ring)")
            if self.assign_missing and bpy.ops.sath.assign_ifc(names=";".join(unassigned(context))) != {"FINISHED"}:
                raise RuntimeError("IFC ga kirmagan obyektlarni qo'shib bo'lmadi")
            if self.purge_orphans and ifc.orphans() and bpy.ops.sath.purge_orphans() != {"FINISHED"}:
                raise RuntimeError("Yetim IFC entitylarni o'chirib bo'lmadi")
            ifc.stamp_guids()  # sath_guid — Blender dan FBX/glTF eksportida GUID saqlansin (CAD-07)
            path = ifc.save(flows.cache_dir() / f"commit_m{s.model_id}.ifc")
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        model_id, message, parent, submit = s.model_id, s.commit_message.strip(), s.version_id or None, s.submit_after_commit

        def work(ctx):
            return flows.commit(session.client(), model_id, path, message, parent, submit)

        def apply(r):
            sc = bpy.context.scene.ges
            sc.head_conflict_id = -1
            v = r["version"]
            sc.version_id, sc.version_number = v["id"], v["number"]
            sc.status = f"v{v['number']} yuklandi" + (" va tasdiqqa yuborildi" if r["cr"] else "")
            sc.commit_message = ""
            bpy.ops.sath.refresh_versions()

        def fail(e):
            head = flows.head_conflict(e) if isinstance(e, ServerError) else None
            if head is None:
                return None
            # VCS-01: ota versiya eskirgan — jimgina «vilka» qilinmaydi; foydalanuvchi eng oxirgisini oladi
            sc = bpy.context.scene.ges
            sc.head_conflict_id = head
            sc.status = flows.conflict_text(e)
            return sc.status

        stale = "Commit serverga yuklangan bo'lishi mumkin — versiyalar ro'yxatini yangilang (qayta commit qilmang)"
        return run_op(self, "Commit", work, apply, key="server.commit", fail=fail, cancellable=False, stale=stale)


class SATH_OT_submit(bpy.types.Operator):
    """Joriy versiya uchun tasdiqlash so'rovi"""

    bl_idname = "sath.submit"
    bl_label = "Tasdiqqa yuborish"
    title: bpy.props.StringProperty(name="Sarlavha")

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and bool(s.model_id and s.version_id) and perms.poll(cls, "cr.create", context)

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
    SATH_OT_refresh_versions, SATH_OT_create_model, SATH_OT_open_version, SATH_OT_commit, SATH_OT_pull_head,
    SATH_OT_submit, SATH_OT_open_web, SATH_OT_notifications, SATH_OT_mark_read,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
