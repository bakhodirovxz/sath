"""Gidravlik zarba (water hammer) bosimli quvurda — xarakteristikalar usuli (MOC).

Zadvijka/yo'naltiruvchi apparat yopilganda (yuk tashlash) quvurdagi bosim ko'tarilishi:
  Jukovskiy (bir zumda yopilish):      ΔH = a·V0 / g
  Mishо (sekin yopilish, Tc > 2L/a):    ΔH = 2·L·V0 / (g·Tc)
  To'lqin tezligi (Korteweg):           a = sqrt(K/ρ) / sqrt(1 + (K/E)·(D/e)·c1)
Vaqt-fazo yechimi — Wylie & Streeter, "Fluid Transients in Systems" (1993), 3-bob:
  C+: H_P = C_P − B·Q_P,  C_P = H_A + B·Q_A − R·Q_A|Q_A|
  C−: H_P = C_M + B·Q_P,  C_M = H_B − B·Q_B + R·Q_B|Q_B|
  B = a/(g·A),  R = f·Δx/(2·g·D·A²),  Δt = Δx/a
Chegaralar: yuqorida suv ombori (H = const), pastda zadvijka Q = Q0·τ(t)·sqrt(H/H0),
τ(t) = (1 − t/Tc)^n (n=1 chiziqli, n>1 — oxirida tez yopiladigan).
Halqa kuchlanish (Barlow):  σ = p·D / (2·e),  p = ρ·g·H_max.
"""

from __future__ import annotations

import math

from .penstock import RHO, G, PenstockSpec, friction_factor, reynolds
from .schema import Field, Meta

K_WATER = 2.15e9  # suvning hajmiy elastiklik moduli, Pa
MATERIALS = {
    "steel": (
        "Po'lat S355/09G2S",
        2.07e11,
        345 / 1.25,
    ),  # E Pa, ruxsat etilgan (o'tkinchi) MPa = σ_T/1.25
    "st3": ("Po'lat St3 (S235)", 2.07e11, 245 / 1.25),
    "17g1s": ("Po'lat 17G1S", 2.07e11, 365 / 1.25),
    "10hsnd": ("Po'lat 10HSND", 2.07e11, 390 / 1.25),
    "s460": ("Po'lat S460", 2.07e11, 460 / 1.25),
    "ductile_iron": ("Cho'yan (yuqori mustahkam)", 1.70e11, 120.0),
    "concrete": ("Temir-beton (B30)", 3.25e10, 8.0),
    "grp": ("Shisha-plastik (GRP)", 2.5e10, 60.0),
}

META = Meta(
    id="water_hammer",
    title="Gidravlik zarba (bosim oshishi)",
    description="Yuk tashlash / zadvijka yopilishida bosimli quvurdagi bosim to'lqini: maksimal napor, "
    "halqa kuchlanish va mustahkamlik zaxirasi, kavitatsiya xavfi. Xarakteristikalar usuli.",
    group="gidravlika",
    icon="gauge",
    formulas=[
        "ΔH_Jukovskiy = a·V₀/g",
        "ΔH_Misho = 2·L·V₀/(g·T_c)  (T_c > 2L/a)",
        "a = √(K/ρ) / √(1 + (K/E)(D/e)c₁)",
        "MOC: H_P = (C_P + C_M)/2, Q_P = (C_P − C_M)/(2B)",
        "σ = ρ·g·H_max·D/(2e)",
    ],
    viz={"penstock_profile": "h_max_x", "water_level": None},
    outputs=[
        {"key": "h_max_m", "label": "Maksimal napor (zadvijkada)", "unit": "m"},
        {"key": "dh_max_m", "label": "Bosim ko'tarilishi", "unit": "m"},
        {"key": "stress_mpa", "label": "Halqa kuchlanish", "unit": "MPa"},
        {"key": "safety_factor", "label": "Mustahkamlik zaxirasi", "unit": ""},
    ],
)

FIELDS = [
    Field(
        "length_m",
        "Quvur uzunligi",
        "m",
        default=300,
        min=5,
        group="Quvur",
        model="penstock.length_m",
    ),
    Field(
        "diameter_m",
        "Ichki diametr",
        "m",
        default=3.0,
        min=0.1,
        step=0.1,
        group="Quvur",
        model="penstock.diameter_m",
    ),
    Field("wall_mm", "Devor qalinligi", "mm", default=20, min=1, group="Quvur"),
    Field(
        "material",
        "Material",
        type="select",
        default="steel",
        options=tuple((k, v[0]) for k, v in MATERIALS.items()),
        group="Quvur",
    ),
    Field(
        "roughness_mm",
        "G'adir-budirlik",
        "mm",
        default=0.1,
        min=0.001,
        step=0.01,
        group="Quvur",
        model="penstock.roughness_mm",
        advanced=True,
    ),
    Field(
        "anchor_c1",
        "Mahkamlash koeff. c₁",
        "",
        default=1.0,
        min=0.5,
        max=1.0,
        step=0.05,
        group="Quvur",
        hint="1 — kompensatorli; 0.91 — butunlay mahkamlangan (1−ν²)",
        advanced=True,
    ),
    Field(
        "head_m",
        "Statik napor (ombor − zadvijka)",
        "m",
        default=90,
        min=1,
        group="Rejim",
        live="gross_head",
    ),
    Field(
        "flow_m3s",
        "Boshlang'ich sarf Q₀",
        "m³/s",
        default=40,
        min=0.01,
        group="Rejim",
        live="penstock_flow",
    ),
    Field(
        "close_s",
        "Yopilish vaqti T_c",
        "s",
        default=6,
        min=0.05,
        step=0.5,
        group="Rejim",
        hint="Yo'naltiruvchi apparat / zadvijka",
    ),
    Field(
        "close_exp",
        "Yopilish qonuni darajasi n",
        "",
        default=1.0,
        min=0.5,
        max=3,
        step=0.1,
        group="Rejim",
        hint="τ=(1−t/Tc)ⁿ",
        advanced=True,
    ),
    Field("sim_s", "Hisob davomiyligi", "s", default=30, min=1, group="Rejim"),
    Field(
        "reaches",
        "Bo'laklar soni N",
        "",
        type="int",
        default=20,
        min=4,
        max=200,
        group="Rejim",
        advanced=True,
    ),
    Field(
        "valve_elev_m",
        "Zadvijka belgisi (quvur eng past nuqtasi)",
        "m",
        default=0,
        group="Rejim",
        hint="Kavitatsiya tekshiruvi uchun (H_abs < −10 m)",
        advanced=True,
    ),
]


def wave_speed(diameter_m: float, wall_m: float, e_pa: float, c1: float = 1.0) -> float:
    """Korteweg: elastik devorli quvurda bosim to'lqini tezligi, m/s."""
    return math.sqrt(K_WATER / RHO) / math.sqrt(1 + (K_WATER / e_pa) * (diameter_m / wall_m) * c1)


def run(p: dict) -> dict:
    L, D = p["length_m"], p["diameter_m"]
    e = p["wall_mm"] / 1000
    mat_name, E, sigma_all = MATERIALS[p["material"]]
    a = wave_speed(D, e, E, p["anchor_c1"])
    spec = PenstockSpec(L, D, p["roughness_mm"], 0.0)
    A = spec.area
    q0 = p["flow_m3s"]
    v0 = q0 / A
    f = friction_factor(reynolds(q0, spec), p["roughness_mm"] / 1000 / D)
    hf0 = f * L / D * v0**2 / (2 * G)
    h_res = p["head_m"]
    h0 = h_res - hf0  # zadvijkada boshlang'ich napor
    if h0 <= 0:
        raise ValueError(
            "Ishqalanish yo'qotishi statik napordan katta — sarf yoki uzunlikni tekshiring"
        )
    tc, n_exp = p["close_s"], p["close_exp"]

    # Analitik baholar
    t_crit = 2 * L / a
    dh_jouk = a * v0 / G
    dh_michaud = 2 * L * v0 / (G * tc)
    dh_theory = dh_jouk if tc <= t_crit else dh_michaud

    # MOC to'ri
    N = int(p["reaches"])
    dx = L / N
    dt = dx / a
    B = a / (G * A)
    R = f * dx / (2 * G * D * A**2)
    steps = int(p["sim_s"] / dt) + 1
    H = [h_res - hf0 * i / N for i in range(N + 1)]
    Q = [q0] * (N + 1)
    cv0 = q0**2 / h0  # Q = sqrt(cv0·τ²·H)
    t_series, h_valve, q_valve, h_mid = [], [], [], []
    h_max = list(H)
    h_min = list(H)
    frames: list[dict] = []  # 3D animatsiya uchun: har ~1/60 davrda quvur bo'ylab napor
    frame_every = max(steps // 60, 1)
    for k in range(steps):
        t = k * dt
        if k % frame_every == 0:
            frames.append({"t": round(t, 3), "h": [round(v, 2) for v in H]})
        t_series.append(round(t, 4))
        h_valve.append(round(H[N], 3))
        q_valve.append(round(Q[N], 4))
        h_mid.append(round(H[N // 2], 3))
        Hn, Qn = [0.0] * (N + 1), [0.0] * (N + 1)
        # Suv ombori (yuqori chegara)
        cm = H[1] - B * Q[1] + R * Q[1] * abs(Q[1])
        Hn[0] = h_res
        Qn[0] = (Hn[0] - cm) / B
        # Ichki nuqtalar
        for i in range(1, N):
            cp = H[i - 1] + B * Q[i - 1] - R * Q[i - 1] * abs(Q[i - 1])
            cm = H[i + 1] - B * Q[i + 1] + R * Q[i + 1] * abs(Q[i + 1])
            Hn[i] = (cp + cm) / 2
            Qn[i] = (cp - cm) / (2 * B)
        # Zadvijka (quyi chegara): Q_P = −B·Cv/2 + sqrt((B·Cv/2)² + Cv·C_P)
        tau = (1 - (t + dt) / tc) ** n_exp if (t + dt) < tc else 0.0
        cp = H[N - 1] + B * Q[N - 1] - R * Q[N - 1] * abs(Q[N - 1])
        cv = cv0 * tau**2
        if cv > 0 and cp > 0:
            Qn[N] = -B * cv / 2 + math.sqrt((B * cv / 2) ** 2 + cv * cp)
        else:
            Qn[N] = 0.0
        Hn[N] = cp - B * Qn[N]
        H, Q = Hn, Qn
        for i in range(N + 1):
            h_max[i] = max(h_max[i], H[i])
            h_min[i] = min(h_min[i], H[i])

    hmax = max(h_max)
    hmin = min(h_min)
    p_max = RHO * G * hmax  # Pa (manometrik)
    stress = p_max * D / (2 * e) / 1e6  # MPa
    sf = sigma_all / stress if stress > 0 else 99.0
    # Kavitatsiya: absolyut napor ≈ H + 10.3 m; suv bug'lanish napori ≈ 0.24 m (20 °C)
    cav = hmin + 10.3 < 0.3
    x_series = [round(i * dx, 2) for i in range(N + 1)]
    verdict = (
        "XAVFLI: kuchlanish ruxsat etilgandan yuqori"
        if sf < 1.0
        else "Zaxira kam (< 1.5)"
        if sf < 1.5
        else "Qoniqarli"
    )
    return {
        "series": {
            "t": t_series,
            "h_valve": h_valve,
            "q_valve": q_valve,
            "h_mid": h_mid,
        },
        "profile": {
            "x": x_series,
            "h_max_x": [round(v, 2) for v in h_max],
            "h_min_x": [round(v, 2) for v in h_min],
            "frames": frames,
        },
        "summary": {
            "wave_speed_ms": round(a, 1),
            "t_critical_s": round(t_crit, 3),
            "closure": "tez (T_c ≤ 2L/a)" if tc <= t_crit else "sekin (T_c > 2L/a)",
            "dh_theory_m": round(dh_theory, 2),
            "dh_joukowsky_m": round(dh_jouk, 2),
            "h0_m": round(h0, 2),
            "h_max_m": round(hmax, 2),
            "dh_max_m": round(hmax - h0, 2),
            "h_min_m": round(hmin, 2),
            "p_max_bar": round(p_max / 1e5, 2),
            "stress_mpa": round(stress, 1),
            "allowable_mpa": sigma_all,
            "safety_factor": round(sf, 2),
            "cavitation_risk": bool(cav),
            "material": mat_name,
            "verdict": verdict + (" · kavitatsiya xavfi (manfiy bosim)" if cav else ""),
            "ok": sf >= 1.5 and not cav,
        },
    }
