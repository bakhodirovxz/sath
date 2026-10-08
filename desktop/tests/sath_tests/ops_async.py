"""K3: server operatorlari asinxron — sekin serverda operator darhol qaytadi, natija pompadan keyin sahnada."""

import time
from pathlib import Path

import bpy
from fake_server import js, serve

SLOW = 0.6


def slow(obj):
    def f():
        time.sleep(SLOW)
        return js(obj)()

    return f


def run(ctx):
    from sath import props
    from sath.core.tasks import TASKS
    from sath.prefs import prefs

    sample = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"
    ifc_bytes = sample.read_bytes()
    url, stop = serve({
        ("POST", "/api/auth/login"): slow({"access_token": "t", "refresh_token": "r"}),
        ("GET", "/api/auth/me"): js({"id": 1, "username": "admin"}),
        ("GET", "/api/desktop/latest"): js({"detail": "yo'q"}, 404),
        ("GET", "/api/notifications"): js([]),
        ("GET", "/api/projects"): js([{"id": 7, "name": "P", "my_role": "engineer"}]),
        ("GET", "/api/projects/7/models"): js([{"id": 3, "name": "M"}]),
        ("GET", "/api/models/3/versions"): js([{"id": 11, "number": 1, "state": "wip", "message": "", "author_username": "a"}]),
        ("GET", "/api/versions/11/file"): lambda: (time.sleep(SLOW), (200, ifc_bytes))[1],
        ("GET", "/api/versions/11/diff"): slow({"added": [], "changed": [], "deleted": [], "summary": {"added": 0, "changed": 0, "deleted": 0}}),
        ("POST", "/api/models/3/sim/safety-check"): slow({"score": 100, "verdict": "yaxshi", "counts": {"ok": 0, "warn": 0, "fail": 0, "skip": 0}, "rows": []}),
    })  # fmt: skip
    TASKS.inline = False
    try:
        s = bpy.context.scene.ges
        prefs().server, prefs().username = url, "admin"
        bpy.context.window_manager.sath_secret.password = "x"

        t0 = time.perf_counter()
        assert bpy.ops.sath.connect() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "connect bloklayapti"
        assert bpy.context.window_manager.sath_secret.password == ""  # parol darhol tozalanadi
        TASKS.drain(10)
        assert "admin sifatida kirildi" in s.status, s.status
        assert len(s.projects) == 1

        props.fill(s.models, [{"item_id": 3, "name": "M"}])
        s.models_index = 0
        props.fill(s.versions, [{"item_id": 11, "number": 1, "name": "v1"}])
        s.versions_index = 0
        t0 = time.perf_counter()
        assert bpy.ops.sath.open_version() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "open_version bloklayapti"
        TASKS.drain(20)
        s = bpy.context.scene.ges
        assert s.version_id == 11 and "v1 ochildi" in s.status, s.status

        s = bpy.context.scene.ges
        t0 = time.perf_counter()
        assert bpy.ops.sath.diff() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "diff bloklayapti"
        try:  # Review Focus 1: takror bosish rad etiladi
            bpy.ops.sath.diff()
        except RuntimeError:
            pass  # -b da WARNING report RuntimeError emas; CANCELLED qaytishi kifoya
        assert sum(1 for t in TASKS.active() if t.key == "review.diff") == 1
        TASKS.drain(10)
        assert "v1:" in bpy.context.scene.ges.diff_note, bpy.context.scene.ges.diff_note

        s = bpy.context.scene.ges
        s.model_id = 3
        t0 = time.perf_counter()
        assert bpy.ops.sath.safety_check() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "safety_check bloklayapti"
        TASKS.drain(10)
        assert bpy.context.scene.ges.safety_head.startswith("100"), bpy.context.scene.ges.safety_head

        # monitoring: noto'g'ri shakldagi egizak javobi monitoringni to'xtatmaydi
        from sath import ops_monitor

        s = bpy.context.scene.ges
        s.monitor_on = True
        ops_monitor._apply({"project_id": 7, "sensors": [], "twin": {}, "health": {"assets": []}, "twin_err": None,
                            "level_sensor": None, "level_pts": None, "level_err": None}, 0.0)  # fmt: skip
        assert s.twin_head.startswith("Egizak:"), s.twin_head
        assert s.monitor_status, "monitoring davom etishi kerak"
        s.monitor_on = False
    finally:
        TASKS.inline = True
        stop()
