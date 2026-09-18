"""GUI ko'rinish: namuna GES + gidrozarba markerlari (server bor bo'lsa) — skrinshot uchun; animatsiya tozalanmaydi."""

import os
import time

import bpy


def run(ctx):
    from sath import demo_plant, ges_objects, ops_sim, ops_twin, prefs, session, sim_anim

    out = demo_plant.build(bpy.context, head_m=45.0, units=2, unit_mw=25.0, zero_m=850.0)
    assert len(out) == 16
    url = os.environ.get("GES_TEST_SERVER")
    if not url:
        return
    p = prefs.prefs()
    p.server, p.username = url, "admin"
    s = bpy.context.scene.ges
    s.password = "admin123"
    assert bpy.ops.sath.connect() == {"FINISHED"}
    c = session.client()
    proj = c._json("POST", "/api/projects", {"name": f"GUI twin {os.getpid()}"})
    m = c.create_model(proj["id"], "gui-twin")
    s.project_id, s.model_id, s.model_name = proj["id"], m["id"], m["name"]
    s.hammer_close_s = 3.0
    job = c.create_sim(s.model_id, "hammer", None, ops_twin.hammer_params(s), kind="water_hammer")
    poll = ops_sim._poll_factory(ops_twin.HAMMER_META, job["id"], lambda r: sim_anim.animate_hammer(bpy.context, r, ges_objects.by_role("penstock:1")))
    for _ in range(120):
        if poll() is None:
            break
        time.sleep(0.5)
    assert s.sim_status.startswith("Tayyor"), s.sim_status
    bpy.context.scene.frame_set(max(2, bpy.context.scene.frame_end // 3))


def after_ui(context):
    from sath import demo_plant

    demo_plant.frame_view(context)
    print("GUI-TWIN: ko'rinish", [(a.spaces.active.shading.type, a.spaces.active.shading.color_type) for a in context.screen.areas if a.type == "VIEW_3D"])
    print("GUI-TWIN: kadr", bpy.context.scene.frame_current, "/", bpy.context.scene.frame_end)
