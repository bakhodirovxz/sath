"""Egizak simulyatsiyalari: parametrlar modeldagi GES obyektlaridan (obj.ges.params, rollar), hisob serverda
(ges_sim: gidrozarba MOC, HYGOV regulyator, IEC 60076-7 transformator, Eurocode 8 zilzila), natija — Blender timeline
animatsiyasi (sim_anim)."""

from __future__ import annotations

import bpy

from . import ges_objects, ops_sim, session, sim_anim, water
from .shared.server_client import ServerError

HAMMER_META = {
    "outputs": [
        {"key": "wave_speed_ms", "label": "To'lqin tezligi", "unit": "m/s"},
        {"key": "dh_max_m", "label": "Maks. napor ortishi", "unit": "m"},
        {"key": "h_max_m", "label": "Maks. napor", "unit": "m"},
        {"key": "p_max_bar", "label": "Maks. bosim", "unit": "bar"},
        {"key": "stress_mpa", "label": "Halqa kuchlanish", "unit": "MPa"},
        {"key": "closure", "label": "Yopilish", "unit": ""},
    ]
}
GOV_META = {
    "outputs": [
        {"key": "freq_max_dev_pct", "label": "Chastota maks. og'ishi", "unit": "%"},
        {"key": "overspeed_pct", "label": "Ortiqcha tezlik", "unit": "%"},
        {"key": "settling_s", "label": "O'rnashish vaqti", "unit": "s"},
        {"key": "stable", "label": "Barqaror", "unit": ""},
        {"key": "r_recommended", "label": "Tavsiya r", "unit": ""},
    ]
}
TR_META = {
    "outputs": [
        {"key": "hot_spot_max_c", "label": "Issiq nuqta maks.", "unit": "°C"},
        {"key": "top_oil_max_c", "label": "Yuqori moy maks.", "unit": "°C"},
        {"key": "loss_of_life_days", "label": "Umr sarfi", "unit": "kun"},
        {"key": "life_years_at_this_load", "label": "Shu yukda umr", "unit": "yil"},
    ]
}
SEIS_META = {
    "outputs": [
        {"key": "pga_g", "label": "PGA", "unit": "g"},
        {"key": "kh", "label": "Seysmik koeffitsient k_h", "unit": ""},
        {"key": "dam_sa_g", "label": "To'g'on S_a", "unit": "g"},
        {"key": "powerhouse_sa_g", "label": "Mashina zali S_a", "unit": "g"},
        {"key": "westergaard_kn_m", "label": "Gidrodinamik kuch", "unit": "kN/m"},
    ]
}
_MATERIAL = {"Po'lat": "steel", "Temir-beton": "concrete", "GRP": "grp"}
_COOLING = {"ONAN": "ONAN", "ONAF": "ONAF", "OFAF": "OF", "ODAF": "OD"}


def _first(kind: str):
    objs = ges_objects.by_kind(kind)
    return objs[0] if objs else None


def _gross_head() -> float | None:
    up, tw = bpy.data.objects.get(water.NAME), bpy.data.objects.get(water.TAIL_NAME)
    if up is not None and tw is not None:
        return float(up.location.z - tw.location.z)
    return None


def hammer_params(s) -> dict:
    pen, unit = _first("GES_Penstock"), _first("GES_Turbine")
    if pen is None:
        raise ValueError("Modelda bosh quvur (GES_Penstock) yo'q")
    p = ges_objects.params_dict(pen)
    u = ges_objects.params_dict(unit) if unit is not None else {}
    head = _gross_head() or float(u.get("RatedHead", 45.0))
    return {
        "length_m": p.get("Length", 100.0),
        "diameter_m": p.get("Diameter", 3.0),
        "wall_mm": max(1.0, p.get("WallThickness", 0.02) * 1000.0),
        "material": _MATERIAL.get(str(p.get("Material", "Po'lat")), "steel"),
        "roughness_mm": p.get("Roughness", 0.1),
        "head_m": round(head, 2),
        "flow_m3s": float(u.get("RatedFlow", 40.0)),
        "close_s": float(s.hammer_close_s),
        "sim_s": round(4 * float(s.hammer_close_s) + 10, 1),
        "reaches": 20,
    }


def governor_params(s) -> dict:
    pen, unit = _first("GES_Penstock"), _first("GES_Turbine")
    u = ges_objects.params_dict(unit) if unit is not None else {}
    p = ges_objects.params_dict(pen) if pen is not None else {}
    # Suv ishga tushish vaqti T_w = L·V/(g·H), V = 4Q/(πD²)
    L, D = p.get("Length", 100.0), p.get("Diameter", 3.0)
    q, h = float(u.get("RatedFlow", 40.0)), float(u.get("RatedHead", 45.0))
    v = 4 * q / (3.14159265 * D * D) if D > 0 else 4.0
    tw = max(0.5, min(4.0, L * v / (9.81 * h))) if h > 0 else 1.5
    return {
        "event": s.gov_event,
        "step_pu": float(s.gov_step),
        "p0_pu": 0.8,
        "tw": round(tw, 2),
        "sim_s": 60,
    }


def transformer_params(s) -> dict:
    tf, unit = _first("GES_Transformer"), _first("GES_Turbine")
    t = ges_objects.params_dict(tf) if tf is not None else {}
    u = ges_objects.params_dict(unit) if unit is not None else {}
    mva = float(t.get("RatedPower", 40.0))
    return {
        "rated_mva": mva,
        "cooling": _COOLING.get(str(t.get("Cooling", "ONAF")), "ONAF"),
        "power_mw": round(mva * 0.9 * float(s.tr_load) / 100.0, 2),
        "cos_phi": 0.9,
        "days": int(s.tr_days),
        "gen_rated_mva": float(u.get("RatedPower", 25.0)) / 0.9,
    }


def seismic_params(s) -> dict:
    dam, ph, pen = _first("GES_Dam"), _first("GES_Powerhouse"), _first("GES_Penstock")
    d = ges_objects.params_dict(dam) if dam is not None else {}
    p = ges_objects.params_dict(ph) if ph is not None else {}
    head = _gross_head()
    h_dam = float(d.get("Height", 80.0))
    out = {
        "intensity": s.seis_intensity,
        "ground": s.seis_ground,
        "dam_height_m": h_dam,
        "dam_base_m": float(d.get("BaseWidth", 0.8 * h_dam)),
        "water_depth_m": round(min(h_dam - 3.0, (head or 0.75 * h_dam) + 10.0), 1),
        "ph_height_m": float(p.get("Height", 30.0)),
    }
    if pen is not None:
        pp = ges_objects.params_dict(pen)
        out["penstock_mass_t"] = round(7850 * 3.14159265 * pp.get("Diameter", 3.0) * pp.get("WallThickness", 0.02) * pp.get("Length", 100.0) / 1000.0, 1)
    return out


class _TwinSim(bpy.types.Operator):
    kind = ""
    meta: dict = {}
    title = ""

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def params(self, s) -> dict:
        raise NotImplementedError

    def animate(self, context, result: dict, s) -> str:
        raise NotImplementedError

    def execute(self, context):
        s = context.scene.ges
        try:
            params = self.params(s)
            job = session.client().create_sim(s.model_id, f"{self.title} (egizak)", s.version_id or None, params, kind=self.kind)
        except (ServerError, ValueError, KeyError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.sim_job_id = job["id"]
        s.sim_status = "Hisoblanmoqda…"

        def done(result: dict):
            s.twin_note = self.animate(bpy.context, result, s)

        bpy.app.timers.register(ops_sim._poll_factory(self.meta, job["id"], done), first_interval=0.6)
        return {"FINISHED"}


class SATH_OT_sim_hammer(_TwinSim):
    """Gidrozarba (MOC, Wylie–Streeter): zadvijka yopilganda bosh quvur bo'ylab bosim — markerlar animatsiyasi"""

    bl_idname = "sath.sim_hammer"
    bl_label = "Gidrozarba"
    kind, meta, title = "water_hammer", HAMMER_META, "Gidrozarba"

    def params(self, s):
        return hammer_params(s)

    def animate(self, context, result, s):
        n = sim_anim.animate_hammer(context, result, _first("GES_Penstock"))
        sm = result.get("summary", {})
        return f"{n} kadr: ΔH maks {sm.get('dh_max_m', 0):.1f} m, {sm.get('p_max_bar', 0):.1f} bar — Space bilan ijro"


class SATH_OT_sim_governor(_TwinSim):
    """Agregat–regulyator (HYGOV): chastota o'tish jarayoni — rotor aylanishi va ranglar animatsiyasi"""

    bl_idname = "sath.sim_governor"
    bl_label = "Regulyator"
    kind, meta, title = "governor", GOV_META, "Regulyator"

    def params(self, s):
        return governor_params(s)

    def animate(self, context, result, s):
        n = sim_anim.animate_governor(context, result)
        sm = result.get("summary", {})
        return f"{n} kadr: Δf maks {sm.get('freq_max_dev_pct', 0):.2f} %, o'rnashish {sm.get('settling_s', 0):.1f} s"


class SATH_OT_sim_transformer(_TwinSim):
    """Transformator issiqlik holati (IEC 60076-7): issiq nuqta harorati → rang animatsiyasi"""

    bl_idname = "sath.sim_transformer"
    bl_label = "Transformator"
    kind, meta, title = "transformer", TR_META, "Transformator issiqligi"

    def params(self, s):
        return transformer_params(s)

    def animate(self, context, result, s):
        n = sim_anim.animate_transformer(context, result)
        sm = result.get("summary", {})
        return f"{n} kadr: issiq nuqta maks {sm.get('hot_spot_max_c', 0):.0f} °C, umr sarfi {sm.get('loss_of_life_days', 0):.1f} kun"


class SATH_OT_sim_seismic(_TwinSim):
    """Zilzila (Eurocode 8 spektri): inshootlar tebranishi (psevdo-spektral siljish, vizual ko'paytirgich) va rang"""

    bl_idname = "sath.sim_seismic"
    bl_label = "Zilzila"
    kind, meta, title = "seismic", SEIS_META, "Zilzila"

    def params(self, s):
        return seismic_params(s)

    def animate(self, context, result, s):
        n = sim_anim.animate_seismic(context, result, scale=float(s.seis_scale))
        sm = result.get("summary", {})
        return f"{n} kadr: PGA {sm.get('pga_g', 0):.2f} g, k_h {sm.get('kh', 0):.3f} (siljish ×{s.seis_scale:.0f})"


CLASSES = (SATH_OT_sim_hammer, SATH_OT_sim_governor, SATH_OT_sim_transformer, SATH_OT_sim_seismic)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
