"""core/keys.py (P4, spec §5): yorliqlar to'qnashuvi qoidalari — bpy siz."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import keys  # noqa: E402
from sath.core.keys import Chord  # noqa: E402


def C(keymap, type_, ctrl=0, shift=0, alt=0, idname="x.op", owner="blender", value="PRESS", menu=""):
    return Chord(keymap, type_, value, ctrl, shift, alt, 0, idname, owner, menu)


SATH = C("3D View", "G", 1, 1, idname="wm.call_menu", owner="sath:core", menu="SATH_MT_main")


def test_overlap_rules():
    assert keys.overlaps(SATH, C("Object Mode", "G", 1, 1))
    assert not keys.overlaps(SATH, C("Object Mode", "G", 1, 0))
    assert keys.overlaps(SATH, C("3D View", "G", -1, -1, -1))  # «any» modifikator
    assert not keys.overlaps(SATH, C("3D View", "G", 1, 1, value="RELEASE"))
    assert keys.overlaps(SATH, C("3D View", "G", 1, 1, value="CLICK"))


def test_conflicts_scope_allowed_and_own_duplicates():
    other = [
        C("Object Mode", "G", 1, 1, idname="collection.objects_add_active"),  # ALLOWED
        C("Node Editor", "G", 1, 1, idname="node.select_grouped"),  # 3D ko'rinishda emas
        C("Window", "N", 1, idname="wm.call_menu", owner="addon", menu="X"),  # boshqa chord
    ]
    ours = [SATH, SATH._replace(keymap="Object Mode")]  # bir xil menyu ikki keymapda — to'qnashuv emas
    assert keys.conflicts(ours, other) == []
    bad = keys.conflicts(ours, other, allowed={})
    assert len(bad) == 2 and all("collection.objects_add_active" in b for b in bad)
    clash = C("Mesh", "G", 1, 1, idname="mesh.yangi")
    assert len(keys.conflicts([SATH], [clash])) == 1  # rejim keymapi 3D View dan oldin ishlaydi
    twin = C("3D View", "G", 1, 1, idname="sath.boshqa", owner="sath:twin")
    assert any("sath.boshqa" in b for b in keys.conflicts([SATH, twin], []))  # Sath ichida


def test_scope_for_non_3d_keymaps_is_own_plus_global():
    assert keys.scope("Outliner") == frozenset({"Outliner", "Window", "Screen"})
    assert "Object Mode" in keys.scope("3D View")


def test_chord_from_blender_default_event_and_kmi():
    c = keys.chord_from_event(
        "Object Mode", "wm.call_menu", {"type": "G", "value": "PRESS", "ctrl": True, "shift": True},
        {"properties": [("name", "VIEW3D_MT_x")]},
    )
    assert (c.ctrl, c.shift, c.alt, c.menu) == (1, 1, 0, "VIEW3D_MT_x")
    ev = {"type": "TIMER1", "value": "ANY", "any": True}
    anyc = keys.chord_from_event("3D View", "view3d.smoothview", ev, None)
    assert (anyc.ctrl, anyc.shift, anyc.alt, anyc.oskey) == (-1, -1, -1, -1)
    kmi = SimpleNamespace(type="G", value="PRESS", ctrl=1, shift=1, alt=0, oskey=0, any=False,
                          idname="wm.call_menu", properties=SimpleNamespace(name="SATH_MT_main"))  # fmt: skip
    assert keys.chord(kmi, "3D View", "sath:core") == SATH
