"""Modul reyestrining Blender ulagichi (P3): sath/modules/ dagi modullarni topadi, tartib bilan yoqadi, o'chirishda
klass/menyu/obunalarni qaytaradi; 3D View «Sath» menyusiga modul bandlari. Sof qism — core/registry.py."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import bpy

from . import events, perms, registry

ROOT_PKG = __package__.rpartition(".")[0]  # "sath" (headless) yoki "bl_ext.user_default.sath"
BUNDLED = Path(__file__).resolve().parents[1] / "modules"
REG: registry.Registry | None = None
_menus: list[tuple[str, Callable]] = []
_offs: list[Callable[[], None]] = []


def record(mod_id: str) -> registry.Record | None:
    return REG.records.get(mod_id) if REG is not None else None


def is_enabled(mod_id: str) -> bool:
    return REG is not None and REG.is_enabled(mod_id)


def _import(m: registry.Manifest):
    if m.origin == "bundled":
        return importlib.import_module(f"{ROOT_PKG}.modules.{m.id}")
    name = f"_sath_user_{m.id}"
    spec = importlib.util.spec_from_file_location(name, m.path / "__init__.py", submodule_search_locations=[str(m.path)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def wanted(m: registry.Manifest) -> bool:
    return m.default_enabled  # Task 5: Sozlamalardagi tanlov


def scan() -> None:
    if REG is None:
        return
    manifests, errors = registry.discover(BUNDLED)
    REG.load(manifests, errors)
    REG.start(wanted)
    _redraw()


def add_menu(mod_id: str, draw: Callable) -> None:
    entry = (mod_id, draw)
    REG.add_cleanup(mod_id, lambda: _menus.remove(entry) if entry in _menus else None)
    _menus.append(entry)


def draw_menus(layout, context) -> None:
    for mod_id, draw in list(_menus):
        if is_enabled(mod_id):
            layout.separator()
            draw(layout, context)


def _redraw() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    for w in getattr(wm, "windows", ()):
        for a in w.screen.areas:
            a.tag_redraw()


def register() -> None:
    global REG
    from .. import api

    REG = registry.Registry(
        import_module=_import, register_class=bpy.utils.register_class, unregister_class=bpy.utils.unregister_class
    )
    REG.api = api
    _offs.append(events.subscribe("session.login", lambda _p: perms.clear()))
    _offs.append(events.subscribe("session.logout", lambda _p: perms.clear()))
    scan()


def unregister() -> None:
    global REG
    if REG is not None:
        REG.stop()
    for off in _offs:
        off()
    _offs.clear()
    _menus.clear()
    REG = None
