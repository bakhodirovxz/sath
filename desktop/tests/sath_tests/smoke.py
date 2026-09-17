"""Addon ro'yxatga olinadi, prefs/scene props bor, panel mavjud."""

import bpy


def run(ctx):
    from sath import prefs, session

    assert prefs.prefs().server.startswith("http")
    s = bpy.context.scene.ges
    assert s.model_id == 0 and s.status == ""
    assert not session.is_logged_in()
    assert hasattr(bpy.types, "SATH_PT_server") and hasattr(bpy.types, "SATH_MT_main")
    try:
        session.client()
        raise AssertionError("client() login siz RuntimeError berishi kerak")
    except RuntimeError:
        pass
