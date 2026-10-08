"""K4: IFC o'zgartiradigan Sath operatorlari — Bonsai `tool.Ifc.Operator` shartnomasi ustidan mixin.

Bonsai IFC tranzaksiyalarini o'z tarixida (IfcStore.history) saqlaydi va Blender undo/redo dan keyin `undo_post`
handler orqali shu tarixni orqaga/oldinga suradi. Operator `IfcStore.execute_ifc_operator` orqali bajarilsa,
ichidagi barcha IFC o'zgarishlari (ichki bim.* operatorlari, ifcopenshell.api, ifc.write_psets) bitta tranzaksiya
— Blender ning bitta undo qadami bilan bog'lanadi. Bonsai ichki API faqat shu faylda (spec «Xavflar»); sinalgan:
Bonsai 0.9.0 (`bonsai.bim.ifc.IfcStore.execute_ifc_operator(op, context)` — `_execute` natijasini qaytaradi).
"""

from __future__ import annotations

import bpy


class SathOpError(RuntimeError):
    """Kutilgan foydalanuvchi xatosi: operator xabar beradi va {"CANCELLED"} qaytaradi (traceback siz)."""


def _store():
    """Bonsai IfcStore yoki None (Bonsai yoqilmagan — masalan `--bonsai` siz headless test)."""
    if not hasattr(bpy.types.Scene, "BIMProperties"):
        return None
    try:
        from bonsai.bim.ifc import IfcStore
    except ImportError:
        return None
    return IfcStore


class IfcOperator:
    """Mixin: `class SATH_OT_x(IfcOperator, bpy.types.Operator)`, ish `_execute(context)` da (execute emas).

    - `bl_options = {"REGISTER", "UNDO"}` — IFC tranzaksiyasi Blender undo qadami bilan bog'lanadi.
    - `sath_needs_project` (True) — tranzaksiyadan OLDIN `ifc.ensure_project()` (yangi loyiha o'z undo qadami;
      tranzaksiya o'rtasida fayl yaratilmaydi). Import kabi operatorlarda property bilan shartli qilinadi.
    - `_execute` xatoda istisno (`SathOpError` — kutilgan) ko'taradi, {"CANCELLED"} QAYTARMAYDI: IFC o'zgargan bo'lsa
      Bonsai «Recover» undo qadamini qo'yadi, biz xabar beramiz. CANCELLED qaytarilsa Blender undo qadami yo'q,
      IfcStore da tranzaksiya bor — tarixlar ajraladi.
    """

    bl_options = {"REGISTER", "UNDO"}
    transaction_key = ""
    transaction_data = None
    sath_needs_project = True

    def execute(self, context):
        from .. import ifc

        store = _store()
        try:
            if store is None:
                return self._execute(context) or {"FINISHED"}
            if self.sath_needs_project:
                ifc.ensure_project()
            return store.execute_ifc_operator(self, context) or {"FINISHED"}
        except SathOpError as e:
            self.report({"ERROR"}, str(e))
        except Exception as e:  # noqa: BLE001 — Blender da traceback o'rniga aniq xabar
            import traceback

            traceback.print_exc()  # konsolda to'liq (kutilmagan xato), foydalanuvchiga qisqa
            self.report({"ERROR"}, f"{self.bl_label}: {e}")
        return {"CANCELLED"}

    def _execute(self, context):
        raise NotImplementedError


def last_key() -> str:
    """Oxirgi IFC tranzaksiyasi kaliti (Bonsai yo'q — "")."""
    store = _store()
    return store.last_transaction if store is not None else ""


def undo_to(key: str) -> None:
    """Headless testlar uchun: IFC tranzaksiyalarini `key` gacha orqaga. GUI da Ctrl+Z dan keyin Bonsai `undo_post`
    aynan shuni qiladi (`IfcStore.undo(until_key=props.last_transaction)`); `-b` da Blender undo steki yo'q."""
    import bonsai.tool as tool

    store = _store()
    store.undo(until_key=key)
    store.last_transaction = key
    tool.Blender.get_bim_props().last_transaction = key


def rebuild_maps() -> None:
    """Blender obyektlari o'chirilgandan keyin Bonsai element xaritalarini (id/guid → obyekt) yangilash."""
    import bonsai.tool as tool

    tool.Ifc.rebuild_element_maps()
