"""SathPanel — modul panellari uchun yagona poll (spec §1): modul yoqilgan + workspace tegi + ruxsat + holat.
Atributlarga tip annotatsiyasi yozilmaydi (Blender ularni property deb o'qiydi)."""

from __future__ import annotations

from .. import session
from . import host, perms


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


def visible(cls, context) -> bool:
    m = None
    if cls.sath_module:
        rec = host.record(cls.sath_module)
        if rec is None or rec.state != "enabled":
            return False
        m = rec.manifest
        ws = getattr(context, "workspace", None)
        tag = ws.get("sath_ws") if ws is not None else None
        if tag and m.workspaces and tag not in m.workspaces:  # tegsiz workspace (P4 gacha) — hammasi ko'rinadi
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
