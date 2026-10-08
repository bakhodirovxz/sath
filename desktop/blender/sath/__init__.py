"""Sath Blender addoni: yadro (server, versiyalar, rolga sezgir UI, fon vazifalari) + modullar (sath/modules/:
review, sim, scada, twin, io, bim; Sozlamalarda yoqiladi/o'chiriladi). IFC — Bonsai."""

from __future__ import annotations

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

MODULES: list = []
if bpy is not None:
    from . import ops_server, prefs, props, ui
    from .core import host, ui_tasks

    # Yadro: fon vazifalari, sozlamalar, Scene.ges, server/login/commit, yadro panellari va menyu; qolgani — modules/
    MODULES = [ui_tasks, prefs, props, ops_server, ui, host]


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
