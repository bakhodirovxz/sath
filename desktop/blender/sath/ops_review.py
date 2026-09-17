"""Issue lar (ko'rinish bilan), tasdiqlash so'rovlari (qarorlar), versiyalar farqi (3D rang)."""

from __future__ import annotations

import bpy

from . import flows, ifc, props, session, viewpoint
from .ops_server import _sel, guard


def _need_model(op, s) -> bool:
    if not s.model_id:
        op.report({"ERROR"}, "Avval serverdagi modelni oching (Model → Ochish)")
        return False
    return True


class SATH_OT_refresh_issues(bpy.types.Operator):
    bl_idname = "sath.refresh_issues"
    bl_label = "Issue lar"

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s):
            return {"CANCELLED"}
        ok = guard(self, lambda: props.fill(s.issues, flows.issue_rows(session.client(), s.model_id)))
        if ok and len(s.issues) and not (0 <= s.issues_index < len(s.issues)):
            s.issues_index = 0  # update → show_issue
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_show_issue(bpy.types.Operator):
    bl_idname = "sath.show_issue"
    bl_label = "Issue tafsiloti"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None:
            s.issue_detail = ""
            return {"FINISHED"}

        def do():
            s.issue_detail = flows.issue_text(session.client().issue(i.item_id))

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_goto_view(bpy.types.Operator):
    """Issue ko'rinishiga o'tish (kamera + tanlov)"""

    bl_idname = "sath.goto_view"
    bl_label = "Ko'rinishga o'tish"

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None:
            return {"CANCELLED"}
        ok = guard(
            self,
            lambda: viewpoint.apply(
                context, session.client().issue(i.item_id).get("viewpoint") or {}
            ),
        )
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_comment_issue(bpy.types.Operator):
    bl_idname = "sath.comment_issue"
    bl_label = "Izoh qoldirish"

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None or not s.comment_text.strip():
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().comment_issue(i.item_id, s.comment_text.strip()))
        if ok:
            s.comment_text = ""
            bpy.ops.sath.show_issue()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_new_issue(bpy.types.Operator):
    """Yangi issue — joriy ko'rinish (kamera, tanlangan elementlar) bilan"""

    bl_idname = "sath.new_issue"
    bl_label = "Yangi issue"
    title: bpy.props.StringProperty(name="Sarlavha")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s) or not self.title.strip():
            return {"CANCELLED"}
        ok = guard(
            self,
            lambda: session.client().create_issue(
                s.model_id,
                self.title.strip(),
                version_id=s.version_id or None,
                viewpoint=viewpoint.capture(context),
            ),
        )
        if ok:
            bpy.ops.sath.refresh_issues()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_refresh_crs(bpy.types.Operator):
    bl_idname = "sath.refresh_crs"
    bl_label = "Tasdiqlash so'rovlari"

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s):
            return {"CANCELLED"}

        def do():
            props.fill(s.crs, flows.cr_rows(session.client(), s.model_id))
            s.my_role = flows.model_role(session.client(), s.model_id) or ""
            if len(s.crs) and not (0 <= s.crs_index < len(s.crs)):
                s.crs_index = 0  # update → show_cr

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_show_cr(bpy.types.Operator):
    bl_idname = "sath.show_cr"
    bl_label = "CR tafsiloti"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            s.cr_detail = ""
            return {"FINISHED"}

        def do():
            s.cr_detail = flows.cr_text(session.client().change_request(cr.item_id))

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_decide(bpy.types.Operator):
    """Qaror: ma'qullash / o'zgartirish so'rash / faqat izoh"""

    bl_idname = "sath.decide"
    bl_label = "Qaror"
    decision: bpy.props.EnumProperty(
        items=[
            ("approve", "Ma'qullash", ""),
            ("request_changes", "O'zgartirish so'rash", ""),
            ("comment", "Faqat izoh", ""),
        ]
    )

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(
            self,
            lambda: session.client().review_change_request(
                cr.item_id, self.decision, s.comment_text.strip()
            ),
        )
        if ok:
            s.comment_text = ""
            bpy.ops.sath.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_merge_cr(bpy.types.Operator):
    bl_idname = "sath.merge_cr"
    bl_label = "Tasdiqlash (merge)"

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().merge_change_request(cr.item_id))
        if ok:
            bpy.ops.sath.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_reject_cr(bpy.types.Operator):
    bl_idname = "sath.reject_cr"
    bl_label = "Rad etish"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().reject_change_request(cr.item_id))
        if ok:
            bpy.ops.sath.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class SATH_OT_diff(bpy.types.Operator):
    """Tanlangan versiyaning ota bilan farqi — 3D da rang (yashil qo'shilgan, sariq o'zgargan)"""

    bl_idname = "sath.diff"
    bl_label = "Ota bilan farq (3D rang)"

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and _sel(s.versions, s.versions_index) is not None

    def execute(self, context):
        s = context.scene.ges
        v = _sel(s.versions, s.versions_index)

        def do():
            d = session.client().diff(v.item_id)
            ifc.DIFF_STATE.restore()
            colors, text = flows.diff_colors(d)
            n = ifc.DIFF_STATE.paint(colors)
            note = "" if s.version_id == v.item_id else "(diqqat: boshqa versiya ochiq) "
            s.diff_note = f"{note}v{v.number}: {text}. 3D da {n} obyekt bo'yaldi."

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_clear_diff(bpy.types.Operator):
    bl_idname = "sath.clear_diff"
    bl_label = "Rangni tozalash"

    def execute(self, context):
        ifc.DIFF_STATE.restore()
        context.scene.ges.diff_note = ""
        return {"FINISHED"}


CLASSES = (
    SATH_OT_refresh_issues, SATH_OT_show_issue, SATH_OT_goto_view, SATH_OT_comment_issue,
    SATH_OT_new_issue, SATH_OT_refresh_crs, SATH_OT_show_cr, SATH_OT_decide, SATH_OT_merge_cr,
    SATH_OT_reject_cr, SATH_OT_diff, SATH_OT_clear_diff,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
