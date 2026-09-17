"""Real server: to'g'on + turbina + suv tashlagich → commit → hydro simulyatsiya → Blender timeline animatsiyasi."""

import os
import time

import bpy


def run(ctx):
    from sath import ges_objects, ops_sim, prefs, session, sim_anim

    url = os.environ.get("GES_TEST_SERVER", "http://127.0.0.1:8000")
    p = prefs.prefs()
    p.server, p.username = url, "admin"
    s = bpy.context.scene.ges
    s.password = "admin123"
    assert bpy.ops.sath.connect() == {"FINISHED"}
    c = session.client()
    proj = c._json("POST", "/api/projects", {"name": f"Hydro anim {os.getpid()}"})
    m = c.create_model(proj["id"], "hydro-model")
    s.project_id, s.model_id, s.model_name = proj["id"], m["id"], m["name"]
    ges_objects.add(bpy.context, "GES_Dam")
    ges_objects.add(bpy.context, "GES_Turbine", "Agregat 1")
    ges_objects.add(bpy.context, "GES_Turbine", "Agregat 2")
    ges_objects.add(bpy.context, "GES_Spillway")
    s.commit_message = "v1: GES obyektlari"
    assert bpy.ops.sath.commit() == {"FINISHED"}, s.status
    assert s.version_id
    s.hydro_days, s.hydro_inflow, s.hydro_mode = 30, 150.0, "target_level"
    params = ops_sim.hydro_params(c, s.version_id, s)
    assert len(params["units"]) == 2 and all(u.get("guid") for u in params["units"]), params["units"]
    assert params["reservoir"].get("spillway") and params.get("spillway_guid"), params["reservoir"]
    assert params["inflow_m3s"] == {"constant": 150.0, "steps": 30}
    job = c.create_sim(s.model_id, "hydro test", s.version_id, params, kind="hydro")
    poll = ops_sim._poll_factory(ops_sim.HYDRO_META, job["id"], lambda r: sim_anim.animate_hydro(bpy.context, r, params))
    for _ in range(60):
        if poll() is None:
            break
        time.sleep(0.5)
    assert s.sim_status.startswith("Tayyor"), s.sim_status
    assert bpy.context.scene.frame_end == 30
    plane = bpy.data.objects["GES_SuvSathi"]
    assert plane.animation_data and plane.animation_data.action, "suv sathi keyframelari yo'q"
    fc = [f for f in sim_anim_fcurves(plane) if f.data_path == "location"]
    assert fc and len(fc[0].keyframe_points) == 30
    unit = bpy.data.objects["IfcFlowMovingDevice/Agregat 1"] if "IfcFlowMovingDevice/Agregat 1" in bpy.data.objects else next(o for o in bpy.data.objects if "Agregat 1" in o.name)
    cfc = [f for f in sim_anim_fcurves(unit) if f.data_path == "color"]
    assert cfc and len(cfc[0].keyframe_points) == 30, "agregat rang keyframelari yo'q"
    assert [r.name for r in s.sim_results][0] == "Xulosa"
    print("HYDRO:", s.sim_status, "| kadrlar:", bpy.context.scene.frame_end, "| natija:", [(r.name, r.col2) for r in s.sim_results][:3])
    bpy.ops.sath.sim_clear_anim()
    assert not plane.animation_data or not plane.animation_data.action


def sim_anim_fcurves(obj):
    act = obj.animation_data.action if obj.animation_data else None
    if act is None:
        return []
    if hasattr(act, "fcurves") and len(act.fcurves):
        return list(act.fcurves)
    out = []  # Blender 4.4+/5.x: slots → layers → strips → channelbag
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for slot in act.slots:
                cb = strip.channelbag(slot) if hasattr(strip, "channelbag") else None
                if cb is not None:
                    out.extend(cb.fcurves)
    return out
