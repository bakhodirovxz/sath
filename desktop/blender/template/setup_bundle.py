"""Sath bundle ichida ishlaydi (stage/blender.exe -b --app-template Sath --python setup_bundle.py -- <template>):
app template `Sath` sukut, Sath temasi (theme_sath.xml — Blender Dark + Sath farqlari), prefs, portable
userpref.blend va template startup.blend (Sath ish joylari bilan — template ilgagi workspaces.ensure quradi).
Extension lar oldindan `--command extension install-file` bilan o'rnatilgan bo'ladi."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

TEMPLATE_DIR = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None

# startup.blend: bo'sh sahna (kub siz), metr, kamera/yorug'lik + Sath ish joylari. Scripting fayl ichida qolsin
# (developer UI yoqilsa kerak) — ilgak uni developer UI o'chiq bo'lsa olib tashlaydi, shuning uchun qurishda
# vaqtincha yoqiladi; har ishga tushishda ilgak qayta ishlaydi va Scripting ni olib tashlaydi.
# Eski startup.blend (oldingi yig'ish) o'chiriladi — aks holda u zavod holati o'rniga yuklanib, ish joylari
# takrorlanadi (BIM.001).
if TEMPLATE_DIR is not None:
    for stale in ("startup.blend", "startup.blend1"):
        (TEMPLATE_DIR / stale).unlink(missing_ok=True)
bpy.context.preferences.view.show_developer_ui = True
bpy.ops.wm.read_homefile(app_template="Sath", use_factory_startup=True)

for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
for sc in bpy.data.scenes:
    sc.name = "Sath"
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "METERS"
tags = sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws"))
print("WORKSPACES:", tags, flush=True)
EXPECTED = ["BIM", "Compare", "SCADA", "Simulation"]  # = sorted(workspaces.ORDER); ilgak hech narsa qurmasa ham yiqiladi
if tags != EXPECTED:
    raise SystemExit(f"Sath ish joylari qurilmadi: {tags} != {EXPECTED}")
if TEMPLATE_DIR is not None:
    out = TEMPLATE_DIR / "startup.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True)
    print("STARTUP:", out, flush=True)
    (TEMPLATE_DIR / "startup.blend1").unlink(missing_ok=True)
# read_homefile(use_factory_startup=True) prefs ni ham zavod holatiga qaytaradi — sozlamalar shundan KEYIN.
# startup.blend extension lar yoqilmasdan SAQLANADI (yoqish ish joylarini zavod holatiga qaytaradi/Bonsai o'z
# «BIM» ini qo'shadi); Bonsai ning should_setup_workspace i o'chiriladi (Sath BIM bilan to'qnashmasin).
p = bpy.context.preferences  # app_template userpref ga yozilmaydi — Sath ga sath_boot.py o'tkazadi
p.view.show_developer_ui = False
p.view.show_splash = True
p.filepaths.use_relative_paths = True
for name in ("bl_ext.user_default.bonsai", "bl_ext.user_default.sath"):
    if name not in p.addons:
        bpy.ops.preferences.addon_enable(module=name)
p.addons["bl_ext.user_default.bonsai"].preferences.should_setup_workspace = False
if TEMPLATE_DIR is not None:
    theme = TEMPLATE_DIR / "theme_sath.xml"
    bpy.ops.preferences.reset_default_theme()  # Blender Dark ga qaytarib, ustiga Sath farqlari
    bpy.ops.script.execute_preset(filepath=str(theme), menu_idname="USERPREF_MT_interface_theme_presets")
    p.themes[0].filepath = ""  # build mashinasi yo'li userpref da qolmasin
    print("THEME:", theme.name, flush=True)
cfg = Path(bpy.utils.user_resource("CONFIG")).resolve()
portable = (Path(bpy.app.binary_path).parent / "portable").resolve()
if portable not in cfg.parents:  # BLENDER_USER_CONFIG va h.k. — prefs bundle dan tashqariga yozilmasin
    raise SystemExit(f"prefs portable/ ga yozilmaydi: {cfg} (kutilgan: {portable})")
bpy.ops.wm.save_userpref()
print("USERPREF:", cfg, flush=True)
if TEMPLATE_DIR is not None:  # diskdagi startup.blend: Sath ish joylari faylning o'zida bormi (xotiradagi emas)
    bpy.ops.wm.open_mainfile(filepath=str(TEMPLATE_DIR / "startup.blend"))
    disk = sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws"))
    print("STARTUP-DISK:", disk, flush=True)
    if disk != EXPECTED:
        raise SystemExit(f"startup.blend da Sath ish joylari yo'q: {disk} != {EXPECTED}")
