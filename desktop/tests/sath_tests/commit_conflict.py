"""VCS-01: commit 409 dan keyin «Eng oxirgi versiyani yuklab olish» — lokal IFC zaxiraga, head ochiladi (server kerak)."""

import os

import bpy
from creds import admin_password


def run(ctx):
    from sath import flows, ges_objects, ifc, prefs, session

    url = os.environ.get("GES_TEST_SERVER", "http://127.0.0.1:8765")
    p = prefs.prefs()
    p.server, p.username = url, "admin"
    s = bpy.context.scene.ges
    bpy.context.window_manager.sath_secret.password = admin_password()
    assert bpy.ops.sath.connect() == {"FINISHED"}, s.status
    c = session.client()
    proj = c._json("POST", "/api/projects", {"name": f"Conflict {os.getpid()}"})
    m = c.create_model(proj["id"], "conflict-model")
    s.project_id, s.model_id, s.model_name = proj["id"], m["id"], m["name"]
    ges_objects.add(bpy.context, "GES_Dam")
    s.commit_message = "v1"
    assert bpy.ops.sath.commit() == {"FINISHED"}, s.status
    v1_path = flows.cache_dir() / f"commit_m{m['id']}.ifc"
    v2 = c.upload_version(m["id"], v1_path, "boshqa foydalanuvchi", s.version_id)  # server head endi v2
    s.head_conflict_id = v2["id"]  # commit 409 dan keyingi holat (VCS-01)
    assert bpy.ops.sath.pull_head.poll()
    assert bpy.ops.sath.pull_head() == {"FINISHED"}, s.status
    s = bpy.context.scene.ges
    assert s.version_id == v2["id"] and s.version_number == 2 and s.head_conflict_id == -1, s.status
    assert "lokal nusxa" in s.status and ifc.file() is not None
    assert list(flows.cache_dir().glob(f"lokal_m{m['id']}_*.ifc"))
