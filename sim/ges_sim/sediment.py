"""Suv omborining loyqa bosishi (sedimentatsiya): ushlab qolish samaradorligi, foydali hajm yo'qotilishi, xizmat muddati.

Brune (1953) egri chizig'i — Gill (1979) o'rta approksimatsiyasi:  TE = (C/inflow_yr) / (0.012 + 1.02·(C/inflow_yr)),
  C — ombor sig'imi (m³), inflow_yr — o'rtacha yillik oqim (m³/yil).
Yillik cho'kma:  V_s = (W_s·TE) / ρ_b,  W_s — yillik qattiq oqim (t/yil) = Q_yil·c_s yoki Y_s·A_havza,
  ρ_b — cho'kma zichligi (Lara & Pemberton: gil 0.96, alevrit 1.12, qum 1.55 t/m³; aralash ~1.2–1.35).
Har yil sig'im kamayadi → TE qayta hisoblanadi; o'lik hajm to'lgan yil = "xizmat muddati" (Xrenov-Brune sxemasi).
"""

from __future__ import annotations

from .schema import Field, Meta

META = Meta(
    id="sediment",
    title="Loyqa bosishi (xizmat muddati)",
    description="Yillik qattiq oqim va Brune ushlab qolish egri chizig'i bo'yicha ombor sig'imining yildan-yilga "
    "kamayishi, o'lik hajm to'lish yili, energiya ishlab chiqarishga ta'siri.",
    group="ekspluatatsiya",
    icon="layers",
    formulas=[
        "TE = (C/inflow_yr)/(0.012 + 1.02·C/inflow_yr)",
        "V_s = W_s·TE/ρ_b",
        "C_{n+1} = C_n − V_s",
    ],
    outputs=[
        {"key": "years_dead", "label": "O'lik hajm to'lish yili", "unit": "yil"},
        {"key": "years_half", "label": "Sig'im 50 % ga tushish", "unit": "yil"},
        {"key": "te0_pct", "label": "Boshlang'ich ushlab qolish", "unit": "%"},
    ],
)

FIELDS = [
    Field("capacity_mcm", "To'liq sig'im (NPU da)", "mln m³", default=480, min=0.1, group="Ombor"),
    Field("dead_mcm", "O'lik hajm", "mln m³", default=60, min=0, group="Ombor"),
    Field(
        "inflow_m3s",
        "O'rtacha ko'p yillik sarf",
        "m³/s",
        default=120,
        min=0.1,
        group="Oqim",
        live="inflow",
    ),
    Field(
        "concentration_kg_m3",
        "O'rtacha loyqalik",
        "kg/m³",
        default=1.2,
        min=0,
        step=0.1,
        group="Oqim",
        hint="Chirchiq 0.3–0.8; Amudaryo 2–4",
    ),
    Field(
        "yield_t_km2",
        "yoki eroziya moduli (0 — loyqalik bo'yicha)",
        "t/km²/yil",
        default=0,
        min=0,
        group="Oqim",
        advanced=True,
    ),
    Field("basin_km2", "Havza maydoni", "km²", default=10000, min=1, group="Oqim", advanced=True),
    Field(
        "bulk_density",
        "Cho'kma zichligi ρ_b",
        "t/m³",
        default=1.25,
        min=0.6,
        max=2.0,
        step=0.05,
        group="Oqim",
    ),
    Field(
        "bedload_pct",
        "Tubi oqim ulushi (qo'shimcha)",
        "%",
        default=15,
        min=0,
        max=100,
        group="Oqim",
        advanced=True,
    ),
    Field("years", "Hisob davri", "yil", type="int", default=100, min=1, max=500, group="Oqim"),
    Field(
        "energy_gwh",
        "Yillik ishlab chiqarish (hozir)",
        "GVt·soat",
        default=0,
        min=0,
        group="Oqim",
        hint="0 — hisoblanmaydi; foydali hajmga proporsional kamayadi",
        advanced=True,
    ),
]


def trap_efficiency(cap_m3: float, inflow_m3_yr: float) -> float:
    ci = cap_m3 / inflow_m3_yr if inflow_m3_yr > 0 else 0.0
    if ci <= 0:
        return 0.0
    return max(min(ci / (0.012 + 1.02 * ci), 1.0), 0.0)


def run(p: dict) -> dict:
    cap = p["capacity_mcm"] * 1e6
    dead = p["dead_mcm"] * 1e6
    live0 = cap - dead
    inflow_yr = p["inflow_m3s"] * 365.25 * 86400  # m³/yil
    if p["yield_t_km2"] > 0:
        ws = p["yield_t_km2"] * p["basin_km2"]
    else:
        ws = inflow_yr * p["concentration_kg_m3"] / 1000  # t/yil
    ws *= 1 + p["bedload_pct"] / 100
    rho = p["bulk_density"]
    years, caps, tes, dead_fill, energy = [], [], [], [], []
    c = cap
    sed_total = 0.0
    y_dead = y_half = None
    te0 = trap_efficiency(c, inflow_yr)
    for y in range(int(p["years"]) + 1):
        te = trap_efficiency(c, inflow_yr)
        years.append(y)
        caps.append(round(c / 1e6, 2))
        tes.append(round(te * 100, 1))
        dead_fill.append(round(min(sed_total / dead * 100, 100) if dead > 0 else 100, 1))
        live_now = max(c - max(dead - sed_total, 0.0), 0.0)
        energy.append(
            round(p["energy_gwh"] * live_now / live0, 1)
            if p["energy_gwh"] > 0 and live0 > 0
            else 0.0
        )
        if y_dead is None and sed_total >= dead:
            y_dead = y
        if y_half is None and c <= cap / 2:
            y_half = y
        vs = ws * te / rho
        sed_total += vs
        c = max(c - vs, 0.0)
    return {
        "series": {
            "year": years,
            "capacity_mcm": caps,
            "trap_eff_pct": tes,
            "dead_fill_pct": dead_fill,
            "energy_gwh": energy,
        },
        "summary": {
            "sediment_t_yr": round(ws, 0),
            "sediment_mcm_yr": round(ws * te0 / rho / 1e6, 3),
            "te0_pct": round(te0 * 100, 1),
            "years_dead": y_dead,
            "years_half": y_half,
            "capacity_end_mcm": caps[-1],
            "loss_end_pct": round((1 - caps[-1] / (cap / 1e6)) * 100, 1),
            "verdict": (
                f"O'lik hajm {y_dead}-yilda to'ladi"
                if y_dead is not None
                else f"{p['years']} yilda o'lik hajm to'lmaydi"
            )
            + f"; {p['years']} yildan keyin sig'im {caps[-1]} mln m³",
            "ok": y_dead is None or y_dead >= 50,
        },
    }
