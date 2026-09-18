"""Simulyatsiya natijasini Blender timeline animatsiyasi qilish (egizak ustida, `obj.ges.role` orqali):

hydro       — suv sathi (yuqori byef) keyframe; agregat/generator/transformator rangi yuklama bo'yicha (o'chiq kulrang →
              yashil, Francis qo'pol zona sariq); quyi byef tekisligi Manning normal chuqurligidan (Q_turbina + tashlama);
              chiqarish quvuri Thoma σ < σ_c bo'lsa qizil (kavitatsiya); suv tashlagich rangi tashlama.
water_hammer — bosh quvur bo'ylab bosim markerlari (GES_Bosim.NN): h − h0 nisbiy → ko'k (past) / oq / qizil (yuqori),
              masshtab pulsatsiya; quvur rangi zadvijka oldidagi napor.
governor    — generator/turbina aylanishi (n = n_sinx · f/f_nom, burchak yig'iladi), generator rangi |Δf|, bosh quvur
              rangi sarf p.u., suv qabul qilgich rangi gate.
transformer — issiq nuqta harorati → rang (40 ko'k → 80 yashil → 110 sariq → 140 qizil).
seismic     — psevdo-spektral siljish u(t) = S_d·env(t)·sin(2πt/T) inshoot davri bilan (to'g'on / zal / quvur), vizual
              ko'paytirgich; rang S_a bo'yicha (< 0.2 g yashil, < 0.4 sariq, ≥ qizil).
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector

from . import ges_objects, ifc, physics, water

OFF = (0.42, 0.43, 0.46, 1.0)
ON = (0.23, 0.66, 0.39, 1.0)
WARN = (0.88, 0.66, 0.23, 1.0)
BAD = (0.85, 0.20, 0.15, 1.0)
SPILL = (0.3, 0.6, 0.95, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
LOW = (0.2, 0.45, 0.9, 1.0)
SIM_COLL = "GES_Sim"
BASE_LOC = "sath_base_loc"


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def _key_color(obj, rgba, frame: int) -> None:
    obj.color = rgba
    obj.keyframe_insert(data_path="color", frame=frame)


def _frames(context, n: int, fps: int) -> None:
    sc = context.scene
    sc.frame_start, sc.frame_end = 1, max(n, 2)
    sc.render.fps = fps


def _finish(context) -> None:
    context.scene.frame_set(1)
    for area in getattr(context.screen, "areas", []) if context.screen else []:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.color_type = "OBJECT"


def _fcurves(obj):
    act = obj.animation_data.action if obj.animation_data else None
    if act is None:
        return []
    if hasattr(act, "fcurves") and len(act.fcurves):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):  # Blender 5.x slotted actions
        for strip in layer.strips:
            for slot in act.slots:
                bag = strip.channelbag(slot)
                if bag is not None:
                    out.extend(bag.fcurves)
    return out


def _linear(obj) -> None:
    for fc in _fcurves(obj):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def _role_index(obj) -> int | None:
    r = getattr(obj, "ges", None) and obj.ges.role
    if r and ":" in r:
        try:
            return int(r.split(":", 1)[1])
        except ValueError:
            return None
    return None


def _remember(obj) -> None:
    if obj.get(BASE_LOC) is None:
        obj[BASE_LOC] = list(obj.location)


def _sim_collection(context):
    coll = bpy.data.collections.get(SIM_COLL)
    if coll is None:
        coll = bpy.data.collections.new(SIM_COLL)
        context.scene.collection.children.link(coll)
    return coll


def _sphere(context, name: str, radius: float):
    ob = bpy.data.objects.get(name)
    if ob is None:
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=radius)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        _sim_collection(context).objects.link(ob)
    return ob


# --- hydro ---------------------------------------------------------------------------------------------------------


def _tailwater_series(result: dict, tailrace, zero_m: float) -> list[float] | None:
    """Har qadam quyi byef z (model koordinatasi): reyting egri chizig'i TW(Q) = TW_hisobiy + [y_n(Q) − y_n(Q_hisobiy)],
    y_n — Manning normal chuqurlik (kanal kengligi, nishabi, n). Hisobiy sath berilmagan bo'lsa — tag + y_n(Q)."""
    if tailrace is None:
        return None
    p = ges_objects.params_dict(tailrace)
    s = result["series"]
    b, sl, n = p.get("Width", 20.0), p.get("BedSlope", 0.001), p.get("Manning", 0.03)
    tw0, q0 = float(p.get("DesignTailwater", 0.0)), float(p.get("DesignFlow", 0.0))
    if tw0:
        base, y0 = tw0 - zero_m, physics.manning_depth(q0, b, sl, n)
    else:
        base, y0 = float(tailrace.location.z), 0.0
    out = []
    for q_t, q_s in zip(s["turbine_flow"], s.get("spill", [0.0] * len(s["turbine_flow"])), strict=True):
        out.append(base + physics.manning_depth(float(q_t) + float(q_s), b, sl, n) - y0)
    return out


def animate_hydro(context, result: dict, params: dict, zero_m: float = 0.0, fps: int = 12) -> int:
    """Natija seriyalari → keyframelar. Qaytaradi: kadrlar soni. Sahna kadr diapazoni o'rnatiladi."""
    s = result["series"]
    n = len(s["level"])
    _frames(context, n, fps)
    plane = water.place_water_plane(context, float(s["level"][0]) - zero_m)
    if plane is not None:
        plane.animation_data_clear()
        for i in range(n):
            plane.location.z = float(s["level"][i]) - zero_m
            plane.keyframe_insert(data_path="location", index=2, frame=i + 1)
    tailrace = ges_objects.by_role("tailrace")
    tw = _tailwater_series(result, tailrace, zero_m)
    if tw is not None:
        tp = water.place_tailwater_plane(context, tw[0])
        if tp is not None:
            tp.animation_data_clear()
            for i, z in enumerate(tw):
                tp.location.z = z
                tp.keyframe_insert(data_path="location", index=2, frame=i + 1)
    units = params.get("units") or []
    unit_series = result.get("units") or []
    for k, u in enumerate(units):
        obj = ifc.object_for_guid(u.get("guid", "")) if u.get("guid") else None
        if obj is None or k >= len(unit_series):
            continue
        obj.animation_data_clear()
        rated = float(u.get("rated_power_mw") or 0) or 1.0
        idx = _role_index(obj)
        gen = ges_objects.by_role(f"gen:{idx}") if idx else None
        tf = ges_objects.by_role(f"transformer:{idx}") if idx else None
        draft = ges_objects.by_role(f"draft:{idx}") if idx else None
        for o in (gen, tf, draft):
            if o is not None:
                o.animation_data_clear()
        gp = ges_objects.params_dict(gen) if gen is not None else {}
        rpm = physics.synchronous_rpm(gp.get("Frequency", 50.0), int(gp.get("Poles", 24)))
        mva = float(gp.get("RatedPower", rated / 0.9)) or 1.0
        dp = ges_objects.params_dict(draft) if draft is not None else {}
        for i, mw in enumerate(unit_series[k]["power_mw"]):
            load = mw / rated
            if mw <= 0:
                c = OFF
            elif u.get("type") == "Francis" and 0.4 <= load < 0.6:
                c = WARN
            else:
                c = _mix(OFF, ON, min(1.0, load))
            _key_color(obj, c, i + 1)
            if gen is not None:
                eta_g = physics.generator_efficiency(mw, mva, gp.get("EfficiencyMax", 0.985), gp.get("IronLossFrac", 0.4))
                _key_color(gen, _mix(OFF, ON, min(1.0, load * eta_g)) if mw > 0 else OFF, i + 1)
            if tf is not None:
                _key_color(tf, _mix(OFF, ON, min(1.0, mw / 0.9 / mva)) if mw > 0 else OFF, i + 1)
            if draft is not None:
                if mw <= 0:
                    _key_color(draft, OFF, i + 1)
                else:
                    h_net = float(s["head_net"][i]) if i < len(s.get("head_net", [])) else float(u.get("rated_head_m") or 1.0)
                    hs = float(dp.get("SuctionHead", 0.0))
                    if tw is not None:
                        hs = float(obj.location.z) - tw[i]  # ish g'ildiragi o'qi − joriy quyi byef
                    _, _, cav = physics.cavitation(str(u.get("type") or "Francis"), hs, h_net, rpm, mw * 1000.0)
                    _key_color(draft, BAD if cav else LOW, i + 1)
    spill_guid = (params.get("spillway_guid") or "") if isinstance(params.get("spillway_guid"), str) else ""
    sp = ifc.object_for_guid(spill_guid) if spill_guid else None
    if sp is not None:
        sp.animation_data_clear()
        mx = max(1e-6, max(s["spill"]))
        for i, q in enumerate(s["spill"]):
            _key_color(sp, _mix(OFF, SPILL, min(1.0, q / mx)) if q > 0 else WHITE, i + 1)
    _finish(context)
    return n


# --- water hammer -----------------------------------------------------------------------------------------------------


def animate_hammer(context, result: dict, pen, fps: int = 12) -> int:
    frames = result.get("profile", {}).get("frames") or []
    if not frames or pen is None:
        return 0
    m = len(frames[0]["h"])
    p = ges_objects.params_dict(pen)
    pts = physics.penstock_samples(p.get("Length", 20.0), p.get("Inclination", 0.0), p.get("BendRadius", 8.0), p.get("OutletLength", 6.0), m)
    r = max(0.4, p.get("Diameter", 2.0) * 0.7)
    h0 = [float(v) for v in frames[0]["h"]]
    amp = max(1e-6, max(abs(float(h) - h0[j]) for f in frames for j, h in enumerate(f["h"])))
    _frames(context, len(frames), fps)
    markers = []
    for j, pt in enumerate(pts):
        ob = _sphere(context, f"GES_Bosim.{j:02d}", r)
        ob.location = pen.matrix_world @ Vector(pt)
        ob.scale = (1.0, 1.0, 1.0)
        ob.animation_data_clear()
        markers.append(ob)
    pen.animation_data_clear()
    for i, f in enumerate(frames):
        for j, h in enumerate(f["h"]):
            t = (float(h) - h0[j]) / amp  # −1..1
            c = _mix(WHITE, BAD, t) if t >= 0 else _mix(WHITE, LOW, -t)
            _key_color(markers[j], c, i + 1)
            sc = 1.0 + 0.6 * max(0.0, t)
            markers[j].scale = (sc, sc, sc)
            markers[j].keyframe_insert(data_path="scale", frame=i + 1)
        tv = (float(f["h"][-1]) - h0[-1]) / amp
        _key_color(pen, _mix(WHITE, BAD, tv) if tv >= 0 else _mix(WHITE, LOW, -tv), i + 1)
    _finish(context)
    return len(frames)


# --- governor -------------------------------------------------------------------------------------------------------


def _subsample(n: int, limit: int) -> list[int]:
    step = max(1, math.ceil(n / limit))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def animate_governor(context, result: dict, fps: int = 24, limit: int = 600) -> int:
    s = result["series"]
    t, f_hz = s["t"], s["frequency_hz"]
    idx = _subsample(len(t), limit)
    _frames(context, len(idx), fps)
    f_nom = 50.0
    gens = ges_objects.by_kind("GES_Generator")
    units = ges_objects.by_kind("GES_Turbine")
    pens = ges_objects.by_kind("GES_Penstock")
    intakes = ges_objects.by_kind("GES_Intake")
    for o in gens + units + pens + intakes:
        o.animation_data_clear()
    rpm = {o.name: physics.synchronous_rpm(ges_objects.params_dict(o).get("Frequency", 50.0), int(ges_objects.params_dict(o).get("Poles", 24))) for o in gens}
    theta: dict[str, float] = {o.name: 0.0 for o in gens + units}
    for fr, i in enumerate(idx, start=1):
        dt = (float(t[i]) - float(t[idx[fr - 2]])) if fr > 1 else 0.0
        ratio = float(f_hz[i]) / f_nom
        dev = abs(float(f_hz[i]) - f_nom)
        c = ON if dev <= 0.2 else WARN if dev <= 1.0 else BAD
        for g in gens:
            omega = 2 * math.pi * rpm[g.name] / 60.0 * ratio
            theta[g.name] += omega * dt
            g.rotation_euler.z = theta[g.name]
            g.keyframe_insert(data_path="rotation_euler", index=2, frame=fr)
            _key_color(g, c, fr)
            k = _role_index(g)
            u = ges_objects.by_role(f"unit:{k}") if k else None
            if u is not None:
                u.rotation_euler.z = theta[g.name]
                u.keyframe_insert(data_path="rotation_euler", index=2, frame=fr)
        if not gens:
            for u in units:
                theta[u.name] += 2 * math.pi * 250.0 / 60.0 * ratio * dt
                u.rotation_euler.z = theta[u.name]
                u.keyframe_insert(data_path="rotation_euler", index=2, frame=fr)
                _key_color(u, c, fr)
        q = float(s["flow_pu"][i]) if s.get("flow_pu") else 1.0
        for pnk in pens:
            _key_color(pnk, _mix(OFF, SPILL, max(0.0, min(1.0, q))), fr)
        gate = float(s["gate"][i]) if s.get("gate") else 1.0
        for it in intakes:
            _key_color(it, _mix(OFF, ON, max(0.0, min(1.0, gate))), fr)
    for o in gens + units:
        _linear(o)
    _finish(context)
    return len(idx)


# --- transformer -----------------------------------------------------------------------------------------------------


def animate_transformer(context, result: dict, fps: int = 24, limit: int = 720) -> int:
    s = result["series"]
    th = s["hot_spot_c"]
    idx = _subsample(len(th), limit)
    _frames(context, len(idx), fps)
    tfs = ges_objects.by_kind("GES_Transformer")
    for o in tfs:
        o.animation_data_clear()
    for fr, i in enumerate(idx, start=1):
        c = physics.heat_color(float(th[i]))
        for o in tfs:
            _key_color(o, c, fr)
    _finish(context)
    return len(idx)


# --- seismic --------------------------------------------------------------------------------------------------------


_STRUCT_ROLES = {
    "To'g'on": ("dam", "intake", "spillway"),
    "Mashina zali": ("powerhouse", "controlroom", "unit:", "gen:", "draft:", "transformer:", "tailrace"),
    "Bosh quvur (tayanch)": ("penstock:",),
}


def _objects_for(prefixes) -> list:
    out = []
    for o in bpy.data.objects:
        r = getattr(o, "ges", None) and o.ges.role
        if r and any(r == p or (p.endswith(":") and r.startswith(p)) for p in prefixes):
            out.append(o)
    return out


def animate_seismic(context, result: dict, scale: float = 20.0, fps: int = 24, duration_s: float = 16.0) -> int:
    n = int(duration_s * fps)
    _frames(context, n, fps)
    for st in result.get("structures", []):
        roles = _STRUCT_ROLES.get(st["name"])
        if not roles:
            continue
        sa, T = float(st.get("sa_g", 0.0)), float(st.get("period_s", 0.3))
        c = ON if sa < 0.2 else WARN if sa < 0.4 else BAD
        for o in _objects_for(roles):
            _remember(o)
            o.animation_data_clear()
            bx, by, bz = o[BASE_LOC]
            for fr in range(1, n + 1):
                tt = (fr - 1) / fps
                o.location.x = bx + physics.ground_motion(sa, T, tt, scale)
                o.keyframe_insert(data_path="location", index=0, frame=fr)
            _key_color(o, c, 1)
            _linear(o)
    _finish(context)
    return n


def clear_animation(context) -> None:
    for o in list(context.scene.objects):
        if o.animation_data:
            o.animation_data_clear()
        base = o.get(BASE_LOC)
        if base is not None:
            o.location = base
            del o[BASE_LOC]
        if o.name.startswith("GES_Bosim."):
            bpy.data.objects.remove(o, do_unlink=True)
