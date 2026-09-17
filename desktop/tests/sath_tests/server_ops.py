"""Operatorlar ro'yxatga olingan; login siz connect xatoni report qiladi (crash yo'q)."""

import bpy


def run(ctx):
    for op in (
        "connect", "logout", "refresh_projects", "refresh_models", "refresh_versions",
        "open_version", "commit", "submit", "open_web", "create_model", "notifications", "mark_read",
    ):  # fmt: skip
        assert hasattr(bpy.ops.sath, op), op
    from sath.prefs import prefs

    prefs().server = "http://127.0.0.1:9"  # yopiq port
    try:  # headless da report({'ERROR'}) RuntimeError bo'lib chiqadi (GUI da popup)
        bpy.ops.sath.connect()
        raise AssertionError("yopiq portga ulanish xato berishi kerak")
    except RuntimeError as e:
        assert "ulanib bo'lmadi" in str(e), e
    assert bpy.ops.sath.logout() == {"FINISHED"}
    assert bpy.ops.sath.open_version.poll() is False
