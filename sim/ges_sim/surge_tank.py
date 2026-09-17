"""Bosim tenglashtiruvchi minora (surge tank) — massa tebranishi (qattiq ustun modeli).

Tunnel (L, A_t) suv omboridan minoraga, minoradan turbinaga. Yuk tashlash/qabul qilishda
minora sathi z (ombor sathiga nisbatan) tebranadi:
  (L/g)·dV/dt = −z − h_f(V),   h_f = (f·L/D + k)·V|V| / (2g)
  A_s·dz/dt = A_t·V − Q_turb(t)
Ishqalanishsiz maksimal ko'tarilish (yuk tashlash):  z_max = V₀·√(L·A_t / (g·A_s))
Toma barqarorlik shart (Thoma, 1910):  A_s > A_Th = L·A_t / (2·g·α·H₀),  α = h_f0/V₀²
RK4 integrallash. Manba: Chaudhry, "Applied Hydraulic Transients", 10-bob.
"""

from __future__ import annotations

import math

from .penstock import G, PenstockSpec, friction_factor, reynolds
from .schema import Field, Meta

META = Meta(
    id="surge_tank",
    title="Bosim tenglashtiruvchi minora",
    description="Yuk tashlash/qabul qilishda minora sathining tebranishi: maksimal ko'tarilish va tushish, "
    "Toma barqarorlik sharti, toshib ketish / havo tortish tekshiruvi.",
    group="gidravlika",
    icon="cylinder",
    formulas=[
        "(L/g)·dV/dt = −z − h_f(V)",
        "A_s·dz/dt = A_t·V − Q_turb(t)",
        "z_max ≈ V₀·√(L·A_t/(g·A_s))",
        "A_Th = L·A_t/(2·g·α·H₀)",
    ],
    outputs=[
        {"key": "z_max_m", "label": "Maksimal ko'tarilish", "unit": "m"},
        {"key": "z_min_m", "label": "Maksimal tushish", "unit": "m"},
        {"key": "thoma_ratio", "label": "A_s / A_Thoma", "unit": ""},
    ],
)

FIELDS = [
    Field("tunnel_length_m", "Tunnel uzunligi L", "m", default=1200, min=10, group="Tunnel"),
    Field(
        "tunnel_diameter_m",
        "Tunnel diametri D",
        "m",
        default=5.0,
        min=0.5,
        step=0.1,
        group="Tunnel",
    ),
    Field(
        "roughness_mm", "G'adir-budirlik", "mm", default=0.5, min=0.001, step=0.01, group="Tunnel"
    ),
    Field(
        "minor_k",
        "Mahalliy yo'qotish Σk",
        "",
        default=1.0,
        min=0,
        step=0.1,
        group="Tunnel",
        advanced=True,
    ),
    Field(
        "tank_diameter_m", "Minora diametri", "m", default=12.0, min=0.5, step=0.5, group="Minora"
    ),
    Field(
        "tank_top_m",
        "Minora yuqori chegarasi (ombor sathidan)",
        "m",
        default=15,
        group="Minora",
        hint="+ yuqoriga",
    ),
    Field(
        "tank_bottom_m",
        "Minora tubi (ombor sathidan)",
        "m",
        default=-30,
        group="Minora",
        hint="− pastga; tunnel o'qi",
    ),
    Field(
        "head_m",
        "Napor H₀ (ombor − turbina)",
        "m",
        default=120,
        min=1,
        group="Rejim",
        live="gross_head",
    ),
    Field(
        "flow_m3s",
        "Boshlang'ich sarf Q₀",
        "m³/s",
        default=60,
        min=0.01,
        group="Rejim",
        live="penstock_flow",
    ),
    Field(
        "event",
        "Hodisa",
        type="select",
        default="rejection",
        options=(
            ("rejection", "Yuk tashlash (Q₀ → 0)"),
            ("acceptance", "Yuk qabul (0 → Q₀)"),
            ("partial", "Qisman tashlash (Q₀ → Q₁)"),
        ),
        group="Rejim",
    ),
    Field("flow_final_m3s", "Yakuniy sarf Q₁ (qisman)", "m³/s", default=20, min=0, group="Rejim"),
    Field("change_s", "O'zgarish vaqti", "s", default=8, min=0.1, group="Rejim"),
    Field("sim_s", "Hisob davomiyligi", "s", default=600, min=10, group="Rejim"),
]


def run(p: dict) -> dict:
    L, D = p["tunnel_length_m"], p["tunnel_diameter_m"]
    spec = PenstockSpec(L, D, p["roughness_mm"], p["minor_k"])
    A_t = spec.area
    A_s = math.pi * p["tank_diameter_m"] ** 2 / 4
    q0 = p["flow_m3s"]
    ev = p["event"]
    q_start = 0.0 if ev == "acceptance" else q0
    q_end = q0 if ev == "acceptance" else (p["flow_final_m3s"] if ev == "partial" else 0.0)
    tch = p["change_s"]
    H0 = p["head_m"]

    def hf(v: float) -> float:
        q = abs(v) * A_t
        f = friction_factor(reynolds(q, spec), p["roughness_mm"] / 1000 / D) if q > 1e-9 else 0.0
        return (f * L / D + p["minor_k"]) * v * abs(v) / (2 * G)

    def q_turb(t: float) -> float:
        if t >= tch:
            return q_end
        return q_start + (q_end - q_start) * t / tch

    # Boshlang'ich holat: statsionar — minora sathi ishqalanish yo'qotishi qadar past
    v = q_start / A_t
    z = -hf(v)

    def deriv(t: float, v: float, z: float) -> tuple[float, float]:
        return (G / L) * (-z - hf(v)), (A_t * v - q_turb(t)) / A_s

    dt = 0.25
    n = int(p["sim_s"] / dt) + 1
    ts, zs, vs, qs = [], [], [], []
    for k in range(n):
        t = k * dt
        ts.append(round(t, 2))
        zs.append(round(z, 3))
        vs.append(round(v, 4))
        qs.append(round(q_turb(t), 3))
        k1 = deriv(t, v, z)
        k2 = deriv(t + dt / 2, v + dt / 2 * k1[0], z + dt / 2 * k1[1])
        k3 = deriv(t + dt / 2, v + dt / 2 * k2[0], z + dt / 2 * k2[1])
        k4 = deriv(t + dt, v + dt * k3[0], z + dt * k3[1])
        v += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        z += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])

    v0 = q0 / A_t
    z_theory = v0 * math.sqrt(L * A_t / (G * A_s))
    alpha = hf(v0) / v0**2 if v0 > 0 else 0.0
    a_thoma = L * A_t / (2 * G * alpha * H0) if alpha > 0 else 0.0
    thoma_ratio = A_s / a_thoma if a_thoma > 0 else 99.0
    zmax, zmin = max(zs), min(zs)
    overflow = zmax > p["tank_top_m"]
    air = zmin < p["tank_bottom_m"]
    verdict = []
    if overflow:
        verdict.append("minoradan suv toshadi (yuqori chegara oshdi)")
    if air:
        verdict.append("minora bo'shaydi — tunnelga havo tortiladi")
    if thoma_ratio < 1.0:
        verdict.append("Toma sharti bajarilmaydi (tebranish so'nmaydi)")
    elif thoma_ratio < 1.5:
        verdict.append("Toma zaxirasi kam (< 1.5)")
    return {
        "series": {"t": ts, "z": zs, "v_tunnel": vs, "q_turbine": qs},
        "summary": {
            "z_max_m": round(zmax, 2),
            "z_min_m": round(zmin, 2),
            "z_max_theory_m": round(z_theory, 2),
            "period_s": round(2 * math.pi * math.sqrt(L * A_s / (G * A_t)), 1),
            "thoma_area_m2": round(a_thoma, 1),
            "tank_area_m2": round(A_s, 1),
            "thoma_ratio": round(thoma_ratio, 2),
            "overflow": overflow,
            "air_entrainment": air,
            "verdict": "; ".join(verdict) if verdict else "Qoniqarli",
            "ok": not verdict,
        },
    }
