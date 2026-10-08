"""Sath Blender addoni: yadro (server, versiyalar, rolga sezgir UI, fon vazifalari) + modullar (sath/modules/:
review, sim, scada, twin, io, bim; Sozlamalarda yoqiladi/o'chiriladi). IFC — Bonsai. register() har yadro
qismi va modul vaqtini bitta qatorda logga yozadi (spec §5 byudjeti: core/budget.py)."""

from __future__ import annotations

import time

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

_T0 = time.perf_counter()
MODULES: list = []
if bpy is not None:
    from . import ops_server, prefs, props, ui
    from .core import host, ui_tasks

    # Yadro: fon vazifalari, sozlamalar, Scene.ges, server/login/commit, yadro panellari va menyu; qolgani — modules/
    MODULES = [ui_tasks, prefs, props, ops_server, ui, host]

IMPORT_MS = (time.perf_counter() - _T0) * 1000.0  # yadro fayllari importi; modullar importi — host.scan da
REGISTER_MS: dict[str, float] = {}  # oxirgi register(): yadro qismlari (ms)


def register():
    from .core import budget

    REGISTER_MS.clear()
    for m in MODULES:
        t = time.perf_counter()
        m.register()
        REGISTER_MS[m.__name__.rpartition(".")[2]] = (time.perf_counter() - t) * 1000.0
    reg = host.REG
    mods = {rid: rec.ms for rid, rec in reg.records.items() if rec.state == "enabled"} if reg is not None else {}
    print(budget.register_line(IMPORT_MS, REGISTER_MS, mods), flush=True)


def unregister():
    for m in reversed(MODULES):
        m.unregister()
