"""Uchdan-uchiga: real server (GES_TEST_SERVER) — ulanish, loyiha/model, GES obyekt, commit, ochish, diff,
issue + ko'rinish, taqriz ro'yxati, sim katalogi, monitoring tick. Bonsai + FreeCAD kerak."""

import os

import bpy


def run(ctx):
    from sath import fc_engine, ges_objects, ifc, ops_monitor, prefs, session

    url = os.environ.get("GES_TEST_SERVER", "http://127.0.0.1:8765")
    p = prefs.prefs()
    p.server, p.username = url, "admin"
    s = bpy.context.scene.ges
    s.password = "admin123"
    assert bpy.ops.sath.connect() == {"FINISHED"}, s.status
    assert session.is_logged_in() and s.password == ""
    c = session.client()
    proj = c._json("POST", "/api/projects", {"name": f"E2E Blender {os.getpid()}"})
    assert bpy.ops.sath.refresh_projects() == {"FINISHED"}
    s.projects_index = next(i for i, x in enumerate(s.projects) if x.item_id == proj["id"])
    s.new_model_name = "e2e-model"
    assert bpy.ops.sath.create_model() == {"FINISHED"}
    assert [m.name for m in s.models] == ["e2e-model"], [m.name for m in s.models]
    s.models_index = 0
    s.model_id, s.model_name, s.project_id = s.models[0].item_id, "e2e-model", proj["id"]

    # GES obyekt → yangi Bonsai loyihasi → commit v1
    dam = ges_objects.add(bpy.context, "GES_Dam")
    assert ifc.entity(dam).is_a("IfcWall")
    s.commit_message = "v1: to'g'on"
    assert bpy.ops.sath.commit() == {"FINISHED"}, s.status
    assert s.version_number == 1 and len(s.versions) == 1
    # v2: parametr o'zgaradi → diff
    next(x for x in dam.ges.params if x.name == "Height").value_float = 25.0
    s.commit_message = "v2: balandlik 25"
    s.submit_after_commit = True
    assert bpy.ops.sath.commit() == {"FINISHED"}, s.status
    assert s.version_number == 2 and "tasdiqqa" in s.status
    s.versions_index = 0
    assert bpy.ops.sath.diff() == {"FINISHED"}
    assert "v2" in s.diff_note, s.diff_note
    assert bpy.ops.sath.clear_diff() == {"FINISHED"}

    # ochish (v1 ni qayta yuklash)
    s.versions_index = len(s.versions) - 1
    assert bpy.ops.sath.open_version() == {"FINISHED"}
    s = bpy.context.scene.ges  # Bonsai fresh session: yangi sahna, holat snapshot dan qaytarilgan
    assert s.version_number == 1 and ifc.file() is not None, s.status
    print("DBG", s.projects_index, len(s.projects), s.models_index, len(s.models), s.versions_index, len(s.versions), s.status)
    assert s.model_id and len(s.versions) == 2 and len(s.projects) >= 1, (s.model_id, len(s.versions))
    assert any(ifc.entity(o) is not None and ifc.entity(o).is_a("IfcWall") for o in bpy.data.objects)

    # issue + ko'rinish, taqriz, bildirishnoma, sim, monitoring
    assert bpy.ops.sath.new_issue(title="Yoriq") == {"FINISHED"}
    assert len(s.issues) == 1 and s.issue_detail.startswith("#")
    s.comment_text = "izoh"
    assert bpy.ops.sath.comment_issue() == {"FINISHED"} and "izoh" in s.issue_detail
    assert bpy.ops.sath.goto_view() == {"FINISHED"}
    assert bpy.ops.sath.refresh_crs() == {"FINISHED"} and len(s.crs) == 1 and s.my_role
    assert bpy.ops.sath.notifications() == {"FINISHED"}
    assert bpy.ops.sath.sim_catalog() == {"FINISHED"} and len(s.sim_kinds) > 0 and len(s.sim_fields) > 0
    assert bpy.ops.sath.monitor_toggle() == {"FINISHED"} and s.monitor_on
    assert ops_monitor._tick() == ops_monitor.INTERVAL, s.monitor_status
    assert "sensor" in s.monitor_status
    assert bpy.ops.sath.monitor_toggle() == {"FINISHED"} and not s.monitor_on
    assert fc_engine.doc() is not None
    print("E2E:", s.status, "|", s.diff_note, "|", s.monitor_status)
