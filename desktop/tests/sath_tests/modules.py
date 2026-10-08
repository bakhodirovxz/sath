"""P3 modul tizimi (headless): imzolangan foydalanuvchi moduli jonli yoqiladi/o'chiriladi (panel, operator, sahna
guruhi, hodisa, menyu qaytadi; fon vazifasi bekor qilinadi), yiqilgan modul izolyatsiya qilinadi, imzosiz yoki
o'zgartirilgan modul yuklanmaydi. Keyingi vazifalar birinchi tomon modullari va rolga sezgir UI tekshiruvlarini qo'shadi."""

from __future__ import annotations

import base64
import contextlib
import importlib
import io
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

    def operator_menu_enum(self, idname, _prop, **_k):
        self.calls.append(("operator", idname))


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
    env_keys = os.environ.pop("SATH_MODULE_PUBLIC_KEYS", None)  # muhit kalitlari bekor qilinmaydi — testda bo'lmasin
    old_update_key = p.update_public_key
    p.update_public_key = ""
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
        mod = rec.module
        assert mod.HITS == [{"project_id": 1}]
        assert "hello" in [m for m, _ in host._menus]

        # bitta modulning menyusi yiqilsa — qolganlari chiziladi
        calls: list = []
        boom = ("hello", lambda layout, context: 1 / 0)
        host._menus.insert(0, boom)
        try:
            host.draw_menus(_Layout(calls), bpy.context)
        finally:
            host._menus.remove(boom)
        assert ("operator", "sath.hello_test") in calls and ("operator", "sath.add_object") in calls  # bim bandi

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
        assert mod.HITS == [{"project_id": 1}]  # obuna bekor bo'ldi
        assert rec.module is None  # kesh nusxa tashlandi — qayta yoqish yana xavfsiz yuklovchi (imzo + kalitlar) orqali
        assert json.loads(p.module_states)["hello"] is False

        assert bpy.ops.sath.module_toggle(module_id="hello") == {"FINISHED"}
        assert host.is_enabled("hello") and _registered("hello_test") and rec.module is not mod
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

        # Important 1: nashriyotchi kaliti Sozlamalardan olib tashlansa — Rescan siz darhol o'chadi (update= -> scan)
        key = p.module_public_keys
        p.module_public_keys = ""
        assert host.record("hello") is None and not _registered("hello_test"), host.REG.broken
        assert not hasattr(bpy.types.Scene, "sath_hello") and "_sath_user_hello" not in sys.modules
        assert any(label.startswith("hello") and "kalit" in msg for label, msg in host.REG.broken), host.REG.broken
        p.module_public_keys = key  # ishonch qaytdi — modul yana (tekshirilib) yuklanadi
        rec4 = host.record("hello")
        assert rec4 is not None and rec4.state == "enabled" and _registered("hello_test"), host.REG.broken
    finally:
        p.allow_user_modules = False
        host.scan()
        os.environ.pop("SATH_USER_MODULES", None)
        if env_keys is not None:
            os.environ["SATH_MODULE_PUBLIC_KEYS"] = env_keys
        p.update_public_key = old_update_key
        p.module_public_keys = ""
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


def _core_only():
    """Yadro (Server, Model, bildirishnomalar, menyu, update, status bar) modul emas — doim ro'yxatda."""
    from sath.core import host

    assert host.record("legacy") is None
    assert hasattr(bpy.types, "SATH_PT_server") and hasattr(bpy.types, "SATH_MT_main") and _registered("commit")
    assert sorted(host.REG.records) == ["bim", "io", "review", "scada", "sim", "twin"]


def _pinned_cascade():
    """PINNED bog'liq modul kaskadda o'chmasligi kerak: soxta bog'liqlik (PINNED hozir bo'sh)."""
    from sath.core import host

    host.set_enabled("sim", True)
    assert host.is_enabled("sim")
    real = host.REG.dependents
    host.PINNED = frozenset({"x_pinned"})
    host.REG.dependents = lambda rid: ["x_pinned"] if rid == "sim" else []
    try:
        assert host.pinned_dependents("sim") == ["x_pinned"]
        assert host.set_enabled("sim", False) == [] and host.is_enabled("sim")
    finally:
        host.REG.dependents, host.PINNED = real, frozenset()


def _review_live():
    """Spec P3 mezoni: review jonli o'chadi va yonadi; yadro tegilmaydi."""
    from sath.core import host

    s = bpy.context.scene.ges
    assert host.is_enabled("review") and hasattr(bpy.types, "SATH_PT_review") and _registered("diff")
    s.diff_note = "v1: eski"
    assert host.set_enabled("review", False) == ["review"]
    assert not hasattr(bpy.types, "SATH_PT_review") and not _registered("diff") and not _registered("decide")
    assert s.diff_note == ""  # modul unregister: diff ranglari tiklandi, izoh tozalandi
    assert _registered("commit") and hasattr(bpy.types, "SATH_PT_model")
    assert host.set_enabled("review", True) == ["review"]
    assert hasattr(bpy.types, "SATH_PT_review") and bpy.ops.sath.clear_diff() == {"FINISHED"}


def _scada_off():
    from sath.core import host

    s = bpy.context.scene.ges
    s.monitor_on = True
    off = host.set_enabled("scada", False)
    assert off == ["twin", "scada"], off  # twin birga o'chadi
    assert not s.monitor_on and not hasattr(bpy.types, "SATH_PT_monitor") and not _registered("monitor_toggle")
    for mid in reversed(off):
        assert host.set_enabled(mid, True) == [mid]
    assert hasattr(bpy.types, "SATH_PT_monitor")


def _twin_cascade():
    """Bog'liqlik: sim o'chsa twin ham o'chadi; twin yoqilsa sim ham yonadi."""
    from sath.core import host

    assert host.is_enabled("twin") and hasattr(bpy.types, "SATH_PT_twin_sims")
    assert host.set_enabled("sim", False) == ["twin", "sim"]
    assert not hasattr(bpy.types, "SATH_PT_twin") and not _registered("sim_hammer")
    assert host.set_enabled("twin", True) == ["sim", "twin"]
    assert hasattr(bpy.types, "SATH_PT_sim") and hasattr(bpy.types, "SATH_PT_twin") and _registered("sim_hammer")


def _viewer_hides():
    """Spec P3 mezoni: viewer roli sim panelini va commit ni yashiradi; engineer (eski server — rol zaxirasi) ko'radi.
    IFC yuklaydi (Bonsai yangi sessiya) — run() da oxirgi."""
    from sath import ifc, props, session

    ifc.load(ROOT / "docs" / "samples" / "namuna_ges_v1.ifc")
    s = bpy.context.scene.ges
    session.set_session(object(), {"username": "test"})  # tarmoqsiz «kirgan» holat
    try:
        for role, perms_str, sees in (("viewer", "project.read scada.read", False), ("engineer", "", True)):
            props.fill(s.projects, [{"item_id": 9, "name": "P", "state": role, "perms": perms_str}])
            s.project_id, s.model_id = 9, 5
            assert bpy.types.SATH_PT_sim.poll(bpy.context) is sees, role
            assert bpy.types.SATH_PT_monitor.poll(bpy.context), role  # scada.read — hamma rolda
            assert bpy.ops.sath.commit.poll() is sees, role
            assert bpy.ops.sath.sim_hydro.poll() is sees, role
            assert bpy.ops.sath.safety_check.poll() is sees, role
            assert bpy.types.SATH_PT_twin_sims.poll(bpy.context) is sees, role
            for op in ("sim_hammer", "sim_governor", "sim_transformer", "sim_seismic"):
                assert getattr(bpy.ops.sath, op).poll() is sees, (role, op)
    finally:
        session.logout()
        s.project_id = s.model_id = 0
        s.projects.clear()


def _io_live():
    """P3 io moduli: Import paneli, File→Import va menyu bandlari hamda sath.assign_ifc (commit uchun) jonli
    o'chadi va yonadi."""
    from sath.core import host

    assert _registered("import_dxf") and hasattr(bpy.types, "SATH_PT_import") and _registered("assign_ifc")
    assert host.set_enabled("io", False) == ["io"]
    assert not _registered("import_dxf") and not _registered("import_mesh") and not hasattr(bpy.types, "SATH_PT_import")
    assert not _registered("assign_ifc")
    assert host.set_enabled("io", True) == ["io"] and _registered("import_mesh") and _registered("assign_ifc")


def _commit_without_bim():
    """bim o'chiq: commit dialogi yetim-o'chirish belgisini ko'rsatmaydi; execute sath.sync_ifc ni chaqirmaydi va
    belgi qo'yilgan bo'lsa bim ni yoqishni so'raydi (ro'yxatda yo'q operator chaqirilmaydi)."""
    from types import SimpleNamespace

    from sath import ifc, ops_server

    calls: list = []
    fake = SimpleNamespace(layout=_Layout(calls), unassigned_note="", orphan_note="1 yetim entity", purge_orphans=True,
                           assign_missing=False, msgs=[])  # fmt: skip
    ops_server.SATH_OT_commit.draw(fake, bpy.context)
    assert ("prop", "purge_orphans") not in calls and any("(BIM)" in t for k, t in calls if k == "label"), calls
    fake.report = lambda kind, msg: fake.msgs.append(msg)
    real = ifc.orphans
    ifc.orphans = lambda: ["#1"]
    try:
        assert ops_server.SATH_OT_commit.execute(fake, bpy.context) == {"CANCELLED"}
    finally:
        ifc.orphans = real
    assert fake.msgs == ["Yetim entitylarni o'chirish uchun «GES obyektlari (BIM)» modulini yoqing"], fake.msgs


def _commit_without_io():
    """Minor 5: io o'chiq + «IFC ga kirmagan mesh larni qo'shish» belgisi — commit CANCELLED, io ni yoqishni so'raydi;
    sath.assign_ifc (va uning argumenti unassigned()) chaqirilmaydi."""
    from types import SimpleNamespace

    from sath import ops_server
    from sath.core import host

    assert host.set_enabled("io", False) == ["io"]
    fake = SimpleNamespace(assign_missing=True, purge_orphans=False, msgs=[])
    fake.report = lambda kind, msg: fake.msgs.append(msg)
    asked: list = []
    real = ops_server.unassigned
    ops_server.unassigned = lambda context: asked.append(1) or ["X"]
    try:
        assert ops_server.SATH_OT_commit.execute(fake, bpy.context) == {"CANCELLED"}
    finally:
        ops_server.unassigned = real
        assert host.set_enabled("io", True) == ["io"]
    assert fake.msgs == ["IFC ga qo'shish uchun «Import» (io) moduli yoqilmagan"] and asked == [], fake.msgs


def _toggle_hook_error():
    """Minor 8: disable_blocker ilgagi yiqilsa — o'chirish to'silmaydi, lekin module_toggle ogohlantiradi."""
    from types import SimpleNamespace

    from sath.core import host

    mod = host.record("io").module
    mod.disable_blocker = lambda api: 1 / 0
    fake = SimpleNamespace(module_id="io", msgs=[])
    fake.report = lambda kind, msg: fake.msgs.append((next(iter(kind)), msg))
    try:
        assert host.SATH_OT_module_toggle.execute(fake, bpy.context) == {"FINISHED"}
    finally:
        del mod.disable_blocker
    assert not host.is_enabled("io")
    assert fake.msgs == [("WARNING", "io: o'chirish tekshiruvi xato berdi — baribir o'chirildi")], fake.msgs
    assert host.set_enabled("io", True) == ["io"]


def _restore_without_modules():
    """Minor 3: review/sim o'chiq — props.restore (open_version/pull_head) issue/CR/sim turi indekslarini qaytarganda
    ro'yxatda yo'q operatorlar chaqirilmaydi (avval har safar AttributeError traceback i chiqardi)."""
    from sath import props, session
    from sath.core import host

    s = bpy.context.scene.ges
    off = host.set_enabled("review", False) + host.set_enabled("sim", False)
    assert set(off) == {"review", "sim", "twin"}, off
    session.set_session(object(), {"username": "test"})
    row = [{"item_id": 1, "name": "a"}, {"item_id": 2, "name": "b"}]
    snap = {"issues": row, "issues_index": 1, "crs": row, "crs_index": 1, "sim_kinds": row, "sim_kind_index": 1}
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            props.restore(s, snap)
        for cb in (props._on_issue, props._on_cr, props._on_sim_kind):
            cb(s, bpy.context)  # himoya bo'lmasa — AttributeError (operator ro'yxatda yo'q)
    finally:
        session.logout()
        for coll in ("issues", "crs", "sim_kinds"):
            getattr(s, coll).clear()
        for mid in ("review", "sim", "twin"):
            host.set_enabled(mid, True)
    assert "Traceback" not in err.getvalue() and "AttributeError" not in err.getvalue(), err.getvalue()


def _scada_all_scenes():
    """Minor 9: scada o'chsa monitoring barcha sahnalarda to'xtaydi, holat qatori tozalanadi."""
    from sath.core import host

    extra = bpy.data.scenes.new("sath_test_ikkinchi")
    try:
        for sc in bpy.data.scenes:
            sc.ges.monitor_on, sc.ges.monitor_status = True, "5 sensor"
        off = host.set_enabled("scada", False)
        assert "scada" in off, off
        assert all(not sc.ges.monitor_on and sc.ges.monitor_status == "" for sc in bpy.data.scenes)
        for mid in reversed(off):
            host.set_enabled(mid, True)
    finally:
        bpy.data.scenes.remove(extra)


def _bim_enable_restores_kinds():
    """Important 2: IFC bim o'chiq paytda yuklansa (ifc.loaded obunasi yo'q) — bim yoqilganda bir martalik timer GES
    turlarini IFC psetlaridan tiklaydi. Fon rejimida timer ishlamaydi — callback qo'lda chaqiriladi."""
    from sath import ifc
    from sath.core import host

    def kinds():
        return sorted({o.ges.kind for o in bpy.data.objects if o.ges.kind})

    before = kinds()
    assert before, "namuna IFC da GES obyektlari bo'lishi kerak"
    off = host.set_enabled("bim", False)
    assert off and off[-1] == "bim", off
    ifc.load(ROOT / "docs" / "samples" / "namuna_ges_v1.ifc")  # bim o'chiq: yangi obyektlarda Object.ges ma'lumoti yo'q
    for mid in reversed(off):
        assert host.set_enabled(mid, True) == [mid]
    mod = host.record("bim").module
    assert bpy.app.timers.is_registered(mod.restore_after_enable)
    bpy.app.timers.unregister(mod.restore_after_enable)
    mod.restore_after_enable()
    assert kinds() == before, (before, kinds())
    assert bpy.context.scene.ges.status.startswith("BIM yoqildi — GES:"), bpy.context.scene.ges.status


def _bim_keeps_data():
    """Review Focus 5: bim o'chib-yonsa GES obyekt parametrlari saqlanadi; sim/twin birga o'chadi.
    IFC ga yozilmagan obyekt bo'lsa — o'chirish rad etiladi (modul yoqiq qoladi, sabab foydalanuvchiga)."""
    from sath import ges_objects
    from sath.core import host

    obj = ges_objects.add(bpy.context, "GES_Dam")  # P2 dagi imzo (sath_tests/objects.py dagidek)
    name = obj.name
    # rad etish: IFC ga yozilmagan o'zgarish — hech narsa o'chmaydi, Sozlamalardagi tugma sababni aytadi
    obj.ges.ifc_dirty = True
    why = "bim modulini o'chirib bo'lmaydi: 1 obyekt IFC ga yozilmagan — avval «IFC ga qo'llash»"
    assert host.disable_blocker("bim") == why, host.disable_blocker("bim")
    assert host.disable_blocker("sim") == ""  # sim/twin o'chishi bim ni tegmaydi
    assert host.set_enabled("bim", False) == []
    assert host.is_enabled("bim") and host.is_enabled("sim") and host.is_enabled("twin")
    assert hasattr(bpy.types.Object, "ges") and _registered("sync_ifc")
    assert bpy.ops.sath.module_toggle(module_id="bim") == {"CANCELLED"} and host.is_enabled("bim")
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not obj.ges.ifc_dirty  # «IFC ga qo'llash» — endi mumkin
    assert host.disable_blocker("bim") == ""
    off = host.set_enabled("bim", False)
    assert off[-1] == "bim" and {"sim", "twin"} <= set(off), off
    assert not hasattr(bpy.types.Object, "ges") and not hasattr(bpy.types, "SATH_PT_objects") and not _registered("add_object")
    assert not _registered("sync_ifc") and not _registered("build_demo_plant")
    _commit_without_bim()
    _commit_without_io()
    for mid in reversed(off):
        assert host.set_enabled(mid, True) == [mid]
    assert bpy.data.objects[name].ges.kind == "GES_Dam" and hasattr(bpy.types, "SATH_PT_objects")
    assert _registered("sync_ifc") and not bpy.app.timers.is_registered(ges_objects.flush_pending)


def run(ctx):
    _user_modules()
    _core_only()
    _pinned_cascade()
    _bundled_retry()
    _review_live()
    _scada_off()
    _twin_cascade()
    _io_live()
    _toggle_hook_error()
    _restore_without_modules()
    _scada_all_scenes()
    _bim_keeps_data()
    _viewer_hides()
    _bim_enable_restores_kinds()
