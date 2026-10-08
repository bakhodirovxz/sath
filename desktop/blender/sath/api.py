"""Sath modullari uchun barqaror fasad (spec §1). Modul `register(api)` / `unregister(api)` da faqat shu nomlardan
foydalanadi — ichki fayllar (ops_*.py, ui.py) o'zgarsa ham modul buzilmasin. Mos kelmaydigan o'zgarish
API_VERSION[0] ni oshiradi (manifestda `api = ">=1.0,<2"`).

  register_classes(mod_id, classes)  klasslar (SathPanel lar manifestdan bl_category/bl_order oladi), o'chirishda qaytadi
  adopt(mod_id, *fayllar)            mavjud faylning register()/unregister() juftini modulga biriktirish
  on_unregister(mod_id, fn)          o'chirishda chaqiriladigan tozalash
  session, tasks, perms, events, ui, props; dangasa: ifc, geom, kinds
"""

from __future__ import annotations

import importlib
import os
import threading
from collections.abc import Callable, Iterable
from types import SimpleNamespace

import bpy

from . import props as _props
from . import session
from .core import events as _events
from .core import host as _host
from .core import perms as _perms
from .core.panels import SathPanel, cur, draw_list
from .core.registry import API_VERSION
from .core.tasks import TASKS
from .core.ui_tasks import ensure_pump, run_op

__all__ = ["API_VERSION", "adopt", "events", "module_enabled", "on_unregister", "perms", "props", "register_classes",
           "session", "tasks", "ui"]  # fmt: skip


def _main_thread() -> None:
    assert threading.current_thread() is threading.main_thread(), "sath.api: faqat asosiy oqimda (ishchi oqim bpy ga tegmaydi)"


def register_classes(mod_id: str, classes: Iterable[type]) -> None:
    _main_thread()
    rec = _host.REG.owner(mod_id)
    classes = list(classes)
    panels_open = bool(os.environ.get("SATH_PANELS_OPEN"))  # GUI sinovi: hammasi ochiq, «Item» yorlig'ida
    for c in classes:
        if issubclass(c, SathPanel):
            c.sath_module = mod_id
            c.bl_category = "Item" if panels_open else rec.manifest.category
            if "bl_order" not in c.__dict__:
                c.bl_order = rec.manifest.order
            if panels_open and "DEFAULT_CLOSED" in getattr(c, "bl_options", set()):
                c.bl_options = set(c.bl_options) - {"DEFAULT_CLOSED"}
    _host.REG.add_classes(mod_id, classes)


def adopt(mod_id: str, *files) -> None:
    """Mavjud fayllarni (ops_*.py, ges_objects …) modulga biriktiradi: register() hozir, unregister() o'chirishda
    (teskari tartibda). Fayl register() i yarim yiqilsa — o'z unregister() i bilan tozalanadi."""
    _main_thread()
    _host.REG.owner(mod_id)
    for f in files:
        try:
            f.register()
        except Exception:
            try:
                f.unregister()
            except Exception:  # noqa: BLE001 — qisman ro'yxatdan o'tgan bo'lishi mumkin
                pass
            raise
        _host.REG.add_cleanup(mod_id, f.unregister)


def on_unregister(mod_id: str, fn: Callable[[], None]) -> None:
    _main_thread()
    _host.REG.add_cleanup(mod_id, fn)


def module_enabled(mod_id: str) -> bool:
    return _host.is_enabled(mod_id)


class events:
    @staticmethod
    def publish(topic: str, **payload) -> None:
        """Obunachilar bpy ga tegadi — faqat asosiy oqimdan (ishchi oqim natijani on_done orqali qaytarsin)."""
        _main_thread()
        _events.publish(topic, **payload)

    @staticmethod
    def subscribe(topic: str, fn: Callable[[dict], None], *, owner: str | None = None) -> Callable[[], None]:
        """owner berilsa — modul o'chirilganda obuna avtomatik bekor bo'ladi."""
        _main_thread()
        if owner:
            _host.REG.owner(owner)
        off = _events.subscribe(topic, fn)
        if owner:
            _host.REG.add_cleanup(owner, off)
        return off


class tasks:
    run_op = staticmethod(run_op)
    drain = staticmethod(TASKS.drain)

    @staticmethod
    def run(title, fn, on_done=None, on_error=None, *, key=None, cancellable=True, quiet=False, on_cancel=None):
        """Fon vazifasi + pompa. fn ishchi oqimda (bpy ga TEGMAYDI). Kalit `<mod_id>.` bilan boshlansin —
        modul o'chirilganda shunday vazifalar bekor qilinadi."""
        _main_thread()
        t = TASKS.run(title, fn, on_done, on_error, key=key, cancellable=cancellable, quiet=quiet, on_cancel=on_cancel)
        ensure_pump()
        return t


class perms:
    can = staticmethod(_perms.can)
    any_of = staticmethod(_perms.any_of)
    require = staticmethod(_perms.require)
    role = staticmethod(_perms.role)
    poll = staticmethod(_perms.poll)


class ui:
    SathPanel = SathPanel
    draw_list = staticmethod(draw_list)
    cur = staticmethod(cur)

    @staticmethod
    def main_menu(mod_id: str, draw: Callable) -> None:
        """3D View «Sath» menyusiga band: draw(layout, context)."""
        _main_thread()
        _host.add_menu(mod_id, draw)

    @staticmethod
    def keymap(mod_id: str, idname: str, key: str, *, ctrl=False, shift=False, alt=False, km_name="3D View",
               space_type="VIEW_3D", **properties):  # fmt: skip
        _main_thread()
        kc = bpy.context.window_manager.keyconfigs.addon
        if kc is None:  # fon rejimi
            return None
        km = kc.keymaps.new(name=km_name, space_type=space_type)
        kmi = km.keymap_items.new(idname, key, "PRESS", ctrl=ctrl, shift=shift, alt=alt)
        for k, v in properties.items():
            setattr(kmi.properties, k, v)
        _host.REG.add_cleanup(mod_id, lambda: km.keymap_items.remove(kmi))
        return kmi


class props:
    @staticmethod
    def scene_group(mod_id: str, cls: type) -> str:
        """Modul holati: Scene.sath_<mod_id> (PointerProperty); props.snapshot_scene/restore_scene ga avtomatik
        kiradi (Bonsai yangi sessiyasidan omon qoladi). Qaytaradi: atribut nomi."""
        _main_thread()
        attr = f"sath_{mod_id}"
        _host.REG.add_classes(mod_id, [cls])
        setattr(bpy.types.Scene, attr, bpy.props.PointerProperty(type=cls))
        _props.GROUPS[attr] = mod_id

        def off() -> None:
            _props.GROUPS.pop(attr, None)
            if hasattr(bpy.types.Scene, attr):
                delattr(bpy.types.Scene, attr)

        _host.REG.add_cleanup(mod_id, off)
        return attr


def __getattr__(name: str):
    """Dangasa: api.ifc (+ IfcOperator, restore_ges — P2 da bo'lsa), api.geom, api.kinds (numpy)."""
    if name == "ifc":
        from . import ifc as m
        from .core.ifc_ops import IfcOperator, SathOpError
        from .ges_objects import restore_from_ifc

        ns = SimpleNamespace(file=m.file, load=m.load, save=m.save, entity=m.entity, guid=m.guid, guid_map=m.guid_map,
                             object_for_guid=m.object_for_guid, select_guids=m.select_guids,
                             ensure_project=m.ensure_project, orphans=m.orphans, IfcOperator=IfcOperator,
                             SathOpError=SathOpError, restore_ges=restore_from_ifc)  # fmt: skip
        globals()["ifc"] = ns
        return ns
    if name in ("geom", "kinds"):
        mod = importlib.import_module(".shared." + ("geom" if name == "geom" else "ges_kinds"), __package__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
