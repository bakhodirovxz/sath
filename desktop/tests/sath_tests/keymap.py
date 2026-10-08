"""P4 keymap (headless, --bonsai): Sath yorliqlari (Ctrl+Shift+G, modullar api.ui.keymap) Blender standart
keymapi (blender_default.py dan generatsiya — fon rejimida standart keymaplar bo'sh) va Bonsai/addon
yorliqlari bilan to'qnashmaydi (ataylab ustun qo'yilganlar — core/keys.ALLOWED); addon o'chirilganda
yorliqlar qaytadi, qayta yoqilganda takrorlanmaydi."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy


def _blender_default() -> list:
    path = Path(bpy.utils.system_resource("SCRIPTS")) / "presets" / "keyconfig" / "keymap_data"
    spec = importlib.util.spec_from_file_location("sath_kc_blender_default", path / "blender_default.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate_keymaps(mod.Params())


def _menu_items(kc) -> list:
    return [
        k for km in kc.keymaps for k in km.keymap_items
        if k.idname == "wm.call_menu" and getattr(k.properties, "name", "") == "SATH_MT_main"
    ]  # fmt: skip


def run(ctx):
    from sath.core import keys

    assert "bl_ext.user_default.bonsai" in bpy.context.preferences.addons, "Bonsai yoqilmagan (--bonsai)"
    kc = bpy.context.window_manager.keyconfigs.addon
    ours = [keys.chord(kmi, km.name, f"sath:{owner}") for owner, km, kmi in keys.ITEMS]
    menu = [c for c in ours if c.menu == "SATH_MT_main"]
    assert {c.keymap for c in menu} == {"3D View", "Object Mode"}, ours
    assert all((c.type, c.ctrl, c.shift, c.alt) == ("G", 1, 1, 0) for c in menu)  # spec §5: Ctrl+Shift+G
    mine = {kmi.as_pointer() for _o, _km, kmi in keys.ITEMS}
    addon = [
        keys.chord(k, km.name, "addon") for km in kc.keymaps for k in km.keymap_items
        if k.active and k.as_pointer() not in mine
    ]  # fmt: skip
    default = [
        keys.chord_from_event(name, idn, ev, props)
        for name, _args, data in _blender_default() for idn, ev, props in data["items"]
        if not (props and props.get("active") is False)
    ]  # fmt: skip
    assert len(default) > 1000, len(default)  # standart keymap haqiqatan o'qildi (sinov bo'sh emas)
    bad = keys.conflicts(ours, default + addon)
    assert not bad, "to'qnashuvlar:\n" + "\n".join(bad)
    stale = [k for k in keys.ALLOWED if not any(
        (c.keymap, c.idname) == k and any(keys.overlaps(s, c) for s in ours) for c in default + addon)]
    assert not stale, f"keys.ALLOWED eskirgan: {stale}"
    for (km_name, idn), why in keys.ALLOWED.items():
        print(f"keymap: ataylab ustun — «{km_name}» {idn}: {why}", flush=True)

    addon_pkg = ctx["addon"]
    addon_pkg.unregister()
    try:
        assert keys.ITEMS == [], keys.ITEMS
        assert not _menu_items(kc), "addon o'chirilgandan keyin Sath yorlig'i qoldi"
    finally:
        addon_pkg.register()
    assert len(_menu_items(kc)) == 2  # qayta yoqilganda takrorlanmaydi
