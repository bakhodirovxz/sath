"""P4 ish joylari (headless): Sath app template (repo dan) factory startup da ish joylarini quradi — teglar,
olib tashlanganlar, Scripting faqat developer UI da, egasi filtri, area lar; qayta chaqirish idempotent,
`sath.reset_workspaces(rebuild=True)` qayta quradi; SathPanel tegi modul manifestiga mos; theme_sath.xml
qo'llanadi. Oynali qism (BIM faol, Graph editor yakunlanishi) — desktop/tests/run_gui_workspaces.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"


def _template():
    """App template paketi (Blender uni bl_app_templates_* dan yuklaydi; bu yerda — repo dan)."""
    name = "sath_app_template"
    spec = importlib.util.spec_from_file_location(
        name, TEMPLATE / "__init__.py", submodule_search_locations=[str(TEMPLATE)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _areas(ws, kind: str) -> list:
    return [a for a in ws.screens[0].areas if a.type == kind]


def _check(W, *, dev: bool) -> dict:
    names = {w.name for w in bpy.data.workspaces}
    tags = W.tagged(bpy.data)
    assert sorted(tags) == sorted(W.ORDER), sorted(tags)
    assert sum(1 for w in bpy.data.workspaces if w.get(W.TAG)) == len(W.ORDER), "teg takrorlandi"
    assert not names & set(W.REMOVE), sorted(names & set(W.REMOVE))
    assert ("Scripting" in names) is dev, (dev, sorted(names))
    assert {"Layout", "Modeling", "Animation"} <= names, sorted(names)
    for t, ws in tags.items():
        owners = {o.name for o in ws.owner_ids}
        assert ws.use_filter_by_owner and set(W.DEFAULT_OWNER_IDS) <= owners, (t, owners)
    assert _areas(tags["BIM"], "OUTLINER") and _areas(tags["BIM"], "PROPERTIES")
    assert all(a.spaces.active.show_region_ui for a in _areas(tags["BIM"], "VIEW_3D"))
    assert len(_areas(tags["Compare"], "VIEW_3D")) == 2
    sim = tags["Simulation"]
    assert any(a.ui_type == "TIMELINE" for a in sim.screens[0].areas)
    assert len(_areas(sim, "VIEW_3D")) == 2 and sim.get(W.TODO) == 1  # Graph — ish joyi ochilganda (GUI)
    sh = _areas(tags["SCADA"], "VIEW_3D")[0].spaces.active.shading
    assert sh.color_type == "OBJECT" and sh.background_type == "VIEWPORT"
    grey = W.srgb_to_linear(W.ISA_GREY)
    assert all(abs(x - y) < 1e-4 for x, y in zip(sh.background_color, grey, strict=True))
    return tags


def run(ctx):
    from sath.core import host, panels, tokens

    tpl = _template()
    W = tpl.workspaces
    view = bpy.context.preferences.view
    dev0 = view.show_developer_ui
    tpl.register()
    try:
        view.show_developer_ui = False
        bpy.ops.wm.read_homefile(use_factory_startup=True)  # load_factory_startup_post → template ilgagi
        _check(W, dev=False)
        assert bpy.context.scene.view_settings.view_transform == "Standard"
        rep = W.ensure(bpy.context)
        assert rep == {"created": [], "removed": [], "kept": []}, rep  # idempotent
        assert bpy.ops.sath.reset_workspaces(rebuild=True) == {"FINISHED"}
        tags = _check(W, dev=False)

        rec = {m: host.record(m).manifest for m in ("bim", "scada", "sim", "twin", "review", "io")}
        assert panels.in_workspace(rec["bim"], tags["BIM"])
        assert not panels.in_workspace(rec["bim"], tags["SCADA"])
        assert panels.in_workspace(rec["scada"], tags["SCADA"])
        assert not panels.in_workspace(rec["scada"], tags["BIM"])
        assert panels.in_workspace(rec["sim"], tags["Simulation"])
        assert panels.in_workspace(rec["twin"], tags["Simulation"])
        assert panels.in_workspace(rec["review"], tags["Compare"])
        assert not panels.in_workspace(rec["io"], tags["Compare"])
        layout = bpy.data.workspaces["Layout"]
        assert all(panels.in_workspace(m, layout) for m in rec.values())  # tegsiz — hammasi

        view.show_developer_ui = True
        bpy.ops.wm.read_homefile(use_factory_startup=True)
        _check(W, dev=True)

        theme = bpy.context.preferences.themes[0]
        r = bpy.ops.script.execute_preset(
            filepath=str(TEMPLATE / "theme_sath.xml"), menu_idname="USERPREF_MT_interface_theme_presets"
        )
        assert r == {"FINISHED"}, r
        for got, hex_ in (
            (theme.view_3d.object_active, tokens.PAL["highlight"]),
            (theme.user_interface.axis_x, tokens.PAL["axisX"]),
        ):
            want = tokens.parse(hex_)[:3]
            assert all(abs(a - b) < 1 / 255 for a, b in zip(got, want, strict=True)), (tuple(got), hex_)
    finally:
        bpy.ops.preferences.reset_default_theme()
        view.show_developer_ui = dev0
        tpl.unregister()
    assert not hasattr(bpy.types, "SATH_OT_reset_workspaces")
    assert tpl.load_handler not in bpy.app.handlers.load_factory_startup_post
