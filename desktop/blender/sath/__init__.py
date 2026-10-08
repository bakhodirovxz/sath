"""Sath Blender addoni: server (versiyalar, taqriz, sim, monitoring), GES obyektlari (sof Python geometriya,
FreeCAD siz), DXF/DWG import. IFC — Bonsai."""

from __future__ import annotations

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

MODULES: list = []
if bpy is not None:
    from . import prefs, props
    from .core import host, ui_tasks

    # P3: qolgan hammasi sath/modules/ da — host topadi va yoqadi (legacy — o'tish davri)
    MODULES = [ui_tasks, prefs, props, host]


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
