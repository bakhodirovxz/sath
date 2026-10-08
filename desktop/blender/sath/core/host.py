"""Modul reyestrining Blender ulagichi (P3): sath/modules/ (birinchi tomon) va — Sozlamalarda ruxsat bo'lsa —
foydalanuvchi papkasidagi imzolangan modullarni topadi, tartib bilan yoqadi; jonli yoqish/o'chirish (bog'liqliklar
bilan kaskad, modul fon vazifalari bekor), o'chirishda klass/menyu/obunalarni qaytaradi; Sozlamalardagi modullar
ro'yxati; 3D View «Sath» menyusiga modul bandlari. Sof qism — core/registry.py."""

from __future__ import annotations

import importlib
import json
import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

import bpy

from . import events, perms, registry
from .tasks import TASKS

ROOT_PKG = __package__.rpartition(".")[0]  # "sath" (headless) yoki "bl_ext.user_default.sath"
BUNDLED = Path(__file__).resolve().parents[1] / "modules"
REG: registry.Registry | None = None
PINNED: frozenset[str] = frozenset()  # hozircha yo'q (mexanizm keyingi yadro-modullar uchun)
_KEYS: list[bytes] = []  # ishonchli modul kalitlari — scan() to'ldiradi (prefs + env + yangilanish kaliti); prefs dagi
# kalit maydonlari o'zgarsa (update=) scan() qayta ishlaydi — kaliti olib tashlangan modul darhol o'chadi
_menus: list[tuple[str, Callable]] = []
_offs: list[Callable[[], None]] = []


def record(mod_id: str) -> registry.Record | None:
    return REG.records.get(mod_id) if REG is not None else None


def is_enabled(mod_id: str) -> bool:
    return REG is not None and REG.is_enabled(mod_id)


def _import(m: registry.Manifest):
    if m.origin == "bundled":
        # register() i yiqilgan modul sys.modules da qolgan bo'lishi mumkin — tuzatilgan kod qayta import qilinsin
        name = f"{ROOT_PKG}.modules.{m.id}"
        for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
            del sys.modules[k]
        return importlib.import_module(name)
    # uchinchi tomon: faqat xavfsiz yuklovchi — imzo qayta tekshiriladi, bayt-kod o'qilmaydi/yozilmaydi
    return registry.load_user_module(m, _KEYS)


def _stop_tasks(mod_id: str) -> None:
    """Modul to'xtadi: `<id>.` kalitli fon vazifalari bekor va dropped (o'chirilgan modul yopilmalari chaqirilmaydi)."""
    TASKS.cancel_prefix(f"{mod_id}.", drop=True)


def user_dir() -> Path | None:
    env = os.environ.get("SATH_USER_MODULES")
    if env:
        return Path(env)
    p = bpy.utils.user_resource("CONFIG", path="sath_modules")
    return Path(p) if p else None


def _states() -> dict[str, bool]:
    from ..prefs import prefs

    try:
        d = json.loads(prefs().module_states or "{}")
    except ValueError:
        return {}
    return {str(k): bool(v) for k, v in d.items()} if isinstance(d, dict) else {}


def _save_states(changes: dict[str, bool]) -> None:
    from ..prefs import prefs

    d = _states()
    d.update(changes)
    prefs().module_states = json.dumps(d, sort_keys=True)


def wanted(m: registry.Manifest) -> bool:
    return m.id in PINNED or _states().get(m.id, m.default_enabled)


def scan() -> None:
    """Bundle + (ruxsat bo'lsa) foydalanuvchi papkasini qayta ko'radi; o'zgarmagan modullar holati saqlanadi.
    Imzosi buzilgan, kodi (qayta imzolanib) o'zgargan yoki yo'qolgan modul avval o'chiriladi."""
    if REG is None:
        return
    from ..prefs import prefs

    p = prefs()
    _KEYS[:] = registry.decode_keys([p.update_public_key, p.module_public_keys, os.environ.get("SATH_MODULE_PUBLIC_KEYS", "")])
    manifests, errors = registry.discover(BUNDLED, user_dir() if p.allow_user_modules else None, _KEYS)
    old = {rid: rec for rid, rec in REG.records.items() if rec.manifest.origin == "user"}
    REG.load(manifests, errors)
    for rid, rec in old.items():
        if REG.records.get(rid) is not rec:  # yo'qolgan yoki almashgan — eski kod sys.modules da qolmasin
            registry.unload_user_module(rid)
    REG.start(wanted)
    _redraw()


def pinned_dependents(mod_id: str) -> list[str]:
    """mod_id o'chirilsa kaskadda o'chadigan, lekin o'chirib bo'lmaydigan (PINNED) modullar."""
    return [d for d in REG.dependents(mod_id) if d in PINNED] if REG is not None else []


def disable_blocker(mod_id: str, errors: list[str] | None = None) -> str:
    """mod_id o'chirilsa (kaskadda — unga bog'liq yoqilganlari ham) rad etish sababi yoki "". Modul o'zi aytadi:
    ixtiyoriy `disable_blocker(api) -> str | None` (masalan bim: IFC ga yozilmagan GES obyektlari bor). Faqat
    foydalanuvchi o'chirishida (set_enabled, module_toggle) so'raladi — addon o'chirilishi/qayta skaner rad etilmaydi.
    Ilgak yiqilsa — o'chirish to'silmaydi (xato logda, modul id si `errors` ga): buzuq ilgak modulni abadiy qulflab
    qo'ymasin; module_toggle buni foydalanuvchiga ogohlantirish bilan aytadi."""
    if REG is None or mod_id not in REG.records:
        return ""
    for rid in [*REG.dependents(mod_id), mod_id]:
        rec = REG.records[rid]
        fn = getattr(rec.module, "disable_blocker", None) if rec.state == "enabled" else None
        if fn is None:
            continue
        try:
            why = fn(REG.api)
        except Exception:  # noqa: BLE001
            print(f"[sath] «{rid}» moduli disable_blocker xatosi:", flush=True)
            traceback.print_exc()
            if errors is not None:
                errors.append(rid)
            continue
        if why:
            return str(why)
    return ""


def set_enabled(mod_id: str, on: bool, *, check: bool = True) -> list[str]:
    """Jonli yoqish/o'chirish (bog'liqliklar bilan kaskad). Qaytaradi: holati o'zgargan modullar.
    O'chirilganlarning fon vazifalari _stop_tasks (Registry on_teardown) orqali bekor qilinadi.
    O'chirish rad etilsa (PINNED bog'liq yoki modulning disable_blocker sababi) — [] va hech narsa o'zgarmaydi.
    check=False — chaqiruvchi (module_toggle) disable_blocker ni allaqachon so'ragan (ilgak ikki marta chaqirilmasin)."""
    if REG is None or mod_id not in REG.records or mod_id in PINNED:
        return []
    if not on and (pinned_dependents(mod_id) or (check and disable_blocker(mod_id))):  # kaskad PINNED modulni ham o'chirardi
        return []
    changed = REG.enable(mod_id) if on else REG.disable(mod_id)
    _save_states({**dict.fromkeys(changed, on), mod_id: on})
    _redraw()
    return changed


class SATH_OT_module_toggle(bpy.types.Operator):
    """Sath modulini yoqish yoki o'chirish (Blender qayta ishga tushmaydi)"""

    bl_idname = "sath.module_toggle"
    bl_label = "Modulni yoqish/o'chirish"
    bl_options = {"INTERNAL"}
    module_id: bpy.props.StringProperty()

    def execute(self, context):
        rec = record(self.module_id)
        if rec is None or self.module_id in PINNED:
            return {"CANCELLED"}
        on = not wanted(rec.manifest)
        if not on and (pin := pinned_dependents(self.module_id)):
            self.report({"WARNING"}, f"{rec.manifest.name} ni o'chirib bo'lmaydi: {', '.join(pin)} unga bog'liq va o'chirilmaydi")
            return {"CANCELLED"}
        hook_errors: list[str] = []
        if not on and (why := disable_blocker(self.module_id, hook_errors)):
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        changed = set_enabled(self.module_id, on, check=False)
        if on and rec.state != "enabled":
            self.report({"ERROR"}, f"{rec.manifest.name}: yuklanmadi — sababi modullar ro'yxatida")
            return {"CANCELLED"}
        for rid in hook_errors:  # ilgak yiqildi — o'chirish to'silmadi, lekin jimgina emas
            self.report({"WARNING"}, f"{rid}: o'chirish tekshiruvi xato berdi — baribir o'chirildi")
        others = [REG.records[i].manifest.name for i in changed if i != self.module_id]
        if others:
            self.report({"INFO"}, ("Birga yoqildi: " if on else "Birga o'chirildi: ") + ", ".join(others))
        return {"FINISHED"}


class SATH_OT_modules_rescan(bpy.types.Operator):
    """Modul papkalarini qayta ko'rib chiqish (yangi yoki o'zgargan uchinchi tomon modullari)"""

    bl_idname = "sath.modules_rescan"
    bl_label = "Qayta skanerlash"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        scan()
        return {"FINISHED"}


CLASSES = (SATH_OT_module_toggle, SATH_OT_modules_rescan)


def draw_prefs(layout) -> None:
    """Sozlamalar → Sath: Blender Add-ons ro'yxati kabi (belgi, versiya, ruxsatlar, ko'rinish qoidasi, register vaqti,
    xato traceback i)."""
    from ..prefs import prefs

    box = layout.box()
    box.label(text="Modullar", icon="PLUGIN")
    if REG is None:
        box.label(text="Modul reyestri ishlamayapti", icon="ERROR")
        return
    for rid, rec in REG.records.items():
        m = rec.manifest
        row = box.row(align=True)
        if rid in PINNED:
            row.label(text="", icon="LOCKED")
        else:
            on = wanted(m)
            row.operator("sath.module_toggle", text="", icon="CHECKBOX_HLT" if on else "CHECKBOX_DEHLT",
                         emboss=False).module_id = rid  # fmt: skip
        row.label(text=f"{m.name}  {m.version}", icon={"enabled": "CHECKMARK", "failed": "ERROR"}.get(rec.state, "BLANK1"))
        row.label(text=("foydalanuvchi · " if m.origin == "user" else "") + f"{m.category} · {rec.ms:.0f} ms")
        info = []
        if m.permissions:
            info.append("Ruxsatlar: " + ", ".join(m.permissions))
        if m.requires:
            info.append("Talab: " + ", ".join(m.requires))
        if m.visible_if_any:
            info.append("Ko'rinadi: rolda " + " yoki ".join(m.visible_if_any))
        if m.workspaces:
            info.append("Ish joyi: " + ", ".join(m.workspaces))
        if info:
            box.label(text="      " + "   ".join(info))
        if rec.error:
            err = box.box()
            for line in rec.error.strip().splitlines()[-12:]:
                err.label(text=line[:140])
    for label, msg in REG.broken:
        box.label(text=f"{label}: {msg}"[:160], icon="CANCEL")
    p = prefs()
    col = layout.column()
    col.prop(p, "allow_user_modules")
    if p.allow_user_modules:
        col.prop(p, "module_public_keys")
        col.label(text="Kalit olib tashlansa uning modullari darhol o'chadi; SATH_MODULE_PUBLIC_KEYS (muhit) dagi "
                       "kalitlar doim ishonchli", icon="INFO")  # fmt: skip
        d = user_dir()
        col.label(text=f"Papka: {d}" if d else "Papka: aniqlanmadi")
        col.operator("sath.modules_rescan", icon="FILE_REFRESH")


def add_menu(mod_id: str, draw: Callable) -> None:
    entry = (mod_id, draw)
    REG.add_cleanup(mod_id, lambda: _menus.remove(entry) if entry in _menus else None)
    _menus.append(entry)


def draw_menus(layout, context) -> None:
    for mod_id, draw in list(_menus):
        if is_enabled(mod_id):
            layout.separator()
            try:
                draw(layout, context)
            except Exception:  # noqa: BLE001 — bitta modul menyusi qolgan «Sath» menyusini kesmasin
                print(f"[sath] «{mod_id}» moduli menyusi chizilmadi:", flush=True)
                traceback.print_exc()


def _redraw() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    for w in getattr(wm, "windows", ()):
        for a in w.screen.areas:
            a.tag_redraw()


def register() -> None:
    global REG
    from .. import api

    perms.clear()  # addon qayta yoqilganda: TASKS.reset tashlagan so'rovlar _pending da qolib ketmasin
    REG = registry.Registry(
        import_module=_import, register_class=bpy.utils.register_class, unregister_class=bpy.utils.unregister_class,
        on_teardown=_stop_tasks,
    )  # fmt: skip
    REG.api = api
    for c in CLASSES:
        bpy.utils.register_class(c)
    _offs.append(events.subscribe("session.login", lambda _p: perms.clear()))
    _offs.append(events.subscribe("session.logout", lambda _p: perms.clear()))
    scan()


def unregister() -> None:
    global REG
    if REG is not None:
        REG.stop()
        for rid, rec in REG.records.items():
            if rec.manifest.origin == "user":
                registry.unload_user_module(rid)
    for off in _offs:
        off()
    _offs.clear()
    _menus.clear()
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    perms.clear()
    REG = None
