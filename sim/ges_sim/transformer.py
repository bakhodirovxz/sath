"""Elektr qism: kuch transformatori issiqlik holati va umr sarfi (IEC 60076-7:2018 dinamik model), generator
yuklanishi.

Transformator (IEC 60076-7, 8-band, differensial tenglamalar):
  Yuqori moy harorati:  τ_o·dθ_o/dt = [(1 + R·K²)/(1 + R)]^x · Δθ_or − (θ_o − θ_a)
  Issiq nuqta gradienti: τ_w·dΔθ_h/dt = K^y·Δθ_hr − Δθ_h,   θ_h = θ_o + Δθ_h
  K — yuklanish (S/S_nom), R — yuklanish/bo'sh yurish isroflari nisbati (~6), x, y — sovutish rejimi darajalari
  (ONAN: x=0.8, y=1.3; ONAF: 0.8, 1.3; OF: 1.0, 1.3; OD: 1.0, 2.0), Δθ_or — nominal yuqori moy ko'tarilishi (55 K
  ONAN), Δθ_hr — nominal issiq nuqta gradienti (23 K), τ_o ≈ 150 min (ONAN), τ_w ≈ 7 min.
  Qarish tezligi (termik yaxshilangan qog'oz):  V = exp(15000/383 − 15000/(θ_h + 273)),  oddiy: V = 2^((θ_h − 98)/6)
  Umr sarfi:  L = ∫V dt / L_nom (180 000 soat ≈ 20.5 yil, 110 °C da).
  Chegaralar (IEC 60076-7 4-jadval, normal siklik yuk): θ_h ≤ 120 °C, θ_o ≤ 105 °C, K ≤ 1.5; uzoq muddatli favqulodda ≤ 140 °C.
Generator: S = P/cosφ, yuklanish S/S_nom, stator harorati ≈ θ_a + Δθ_nom·K² (I²R), reaktiv chegara.
"""

from __future__ import annotations

import math

from .schema import Field, Meta

COOLING = {  # rejim → (x, y, Δθ_or, Δθ_hr, τ_o daqiqa, τ_w daqiqa, k11, k21, k22)
    "ONAN": (0.8, 1.3, 55.0, 23.0, 210.0, 10.0, 0.5, 2.0, 2.0),
    "ONAF": (0.8, 1.3, 50.0, 26.0, 150.0, 7.0, 0.5, 2.0, 2.0),
    "OF": (1.0, 1.3, 45.0, 26.0, 90.0, 7.0, 1.0, 1.3, 1.0),
    "OD": (1.0, 2.0, 45.0, 26.0, 90.0, 7.0, 1.0, 1.0, 1.0),
}

META = Meta(
    id="transformer",
    title="Transformator yuklanishi va umr sarfi (IEC 60076-7)",
    description="Kunlik yuk profili va havo harorati bo'yicha kuch transformatorining yuqori moy va issiq nuqta "
    "harorati, izolyatsiya qarish tezligi, umr sarfi; generator yuklanishi (cos φ). Ortiqcha yuk ruxsati.",
    group="ekspluatatsiya",
    icon="zap",
    formulas=[
        "τ_o·dθ_o/dt = [(1+R·K²)/(1+R)]^x·Δθ_or − (θ_o − θ_a)",
        "τ_w·dΔθ_h/dt = K^y·Δθ_hr − Δθ_h",
        "V = exp(15000/383 − 15000/(θ_h+273))",
        "S_gen = P/cosφ",
    ],
    outputs=[
        {"key": "hot_spot_max_c", "label": "Maks. issiq nuqta harorati", "unit": "°C"},
        {"key": "top_oil_max_c", "label": "Maks. yuqori moy harorati", "unit": "°C"},
        {"key": "loss_of_life_days", "label": "Umr sarfi (kuniga)", "unit": "kun"},
        {"key": "gen_load_pct", "label": "Generator yuklanishi", "unit": "%"},
    ],
)

FIELDS = [
    Field(
        "rated_mva",
        "Transformator nominal quvvati S_nom",
        "MVA",
        default=100,
        min=0.1,
        group="Transformator",
    ),
    Field(
        "cooling",
        "Sovutish rejimi",
        type="select",
        default="ONAF",
        options=tuple((k, k) for k in COOLING),
        group="Transformator",
    ),
    Field(
        "loss_ratio",
        "Isroflar nisbati R (yuklanish/bo'sh yurish)",
        "",
        default=6.0,
        min=1,
        max=20,
        step=0.5,
        group="Transformator",
    ),
    Field(
        "theta_or",
        "Nominal yuqori moy ko'tarilishi Δθ_or (0 — rejim bo'yicha)",
        "K",
        default=0,
        min=0,
        max=80,
        group="Transformator",
        advanced=True,
    ),
    Field(
        "theta_hr",
        "Nominal issiq nuqta gradienti Δθ_hr (0 — rejim bo'yicha)",
        "K",
        default=0,
        min=0,
        max=50,
        group="Transformator",
        advanced=True,
    ),
    Field(
        "paper",
        "Izolyatsiya qog'ozi",
        type="select",
        default="upgraded",
        options=(("upgraded", "Termik yaxshilangan (110 °C)"), ("kraft", "Oddiy kraft (98 °C)")),
        group="Transformator",
    ),
    Field(
        "load_profile_mw",
        "Kunlik faol yuk (24 qiymat, MW; bo'sh — doimiy)",
        type="series",
        default=[],
        group="Yuk",
    ),
    Field(
        "power_mw",
        "Doimiy faol quvvat (profil bo'sh bo'lsa)",
        "MW",
        default=80,
        min=0,
        group="Yuk",
        live="power",
    ),
    Field(
        "cos_phi",
        "Quvvat koeffitsienti cos φ",
        "",
        default=0.9,
        min=0.5,
        max=1.0,
        step=0.01,
        group="Yuk",
    ),
    Field(
        "ambient_profile",
        "Havo harorati (24 qiymat, °C; bo'sh — doimiy)",
        type="series",
        default=[],
        group="Yuk",
    ),
    Field("ambient_c", "Doimiy havo harorati", "°C", default=30, min=-40, max=55, group="Yuk"),
    Field(
        "days",
        "Takrorlanadigan kunlar (barqaror holatga)",
        "",
        type="int",
        default=3,
        min=1,
        max=30,
        group="Yuk",
        advanced=True,
    ),
    Field(
        "gen_rated_mva",
        "Generator nominal quvvati (0 — tekshirilmasin)",
        "MVA",
        default=0,
        min=0,
        group="Generator",
    ),
    Field(
        "gen_temp_rise",
        "Generator stator nominal qizishi",
        "K",
        default=80,
        min=20,
        max=120,
        group="Generator",
        advanced=True,
    ),
]


def aging_rate(theta_h: float, paper: str) -> float:
    if paper == "kraft":
        return 2 ** ((theta_h - 98) / 6)
    return math.exp(15000 / 383 - 15000 / (theta_h + 273))


def run(p: dict) -> dict:
    x, y, dor, dhr, tau_o, tau_w, k11, _k21, _k22 = COOLING[p["cooling"]]
    dor = p["theta_or"] or dor
    dhr = p["theta_hr"] or dhr
    R = p["loss_ratio"]
    prof = p["load_profile_mw"] or [p["power_mw"]] * 24
    amb = p["ambient_profile"] or [p["ambient_c"]] * 24
    if len(prof) < 24:
        prof = (prof * 24)[:24]
    if len(amb) < 24:
        amb = (amb * 24)[:24]
    S = p["rated_mva"]
    cosphi = p["cos_phi"]
    dt = 1.0  # daqiqa
    n_day = 24 * 60
    theta_o = amb[0] + dor * 0.5
    d_h = dhr * 0.5
    ts, ko, th, to_, ks = [], [], [], [], []
    v_sum = 0.0
    for day in range(int(p["days"])):
        last = day == int(p["days"]) - 1
        for m in range(n_day):
            h = m // 60
            K = (prof[h] / cosphi) / S if S > 0 else 0.0
            ta = amb[h]
            # IEC 60076-7 (8.2.2) — eksponensial yechim o'rniga to'g'ridan-to'g'ri integrallash (Δt = 1 min)
            theta_o += dt / (k11 * tau_o) * (((1 + R * K**2) / (1 + R)) ** x * dor - (theta_o - ta))
            # Issiq nuqta gradienti: ikki shoxli (k21, k22) modelning barqaror qismi K^y·Δθ_hr; τ_w bilan
            d_h += dt / tau_w * (K**y * dhr - d_h)
            theta_h = theta_o + d_h
            if last:
                v_sum += aging_rate(theta_h, p["paper"]) * dt / 60
                if m % 15 == 0:
                    ts.append(round(m / 60, 2))
                    ko.append(round(K, 3))
                    th.append(round(theta_h, 1))
                    to_.append(round(theta_o, 1))
                    ks.append(round(prof[h], 2))
    hs_max, to_max, k_max = max(th), max(to_), max(ko)
    life_hours = 180000 if p["paper"] == "upgraded" else 150000
    lol_days = v_sum / 24  # umr sarfi kunlarda (24 soat nominal qarish = 1 "kun")
    life_years_at_this_load = (
        life_hours / (v_sum / 1.0) / 365 if v_sum > 0 else None
    )  # yiliga: 365·v_sum soat sarflanadi
    problems = []
    if hs_max > 140:
        problems.append(
            f"issiq nuqta {hs_max:.0f} °C > 140 °C — favqulodda chegara, yukni darhol kamaytiring"
        )
    elif hs_max > 120:
        problems.append(f"issiq nuqta {hs_max:.0f} °C > 120 °C (normal siklik yuk chegarasi)")
    if to_max > 105:
        problems.append(f"yuqori moy {to_max:.0f} °C > 105 °C")
    if k_max > 1.5:
        problems.append(f"yuklanish K = {k_max:.2f} > 1.5")
    elif k_max > 1.0:
        problems.append(f"ortiqcha yuk K = {k_max:.2f} (qisqa muddat ruxsat, qarish tezlashadi)")
    if lol_days > 2:
        problems.append(f"qarish nominaldan {lol_days:.1f} marta tez")
    gen = None
    if p["gen_rated_mva"] > 0:
        s_gen = max(prof) / cosphi
        kg = s_gen / p["gen_rated_mva"]
        t_stator = max(amb) + p["gen_temp_rise"] * kg**2
        gen = {
            "s_max_mva": round(s_gen, 2),
            "load_pct": round(kg * 100, 1),
            "stator_temp_c": round(t_stator, 1),
            "reactive_mvar": round(math.sqrt(max(s_gen**2 - max(prof) ** 2, 0)), 2),
        }
        if kg > 1.0:
            problems.append(f"generator yuklanishi {kg * 100:.0f} % > 100 % (cos φ = {cosphi})")
        if t_stator > 120:
            problems.append(f"stator harorati {t_stator:.0f} °C > 120 °C (F klass)")
    return {
        "series": {"t": ts, "hot_spot_c": th, "top_oil_c": to_, "load_factor": ko, "power_mw": ks},
        "generator": gen,
        "summary": {
            "k_max": round(k_max, 3),
            "hot_spot_max_c": round(hs_max, 1),
            "top_oil_max_c": round(to_max, 1),
            "aging_relative": round(lol_days, 3),
            "loss_of_life_days": round(lol_days, 3),
            "life_years_at_this_load": round(life_years_at_this_load, 1)
            if life_years_at_this_load
            else None,
            "gen_load_pct": gen["load_pct"] if gen else None,
            "verdict": "; ".join(problems)
            if problems
            else f"Normal: issiq nuqta {hs_max:.0f} °C, qarish {lol_days:.2f}× nominal",
            "ok": not problems,
        },
    }
