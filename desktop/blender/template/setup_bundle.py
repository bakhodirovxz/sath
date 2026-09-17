"""Sath bundle ichida ishlaydi (stage/blender.exe -b --app-template Sath --python setup_bundle.py):
app template `Sath` sukut, tema/prefs, portable userpref.blend va template startup.blend.
Extension lar oldindan `--command extension install-file` bilan o'rnatilgan bo'ladi."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

TEMPLATE_DIR = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None

p = bpy.context.preferences
p.app_template = "Sath"
p.view.show_splash = True
p.view.show_developer_ui = False
p.filepaths.use_relative_paths = True
for name in ("bl_ext.user_default.bonsai", "bl_ext.user_default.sath"):
    if name not in p.addons:
        bpy.ops.preferences.addon_enable(module=name)
bpy.ops.wm.save_userpref()
print("USERPREF:", bpy.utils.user_resource("CONFIG"), "app_template=", p.app_template, flush=True)

# startup.blend: bo'sh sahna (kub siz), metr, kamera/yorug'lik qoladi
bpy.ops.wm.read_homefile(app_template="Sath", use_factory_startup=True)
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
for sc in bpy.data.scenes:
    sc.name = "Sath"
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "METERS"
if TEMPLATE_DIR is not None:
    out = TEMPLATE_DIR / "startup.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True)
    print("STARTUP:", out, flush=True)
