"""Taqriz moduli: versiyalar farqi (3D rang), issue lar (BCF ko'rinish), tasdiqlash so'rovlari (CR) — rolga sezgir."""

from __future__ import annotations

import bpy

from ... import ifc, ops_review
from ...core import perms
from ...core.panels import SathPanel, cur, draw_list


class SATH_PT_review(SathPanel, bpy.types.Panel):
    bl_label = "Taqriz va issue lar"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        box = lay.box()
        box.label(text="Versiyalar farqi", icon="SELECT_DIFFERENCE")
        row = box.row(align=True)
        row.operator("sath.diff")
        row.operator("sath.clear_diff", text="", icon="X")
        if s.diff_note:
            box.label(text=s.diff_note)

        box = lay.box()
        box.label(text="Issue lar", icon="ERROR")
        draw_list(box, s, "issues", "issues_index", 4, "sath.refresh_issues")
        for line in s.issue_detail.splitlines()[:8]:
            box.label(text=line)
        row = box.row(align=True)
        row.operator("sath.goto_view", icon="CAMERA_DATA")
        if perms.can("issue.write", context):
            row.operator("sath.new_issue", icon="ADD")
            row = box.row(align=True)
            row.prop(s, "comment_text", text="")
            row.operator("sath.comment_issue", text="", icon="PLAY")

        box = lay.box()
        role = perms.role(context)
        box.label(text="Tasdiqlash so'rovlari" + (f" · {role}" if role else ""), icon="CHECKMARK")
        draw_list(box, s, "crs", "crs_index", 4, "sath.refresh_crs")
        for line in s.cr_detail.splitlines()[:8]:
            box.label(text=line)
        cr = cur(s.crs, s.crs_index)
        st = cr.col4 if cr else ""
        open_ = st in ("open", "changes_requested", "approved")
        can_approve, can_review = perms.can("cr.approve", context), perms.can("cr.review", context)
        if can_approve or can_review:  # spec §2: viewer/engineer da qaror tugmalari ko'rinmaydi
            row = box.row(align=True)
            r1 = row.row()
            r1.enabled = can_approve and open_ and st != "approved"
            r1.operator("sath.decide", text="Ma'qullash").decision = "approve"
            r2 = row.row()
            r2.enabled = can_review and open_
            r2.operator("sath.decide", text="O'zgartirish so'rash").decision = "request_changes"
        row = box.row(align=True)
        if perms.can("cr.merge", context):
            r1 = row.row()
            r1.enabled = st == "approved"
            r1.operator("sath.merge_cr")
        r2 = row.row()
        r2.enabled = bool(cr) and st not in ("merged", "rejected")
        r2.operator("sath.reject_cr")  # muallif o'z CR ini qaytarib olishi mumkin — ruxsat serverda
        box.operator("sath.decide", text="Faqat izoh qoldirish").decision = "comment"


def register(api):
    api.adopt("review", ops_review)
    api.register_classes("review", [SATH_PT_review])


def unregister(api):
    ifc.DIFF_STATE.restore()  # o'chirilgan modulning 3D ranglari qolmasin
    for sc in getattr(bpy.data, "scenes", ()):
        sc.ges.diff_note = ""
