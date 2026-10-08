"""P3 modul tizimi (headless): imzolangan foydalanuvchi moduli jonli yoqiladi/o'chiriladi (panel, operator, sahna
guruhi, hodisa, menyu qaytadi; fon vazifasi bekor qilinadi), yiqilgan modul izolyatsiya qilinadi, imzosiz yoki
o'zgartirilgan modul yuklanmaydi. Keyingi vazifalar birinchi tomon modullari va rolga sezgir UI tekshiruvlarini qo'shadi."""

from __future__ import annotations

import base64
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]

HELLO_PY = '''"""Test moduli (P3)."""
import bpy

HITS = []


class HelloProps(bpy.types.PropertyGroup):
    count: bpy.props.IntProperty()


class SATH_OT_hello_test(bpy.types.Operator):
    bl_idname = "sath.hello_test"
    bl_label = "Salom"

    def execute(self, context):
        context.scene.sath_hello.count += 1
        return {"FINISHED"}


def register(api):
    class SATH_PT_hello_test(api.ui.SathPanel, bpy.types.Panel):
        bl_label = "Salom"

        def draw(self, context):
            self.layout.operator("sath.hello_test")

    api.props.scene_group("hello", HelloProps)
    api.register_classes("hello", [SATH_OT_hello_test, SATH_PT_hello_test])
    api.events.subscribe("project.changed", HITS.append, owner="hello")
    api.ui.main_menu("hello", lambda layout, context: layout.operator("sath.hello_test"))
'''

BROKEN_PY = '''import bpy


class SATH_OT_broken_test(bpy.types.Operator):
    bl_idname = "sath.broken_test"
    bl_label = "Yiqiluvchi"

    def execute(self, context):
        return {"FINISHED"}


def register(api):
    api.register_classes("broken", [SATH_OT_broken_test])
    raise RuntimeError("ataylab yiqildi")
'''

FLAKY_BAD = 'def register(api):\n    raise RuntimeError("hali tuzatilmagan")\n'
FLAKY_OK = '"""Tuzatilgan versiya."""\n\nSTATE = "tuzatildi"\n\n\ndef register(api):\n    pass\n'


def _toml(mid: str) -> str:
    return f'id = "{mid}"\nname = "{mid} (test)"\nversion = "1.0.0"\napi = ">=1.0,<2"\norder = 900\n'


def _registered(op: str) -> bool:
    """bpy.ops.sath.<op> ro'yxatdami (ro'yxatdan chiqqanda get_rna_type xato beradi)."""
    try:
        getattr(bpy.ops.sath, op).get_rna_type()
    except Exception:  # noqa: BLE001
        return False
    return True


class _Layout:
    """draw_prefs/draw_menus uchun soxta UILayout: chaqiruvlarni yozib boradi."""

    def __init__(self, calls: list) -> None:
        self.calls = calls

    def _child(self, *_a, **_k):
        return _Layout(self.calls)

    box = row = column = _child

    def label(self, text="", **_k):
        self.calls.append(("label", text))

    def prop(self, _data, name, **_k):
        self.calls.append(("prop", name))

    def separator(self, **_k):
        self.calls.append(("separator", ""))

    def operator(self, idname, **_k):
        self.calls.append(("operator", idname))
        return type("Props", (), {})()


def _user_modules():
    from sath import props
    from sath.core import events, host
    from sath.core.tasks import TASKS
    from sath.prefs import prefs

    sys.path.insert(0, str(ROOT / "desktop" / "build"))
    import sign_module

    seed = bytes(range(32))
    tmp = Path(tempfile.mkdtemp(prefix="sath_mod_"))
    for mid, code in (("hello", HELLO_PY), ("broken", BROKEN_PY), ("unsigned", HELLO_PY)):
        d = tmp / mid
        d.mkdir()
        (d / "sath_module.toml").write_text(_toml(mid), encoding="utf-8")
        (d / "__init__.py").write_text(code, encoding="utf-8")
        if mid != "unsigned":
            sign_module.sign_module(d, seed)
    p = prefs()
    os.environ["SATH_USER_MODULES"] = str(tmp)
    p.module_public_keys = base64.b64encode(sign_module.public_key(seed)).decode()
    p.allow_user_modules = True  # update callback skanerlaydi; quyidagi scan — aniq bo'lishi uchun
    host.scan()
    s = bpy.context.scene
    try:
        rec = host.record("hello")
        assert rec is not None and rec.state == "enabled", (rec, host.REG.broken)
        assert rec.manifest.origin == "user"
        assert rec.module.__name__ == "_sath_user_hello"  # faqat xavfsiz yuklovchi orqali
        pt = bpy.types.SATH_PT_hello_test
        assert pt.bl_category == "Sath" and pt.bl_order == 900 and _registered("hello_test")
        assert bpy.ops.sath.hello_test() == {"FINISHED"} and s.sath_hello.count == 1
        snap = props.snapshot_scene(s)
        s.sath_hello.count = 7
        props.restore_scene(s, snap)
        assert s.sath_hello.count == 1
        events.publish("project.changed", project_id=1)
        assert rec.module.HITS == [{"project_id": 1}]
        assert "hello" in [m for m, _ in host._menus]

        # bitta modulning menyusi yiqilsa — qolganlari chiziladi
        calls: list = []
        boom = ("hello", lambda layout, context: 1 / 0)
        host._menus.insert(0, boom)
        try:
            host.draw_menus(_Layout(calls), bpy.context)
        finally:
            host._menus.remove(boom)
        assert ("operator", "sath.hello_test") in calls

        bad = host.record("broken")
        assert bad.state == "failed" and "ataylab yiqildi" in bad.error and not _registered("broken_test")
        assert any(label.startswith("unsigned") and "imzolanmagan" in msg for label, msg in host.REG.broken)

        # Sozlamalar ro'yxati: belgi, nom+versiya, traceback, yuklanmaganlar, uchinchi tomon sozlamalari
        calls = []
        host.draw_prefs(_Layout(calls))
        labels = [t for k, t in calls if k == "label"]
        assert calls.count(("operator", "sath.module_toggle")) == len(set(host.REG.records) - host.PINNED)
        assert "hello (test)  1.0.0" in labels and any("ataylab yiqildi" in t for t in labels)
        assert any(t.startswith("unsigned (foydalanuvchi)") for t in labels)
        assert ("prop", "module_public_keys") in calls and ("operator", "sath.modules_rescan") in calls

        TASKS.inline = False  # Review Focus 1: modul o'chganda uning fon vazifasi bekor qilinadi
        try:
            gone: list = []
            t = TASKS.run("uzun", lambda c: c.sleep(5), key="hello.uzun", on_cancel=lambda: gone.append(1))
            other = TASKS.run("boshqa", lambda c: c.sleep(5), key="hellox.uzun")
            assert host.set_enabled("hello", False) == ["hello"]
            assert t.cancelled and t.dropped and not other.cancelled
            other.cancel()
            TASKS.drain(5)
            assert gone == []  # o'chirilgan modul yopilmasi (on_cancel) chaqirilmadi
        finally:
            TASKS.inline = True
        assert not hasattr(bpy.types, "SATH_PT_hello_test") and not _registered("hello_test")
        assert not hasattr(bpy.types.Scene, "sath_hello") and "hello" not in [m for m, _ in host._menus]
        events.publish("project.changed", project_id=2)
        assert rec.module.HITS == [{"project_id": 1}]  # obuna bekor bo'ldi
        assert json.loads(p.module_states)["hello"] is False

        assert bpy.ops.sath.module_toggle(module_id="hello") == {"FINISHED"}
        assert host.is_enabled("hello") and _registered("hello_test")
        assert s.sath_hello.count == 1  # sahnadagi ma'lumot o'chirib-yoqishdan omon qoldi

        (tmp / "hello" / "__init__.py").write_text(HELLO_PY + "\n# o'zgartirildi\n", encoding="utf-8")
        assert bpy.ops.sath.modules_rescan() == {"FINISHED"}
        assert host.record("hello") is None and not _registered("hello_test")
        assert any(label.startswith("hello") and "imzo" in msg for label, msg in host.REG.broken)

        # qayta imzolangan yangi kod (manifest o'zgarmagan) — qayta skanerda yangi kod yuklanadi
        (tmp / "hello" / "__init__.py").write_text(HELLO_PY + "\nVERSION_MARK = 2\n", encoding="utf-8")
        sign_module.sign_module(tmp / "hello", seed)
        host.scan()
        rec2 = host.record("hello")
        assert rec2 is not None and rec2.state == "enabled" and rec2.module.VERSION_MARK == 2, host.REG.broken
        (tmp / "hello" / "__init__.py").write_text(HELLO_PY + "\nVERSION_MARK = 3\n", encoding="utf-8")
        sign_module.sign_module(tmp / "hello", seed)
        host.scan()
        rec3 = host.record("hello")
        assert rec3 is not rec2 and rec3.module.VERSION_MARK == 3 and rec2.state == "disabled"
    finally:
        p.allow_user_modules = False
        host.scan()
        os.environ.pop("SATH_USER_MODULES", None)
        p.module_states = "{}"
        shutil.rmtree(tmp, ignore_errors=True)
    assert host.record("broken") is None and host.REG.broken == []
    assert not _registered("hello_test") and "_sath_user_hello" not in sys.modules  # yo'qolgan modul tushirildi


def _bundled_retry():
    """register() i yiqilgan birinchi tomon moduli tuzatilgach qayta yoqilsa — eski (sys.modules dagi) nusxa emas,
    yangi kod import qilinadi."""
    from sath import modules
    from sath.core import host
    from sath.prefs import prefs

    tmp = Path(tempfile.mkdtemp(prefix="sath_bmod_"))
    d = tmp / "flaky"
    d.mkdir()
    (d / "sath_module.toml").write_text(_toml("flaky"), encoding="utf-8")
    (d / "__init__.py").write_text(FLAKY_BAD, encoding="utf-8")
    old = host.BUNDLED
    modules.__path__.append(str(tmp))
    host.BUNDLED = tmp
    name = f"{host.ROOT_PKG}.modules.flaky"
    try:
        host.scan()
        rec = host.record("flaky")
        assert rec is not None and rec.state == "failed" and "hali tuzatilmagan" in rec.error, host.REG.broken
        assert name in sys.modules  # register() yiqildi, modul import qilingan holda qoldi
        (d / "__init__.py").write_text(FLAKY_OK, encoding="utf-8")
        importlib.invalidate_caches()
        assert host.set_enabled("flaky", True) == ["flaky"], rec.error
        assert rec.state == "enabled" and rec.module.STATE == "tuzatildi"
    finally:
        host.BUNDLED = old
        modules.__path__.remove(str(tmp))
        host.scan()
        sys.modules.pop(name, None)
        prefs().module_states = "{}"
        shutil.rmtree(tmp, ignore_errors=True)
    assert host.record("flaky") is None


def run(ctx):
    _user_modules()
    _bundled_retry()
