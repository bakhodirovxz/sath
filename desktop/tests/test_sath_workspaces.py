"""Sath ish joylari (P4, spec §5): template/Sath/workspaces.py ma'lumot qismi — teglar reyestr va modul
manifestlariga mos, olib tashlanadiganlar, ISA kulrangi web tokeni, egalar. Blender qismi — headless
`workspaces` va GUI `run_gui_workspaces.py`."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import registry, tokens  # noqa: E402

TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"
MODULES = ROOT / "desktop" / "blender" / "sath" / "modules"


@pytest.fixture(scope="module")
def ws():
    spec = importlib.util.spec_from_file_location("sath_template_workspaces", TEMPLATE / "workspaces.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # bpy siz import bo'lishi shart (bpy faqat funksiyalar ichida)
    return mod


def test_tags_match_registry_and_module_manifests(ws):
    assert ws.TAG == registry.WORKSPACE_TAG and ws.ORDER == registry.WORKSPACES
    manifests, errors = registry.discover(MODULES)
    assert errors == []
    used = {w for m in manifests for w in m.workspaces}
    assert used == set(ws.ORDER), used ^ set(ws.ORDER)  # har ish joyida modul paneli bor, begona teg yo'q


def test_removed_kept_and_dev_only(ws):
    assert set(ws.REMOVE) == {
        "Sculpting", "UV Editing", "Texture Paint", "Shading", "Rendering", "Compositing", "Geometry Nodes",
    }  # fmt: skip
    assert ws.DEV_ONLY == ("Scripting",) and "Scripting" in ws.KEEP
    assert not set(ws.REMOVE) & set(ws.KEEP) and not set(ws.ORDER) & (set(ws.KEEP) | set(ws.REMOVE))
    assert ws.BASE in ws.KEEP


def test_scada_grey_is_web_operator_canvas(ws):
    assert ws.ISA_GREY == tokens.THEMES["operator"]["canvas"]
    assert ws.srgb_to_linear(ws.ISA_GREY) == pytest.approx(tokens.rgba("canvas", "operator")[:3])


def test_owner_ids_from_enabled_addons_plus_bundle_defaults(ws):
    addons = {"bl_ext.blender_org.bonsai": 1, "bl_ext.user_default.sath": 1, "boshqa_addon": 1}
    ctx = SimpleNamespace(preferences=SimpleNamespace(addons=addons))
    assert ws.owner_ids(ctx) == [
        "bl_ext.blender_org.bonsai", "bl_ext.user_default.bonsai", "bl_ext.user_default.sath",
    ]  # fmt: skip


class _Area:
    def __init__(self, kind, y, ptr, *, applies=True):
        self.type, self.y, self._p, self._applies, self.ui_type = kind, y, ptr, applies, kind

    def as_pointer(self):
        return self._p

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k == "ui_type" and v == "FCURVES" and getattr(self, "_applies", False):
            object.__setattr__(self, "type", "GRAPH_EDITOR")


class _WS(dict):
    def __init__(self, tag, screen, **kw):
        super().__init__(kw)
        self["sath_ws"] = tag
        self.screens = [screen]


def _win(ws, screen):
    return SimpleNamespace(workspace=ws, screen=screen)


def test_finish_picks_bottom_view3d_and_clears_todo(ws):
    top, bottom = _Area("VIEW_3D", 300, 1), _Area("VIEW_3D", 10, 2)
    screen = SimpleNamespace(areas=[top, bottom], as_pointer=lambda: 99)
    w = _WS("Simulation", screen, sath_ws_todo=1)
    assert ws.finish(_win(w, screen)) is True
    assert bottom.type == "GRAPH_EDITOR" and top.type == "VIEW_3D" and ws.TODO not in w


def test_finish_retries_when_not_applied_yet(ws):
    top, bottom = _Area("VIEW_3D", 300, 1), _Area("VIEW_3D", 10, 2, applies=False)
    screen = SimpleNamespace(areas=[top, bottom], as_pointer=lambda: 99)
    w = _WS("Simulation", screen, sath_ws_todo=1)
    assert ws.finish(_win(w, screen)) is False and w[ws.TODO] == 1


def test_finish_leaves_foreign_screen_untouched(ws):
    a, b = _Area("VIEW_3D", 300, 1), _Area("VIEW_3D", 10, 2)
    own = SimpleNamespace(areas=[a, b], as_pointer=lambda: 99)
    shown = SimpleNamespace(areas=[a, b], as_pointer=lambda: 7)
    w = _WS("Simulation", own, sath_ws_todo=1)
    assert ws.finish(_win(w, shown)) is False
    assert b.type == "VIEW_3D" and w[ws.TODO] == 1


def test_finish_gives_up_without_two_view3d(ws):
    only = _Area("VIEW_3D", 10, 1)
    screen = SimpleNamespace(areas=[only], as_pointer=lambda: 99)
    w = _WS("Simulation", screen, sath_ws_todo=1)
    assert ws.finish(_win(w, screen)) is True and ws.TODO not in w
    assert ws.finish(_win(w, screen)) is False  # TODO yo'q — hech narsa
