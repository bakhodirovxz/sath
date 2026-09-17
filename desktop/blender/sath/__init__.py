"""Sath Blender addoni: server (versiyalar, taqriz, sim, monitoring), GES obyektlari (FreeCAD dvigatel),
DXF/DWG import. IFC — Bonsai."""

from __future__ import annotations

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

MODULES: list = []
if bpy is not None:
    from . import (
        ges_objects,
        ops_import,
        ops_monitor,
        ops_review,
        ops_server,
        ops_sim,
        prefs,
        props,
        ui,
    )

    MODULES = [prefs, props, ges_objects, ops_server, ops_review, ops_sim, ops_monitor, ops_import, ui]


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
