"""Real server: namuna GES → commit → hydro (quyi byef, generator/draft ranglari), gidrozarba (markerlar), regulyator
(rotor aylanishi), transformator (issiqlik rangi), zilzila (siljish) — timeline keyframelari."""

import os
import time

import bpy


def _fcurves(obj):
    from sath import sim_anim

    return sim_anim._fcurves(obj)


def _wait(poll, s, secs=90):
    for _ in range(int(secs / 0.5)):
        if poll() is None:
            break
        time.sleep(0.5)
    assert s.sim_status.startswith("Tayyor"), s.sim_status


def run(ctx):
    from sath import demo_plant, ges_objects, ops_sim, ops_twin, prefs, session, sim_anim

    url = os.environ.get("GES_TEST_SERVER", "http://127.0.0.1:8000")
    p = prefs.prefs()
    p.server, p.username = url, "admin"
    s = bpy.context.scene.ges
    s.password = "admin123"
    assert bpy.ops.sath.connect() == {"FINISHED"}
    c = session.client()
    proj = c._json("POST", "/api/projects", {"name": f"Twin {os.getpid()}"})
    m = c.create_model(proj["id"], "twin-model")
    s.project_id, s.model_id, s.model_name = proj["id"], m["id"], m["name"]
    out = demo_plant.build(bpy.context, head_m=45.0, units=2, unit_mw=25.0, zero_m=850.0)
    s = bpy.context.scene.ges
    s.commit_message = "v1: namuna GES"
    assert bpy.ops.sath.commit() == {"FINISHED"}, s.status
    assert s.version_id
    g = c.ges_params(s.version_id)
    assert len(g["units"]) == 2 and len(g["penstocks"]) == 2 and g["spillways"], {k: len(v) for k, v in g.items()}

    # 1) hydro — quyi byef Manning, generator/draft/transformator ranglari
    s.hydro_days, s.hydro_inflow, s.hydro_mode = 20, 150.0, "max_power"
    params = ops_sim.hydro_params(c, s.version_id, s)
    assert params["model_zero_elevation_m"] == 850.0, params["model_zero_elevation_m"]
    job = c.create_sim(s.model_id, "hydro", s.version_id, params, kind="hydro")
    _wait(ops_sim._poll_factory(ops_sim.HYDRO_META, job["id"], lambda r: sim_anim.animate_hydro(bpy.context, r, params, zero_m=850.0)), s)
    assert bpy.context.scene.frame_end == 20
    tw = bpy.data.objects["GES_QuyiByef"]
    fc = [f for f in _fcurves(tw) if f.data_path == "location"]
    assert fc and len(fc[0].keyframe_points) == 20, "quyi byef keyframelari yo'q"
    zs = [k.co[1] for k in fc[0].keyframe_points]
    assert all(z > -12.0 for z in zs) and max(zs) - (-12.0) < 11.0, zs[:3]  # kanal tagidan yuqori, devordan past
    for role in ("gen:1", "draft:1", "transformer:2"):
        o = ges_objects.by_role(role)
        cfc = [f for f in _fcurves(o) if f.data_path == "color"]
        assert cfc and len(cfc[0].keyframe_points) == 20, role
    gen_last = [f for f in _fcurves(ges_objects.by_role("gen:1")) if f.data_path == "color"][1].keyframe_points[-1].co[1]
    assert gen_last > 0.5, gen_last  # yashil komponent — yuklamada
    bpy.ops.sath.sim_clear_anim()

    # 2) gidrozarba — bosh quvur markerlari
    s.hammer_close_s = 4.0
    hp = ops_twin.hammer_params(s)
    assert hp["length_m"] > 30 and 20 < hp["head_m"] < 50 and hp["material"] == "steel", (hp["head_m"], hp["material"], hp["flow_m3s"])  # napor joriy suv tekisliklaridan
    job = c.create_sim(s.model_id, "hammer", s.version_id, hp, kind="water_hammer")
    _wait(ops_sim._poll_factory(ops_twin.HAMMER_META, job["id"], lambda r: sim_anim.animate_hammer(bpy.context, r, ges_objects.by_role("penstock:1"))), s)
    markers = [o for o in bpy.data.objects if o.name.startswith("GES_Bosim.")]
    assert len(markers) == 21, len(markers)
    assert bpy.context.scene.frame_end >= 30, bpy.context.scene.frame_end
    mk = markers[-1]
    assert [f for f in _fcurves(mk) if f.data_path == "scale"], "marker masshtab keyframelari yo'q"
    pen = ges_objects.by_role("penstock:1")
    first, last = markers[0].matrix_world.translation, markers[-1].matrix_world.translation
    assert (first - pen.matrix_world.translation).length < 1e-3 and last.z < first.z - 10, (tuple(first), tuple(last))
    assert [r.name for r in s.sim_results if r.name.startswith("Maks. bosim")], [r.name for r in s.sim_results]
    bpy.ops.sath.sim_clear_anim()
    assert not [o for o in bpy.data.objects if o.name.startswith("GES_Bosim.")]

    # 3) regulyator — rotor aylanishi
    s.gov_event, s.gov_step = "rejection", 0.8
    gp = ops_twin.governor_params(s)
    assert 0.5 <= gp["tw"] <= 4.0, gp
    job = c.create_sim(s.model_id, "gov", s.version_id, gp, kind="governor")
    _wait(ops_sim._poll_factory(ops_twin.GOV_META, job["id"], lambda r: sim_anim.animate_governor(bpy.context, r)), s)
    gen = ges_objects.by_role("gen:1")
    rfc = [f for f in _fcurves(gen) if f.data_path == "rotation_euler"]
    assert rfc and len(rfc[0].keyframe_points) == bpy.context.scene.frame_end, "aylanish keyframelari yo'q"
    ang = [k.co[1] for k in rfc[0].keyframe_points]
    assert ang[-1] > ang[0] + 50, (ang[0], ang[-1])  # 60 s da ≥ 8 aylanish
    assert rfc[0].keyframe_points[5].interpolation == "LINEAR"
    unit = ges_objects.by_role("unit:1")
    assert [f for f in _fcurves(unit) if f.data_path == "rotation_euler"]
    bpy.ops.sath.sim_clear_anim()

    # 4) transformator — issiqlik rangi
    s.tr_load, s.tr_days = 120.0, 2
    tp = ops_twin.transformer_params(s)
    assert abs(tp["rated_mva"] - 27.8) < 0.11 and tp["cooling"] == "ONAF", tp
    job = c.create_sim(s.model_id, "tr", s.version_id, tp, kind="transformer")
    _wait(ops_sim._poll_factory(ops_twin.TR_META, job["id"], lambda r: sim_anim.animate_transformer(bpy.context, r)), s)
    tf = ges_objects.by_role("transformer:1")
    cfc = [f for f in _fcurves(tf) if f.data_path == "color"]
    assert cfc and len(cfc[0].keyframe_points) == bpy.context.scene.frame_end >= 40
    reds = [k.co[1] for k in cfc[0].keyframe_points]
    assert max(reds) > 0.6, max(reds)  # 120 % yukda issiq nuqta > 110 °C → sariq-qizil (qizil komponent yuqori)
    assert [r for r in s.sim_results if r.name.startswith("Issiq nuqta")], [r.name for r in s.sim_results]
    bpy.ops.sath.sim_clear_anim()

    # 5) zilzila — siljish keyframelari va tozalashda joyiga qaytish
    s.seis_intensity, s.seis_ground, s.seis_scale = "9", "C", 20.0
    sp = ops_twin.seismic_params(s)
    assert sp["dam_height_m"] == 58.0 and sp["ph_height_m"] == 22.0, sp
    dam = ges_objects.by_role("dam")
    x0 = float(dam.location.x)
    job = c.create_sim(s.model_id, "seis", s.version_id, sp, kind="seismic")
    _wait(ops_sim._poll_factory(ops_twin.SEIS_META, job["id"], lambda r: sim_anim.animate_seismic(bpy.context, r, scale=20.0)), s)
    assert bpy.context.scene.frame_end == 16 * 24
    lfc = [f for f in _fcurves(dam) if f.data_path == "location"]
    assert lfc and len(lfc[0].keyframe_points) == 384
    xs = [k.co[1] for k in lfc[0].keyframe_points]
    assert max(abs(x - x0) for x in xs) > 0.05, max(abs(x - x0) for x in xs)  # ×20 da ≥ 5 sm
    assert dam.get("sath_base_loc") is not None
    assert [f for f in _fcurves(ges_objects.by_role("gen:2")) if f.data_path == "location"], "zal ichidagilar ham tebranadi"
    bpy.ops.sath.sim_clear_anim()
    assert abs(dam.location.x - x0) < 1e-9 and dam.get("sath_base_loc") is None
    print("TWIN:", len(out), "obyekt; 5 simulyatsiya animatsiyasi OK; natija:", [(r.name, r.col2) for r in s.sim_results][:3])
