"""SathPanel — modul panellari uchun yagona poll (spec §1): modul yoqilgan + workspace tegi + ruxsat + holat.
Atributlarga tip annotatsiyasi yozilmaydi (Blender ularni property deb o'qiydi)."""

from __future__ import annotations

from .. import session
from . import host, perms
from .registry import WORKSPACE_TAG


class SathPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sath"
    sath_module = ""  # api.register_classes to'ldiradi; "" — yadro paneli
    sath_needs = frozenset()  # {"login", "model"}
    sath_perm = ""  # masalan "sim.run" — bo'lmasa panel yashiriladi

    @classmethod
    def poll(cls, context):
        return visible(cls, context) and cls.sath_poll(context)

    @classmethod
    def sath_poll(cls, context) -> bool:
        """Modulga xos qo'shimcha shart (o'z poll i o'rniga shuni qayta yozing)."""
        return True


def in_workspace(manifest, workspace) -> bool:
    """Modul paneli shu ish joyida ko'rinadimi: tegi (ws["sath_ws"], app template qo'yadi) manifest
    `workspaces` ida bo'lsa. Tegsiz ish joyi (Layout, Modeling …) yoki `workspaces` bo'sh modul — hamma joyda."""
    tag = workspace.get(WORKSPACE_TAG) if workspace is not None else None
    return not tag or not manifest.workspaces or tag in manifest.workspaces


def visible(cls, context) -> bool:
    m = None
    if cls.sath_module:
        rec = host.record(cls.sath_module)
        if rec is None or rec.state != "enabled":
            return False
        m = rec.manifest
        if not in_workspace(m, getattr(context, "workspace", None)):
            return False
    needs = cls.sath_needs
    if ("login" in needs or "model" in needs or cls.sath_perm or (m is not None and m.visible_if_any)) and not session.is_logged_in():
        return False
    if "model" in needs and context.scene.ges.model_id <= 0:
        return False
    if m is not None and m.visible_if_any and not perms.any_of(m.visible_if_any, context):
        return False
    return not cls.sath_perm or perms.can(cls.sath_perm, context)


def draw_list(layout, s, coll: str, idx: str, rows: int = 4, refresh_op: str | None = None) -> None:
    """SATH_UL_simple ro'yxati + yangilash tugmasi."""
    row = layout.row()
    row.template_list("SATH_UL_simple", coll, s, coll, s, idx, rows=rows)
    if refresh_op:
        row.operator(refresh_op, text="", icon="FILE_REFRESH")


def cur(coll, idx: int):
    return coll[idx] if 0 <= idx < len(coll) else None
