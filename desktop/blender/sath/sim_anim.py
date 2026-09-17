"""Simulyatsiya natijasini Blender timeline animatsiyasi qilish: suv sathi tekisligi (keyframe), agregatlar rangi
(quvvat bo'yicha: o'chiq kulrang → to'liq yuklama yashil, Francis qo'pol zona sariq), suv tashlagich rangi (tashlama)."""

from __future__ import annotations

from . import ifc, water

OFF = (0.42, 0.43, 0.46, 1.0)
ON = (0.23, 0.66, 0.39, 1.0)
WARN = (0.88, 0.66, 0.23, 1.0)
SPILL = (0.3, 0.6, 0.95, 1.0)


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def _key_color(obj, rgba, frame: int) -> None:
    obj.color = rgba
    obj.keyframe_insert(data_path="color", frame=frame)


def animate_hydro(context, result: dict, params: dict, zero_m: float = 0.0, fps: int = 12) -> int:
    """Natija seriyalari → keyframelar. Qaytaradi: kadrlar soni. Sahna kadr diapazoni o'rnatiladi."""
    s = result["series"]
    n = len(s["level"])
    sc = context.scene
    sc.frame_start, sc.frame_end = 1, max(n, 2)
    sc.render.fps = fps
    plane = water.place_water_plane(context, float(s["level"][0]) - zero_m)
    if plane is not None:
        plane.animation_data_clear()
        for i in range(n):
            plane.location.z = float(s["level"][i]) - zero_m
            plane.keyframe_insert(data_path="location", index=2, frame=i + 1)
    units = params.get("units") or []
    unit_series = result.get("units") or []
    for k, u in enumerate(units):
        obj = ifc.object_for_guid(u.get("guid", "")) if u.get("guid") else None
        if obj is None or k >= len(unit_series):
            continue
        obj.animation_data_clear()
        rated = float(u.get("rated_power_mw") or 0) or 1.0
        for i, mw in enumerate(unit_series[k]["power_mw"]):
            load = mw / rated
            if mw <= 0:
                c = OFF
            elif u.get("type") == "Francis" and 0.4 <= load < 0.6:
                c = WARN
            else:
                c = _mix(OFF, ON, min(1.0, load))
            _key_color(obj, c, i + 1)
    spill_guid = (params.get("spillway_guid") or "") if isinstance(params.get("spillway_guid"), str) else ""
    sp = ifc.object_for_guid(spill_guid) if spill_guid else None
    if sp is not None:
        sp.animation_data_clear()
        mx = max(1e-6, max(s["spill"]))
        for i, q in enumerate(s["spill"]):
            _key_color(sp, _mix(OFF, SPILL, min(1.0, q / mx)) if q > 0 else (1.0, 1.0, 1.0, 1.0), i + 1)
    sc.frame_set(1)
    for area in getattr(context.screen, "areas", []) if context.screen else []:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.color_type = "OBJECT"
    return n


def clear_animation(context) -> None:
    for o in context.scene.objects:
        if o.animation_data:
            o.animation_data_clear()
