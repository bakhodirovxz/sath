"""GUI: Sath ish joylari (run_gui_workspaces.py ishga tushiradi). Taymerlar zanjiri:
(1) ochilganda BIM faol, N-panel, egasi filtri, bim paneli ko'rinadi, Ctrl+Shift+G «Object Mode» da birinchi
→ SCADA ga; (2) SCADA da bim paneli yashirin, scada ko'rinadi, ISA kulrang fon → Simulation ga;
(3) Graph editor Timeline va 3D orasida, belgi o'chgan, chizish xatosiz → [GUI-OK].
Repo rejimi: addon repo dan (blender_headless.load_addon); bundle (SATH_GUI_BUNDLE=1): o'rnatilgan extension."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BUNDLE = os.environ.get("SATH_GUI_BUNDLE") == "1"
PKG = "bl_ext.user_default.sath" if BUNDLE else "sath"
if not BUNDLE:
    sys.path.insert(0, str(HERE))
    import blender_headless  # noqa: E402

    blender_headless.load_addon()


def _win():
    return bpy.context.window_manager.windows[0]


def _W():
    return next((m for k, m in sys.modules.items() if k.endswith(".workspaces") and hasattr(m, "finish")), None)


def _tagged(tag):
    return next(w for w in bpy.data.workspaces if w.get("sath_ws") == tag)


def _visible(mod_id, ws) -> bool:
    panels, host = sys.modules[f"{PKG}.core.panels"], sys.modules[f"{PKG}.core.host"]
    return panels.in_workspace(host.record(mod_id).manifest, ws)


def _draw(win, shot: str | None = None) -> None:
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
        if shot:
            bpy.ops.screen.screenshot(filepath=shot)
            print("[GUI-SHOT]", shot, flush=True)


def bim():
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "BIM", f"ochilganda faol: {ws.name}"  # spec P4: BIM ish joyida ochiladi
    W = _W()
    assert sorted(W.tagged(bpy.data)) == sorted(W.ORDER)
    assert W.CHAIN_DONE[0], "tab tartibi zanjiri tugamadi"  # tartib skrinshotda ko'rinadi (Python da ochiq emas)
    names = {w.name for w in bpy.data.workspaces}
    assert not names & set(W.REMOVE), sorted(names & set(W.REMOVE))
    v3d = [a for a in win.screen.areas if a.type == "VIEW_3D"]
    assert v3d and all(a.spaces.active.show_region_ui for a in v3d)
    assert ws.use_filter_by_owner
    assert _visible("bim", ws) and not _visible("scada", ws)
    km = bpy.context.window_manager.keyconfigs.user.keymaps.get("Object Mode")
    first = next((k for k in km.keymap_items if k.active and k.type == "G" and k.value == "PRESS"
                  and k.ctrl == 1 and k.shift == 1 and k.alt == 0), None) if km else None  # fmt: skip
    assert first is not None and first.idname == "wm.call_menu", first and first.idname
    assert first.properties.name == "SATH_MT_main"  # addon elementi standartdan oldin (core/keys.ALLOWED)
    _draw(win, os.environ.get("SATH_SCREENSHOT"))
    win.workspace = _tagged("SCADA")


def scada():
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "SCADA", ws.name
    assert _visible("scada", ws) and not _visible("bim", ws)
    sh = next(a for a in win.screen.areas if a.type == "VIEW_3D").spaces.active.shading
    assert sh.background_type == "VIEWPORT" and sh.color_type == "OBJECT"
    _draw(win)
    win.workspace = _tagged("Simulation")


def simulation():
    # Eslatma: startup zanjiri Simulation ni ham faollashtirib o'tadi, shuning uchun bu qadam birinchi
    # almashishni emas, msgbus (Window.workspace) yo'lini tekshiradi. reset_workspaces ham tablarni ~0.7 s
    # almashtiradi va uning INFO xabari zanjir tugashidan oldin chiqadi.
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "Simulation", ws.name
    assert not ws.get(_W().TODO), "Graph editor yakunlanmadi (msgbus finish ishlamadi)"
    areas = win.screen.areas
    g = [a for a in areas if a.type == "GRAPH_EDITOR"]
    v = [a for a in areas if a.type == "VIEW_3D"]
    t = [a for a in areas if a.ui_type == "TIMELINE"]
    assert len(g) == 1 and len(v) == 1 and t, [(a.type, a.ui_type) for a in areas]
    assert t[0].y < g[0].y < v[0].y, "pastdan yuqoriga: Timeline, Graph, 3D"
    _draw(win)


def _quit():
    bpy.context.preferences.use_preferences_save = False  # quit userpref.blend ni yozmasin
    bpy.ops.wm.quit_blender()


STEPS = [bim, scada, simulation]
_i = 0
_wait = [0]


def _tick():
    global _i
    W = _W()
    if W is None:
        print("[GUI-FAIL] workspaces moduli yuklanmagan (template ishlamadi)", flush=True)
        _quit()
        return None
    if _i == 0 and not W.CHAIN_DONE[0] and _wait[0] < 40:  # tab tartibi zanjiri (taymerlar) tugashini kutamiz
        _wait[0] += 1
        return 0.5
    try:
        STEPS[_i]()
        print(f"GUI-WS {STEPS[_i].__name__}: OK", flush=True)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("[GUI-FAIL]", flush=True)
        _quit()
        return None
    _i += 1
    if _i == len(STEPS):
        print("[GUI-OK]", flush=True)
        _quit()
        return None
    return 0.7  # Window.workspace almashinuvi keyingi siklda qo'llanadi


bpy.app.timers.register(_tick, first_interval=3.0, persistent=True)  # sath_boot read_homefile dan omon qolsin
