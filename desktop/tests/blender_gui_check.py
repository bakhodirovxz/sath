"""GUI sinovi: e2e oqim + N-panel «Sath» barcha panellari ochiq holda bir necha marta chiziladi, keyin
Blender yopiladi. Konsolda Python xatosi bo'lmasligi kerak.

  set SATH_PANELS_OPEN=1 && blender --python desktop/tests/blender_gui_check.py
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["SATH_PANELS_OPEN"] = "1"
import blender_headless  # noqa: E402

os.environ.setdefault("GES_FC_HOME", os.path.join(os.path.expanduser("~"), "Tools", "fc-py313"))
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
addon = blender_headless.load_addon()
sys.path.insert(0, str(HERE / "sath_tests"))
ok = True
try:
    importlib.import_module(os.environ.get("GES_GUI_TEST", "e2e_server")).run({"addon": addon})
except Exception:  # noqa: BLE001
    traceback.print_exc()
    ok = False


def _show_and_draw():
    try:
        _draw()
    finally:
        bpy.ops.wm.quit_blender()
    return None


def _draw():
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.show_region_ui = True  # panellar sinovda «Item» yorlig'ida (sukut faol)
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=5)
    print("[GUI-OK]" if ok else "[GUI-FAIL]", flush=True)


bpy.app.timers.register(_show_and_draw, first_interval=1.0)
