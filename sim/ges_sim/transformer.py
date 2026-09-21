"""Elektr qism: kuch transformatori issiqlik holati va umr sarfi (IEC 60076-7:2018 dinamik model), generator
yuklanishi.

Transformator (IEC 60076-7, 8-band, differensial tenglamalar):
  Yuqori moy harorati:  τ_o·dθ_o/dt = [(1 + R·K²)/(1 + R)]^x · Δθ_or − (θ_o − θ_a)
  Issiq nuqta gradienti — ikki shoxli model (IEC 60076-7:2018 §8.2.2, (10)–(12)):
    Δθ_h = Δθ_h1 − Δθ_h2;  k22·τ_w·dΔθ_h1/dt = k21·K^y·Δθ_hr − Δθ_h1;
    (τ_o/k22)·dΔθ_h2/dt = (k21 − 1)·K^y·Δθ_hr − Δθ_h2;   θ_h = θ_o + Δθ_h
    (k21 > 1 yuk sakrashida issiq nuqtaning vaqtinchalik oshib ketishini beradi — 120/140 °C
    chegaralari aynan shu cho'qqiga nisbatan tekshiriladi; bir shoxli soddalashtirish uni yo'qotadi)
  K — yuklanish (S/S_nom), R — yuklanish/bo'sh yurish isroflari nisbati (~6), x, y — sovutish rejimi darajalari
  (ONAN: x=0.8, y=1.3; ONAF: 0.8, 1.3; OF: 1.0, 1.3; OD: 1.0, 2.0), Δθ_or — nominal yuqori moy ko'tarilishi (55 K
  ONAN), Δθ_hr — nominal issiq nuqta gradienti (23 K), τ_o ≈ 150 min (ONAN), τ_w ≈ 7 min.
  Qarish tezligi (termik yaxshilangan qog'oz):  V = exp(15000/383 − 15000/(θ_h + 273)),  oddiy: V = 2^((θ_h − 98)/6)
  Umr sarfi:  ∫V dt — kuniga sarflangan nominal umr soatlari (loss_of_life_h); aging_relative = ∫V dt / 24
  (o'lchamsiz o'rtacha nisbiy qarish). L_nom (life_hours): IEEE C57.91-2011 I-jadval — termik
  yaxshilangan qog'oz 180 000 soat (110 °C da, 50 % mustahkamlik), oddiy kraft 65 000 soat (95 °C,
  IEEE C57.91-1981); IEC 60076-7 umr soatini belgilamaydi (faqat nisbiy tezlik, 98/110 °C ga
  normallashtirilgan) — ishlab chiqaruvchi qiymati bo'lsa life_hours maydoniga kiriting.
  Chegaralar (IEC 60076-7 4-jadval, normal siklik yuk): θ_h ≤ 120 °C, θ_o ≤ 105 °C, K ≤ 1.5; uzoq muddatli favqulodda ≤ 140 °C.
Generator: S = P/cosφ, yuklanish S/S_nom, stator harorati ≈ θ_a + Δθ_nom·K² (I²R), reaktiv chegara.
"""

from __future__ import annotations

import math

from .schema import Field, Meta
from .validity import check_budget

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
        {"key": "loss_of_life_h", "label": "Umr sarfi (kuniga, nominal soat)", "unit": "soat"},
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
        "life_hours",
        "Nominal izolyatsiya umri L_nom",
        "soat",
        default=0,
        min=0,
        group="Transformator",
        hint="0 — qog'oz bo'yicha: yaxshilangan 180 000 (IEEE C57.91-2011, 110 °C), kraft 65 000 (95 °C)",
        advanced=True,
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


LIFE_HOURS = {"upgraded": 180000.0, "kraft": 65000.0}  # IEEE C57.91-2011 I-jadval / C57.91-1981


def run(p: dict) -> dict:
    x, y, dor, dhr, tau_o, tau_w, k11, k21, k22 = COOLING[p["cooling"]]
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
    check_budget(int(p["days"]) * n_day * 3, "Transformator", "kunlar sonini kamaytiring")
    # Boshlang'ich holat: birinchi soat yuki bilan statsionar (kunlar takrorlanib o'rnashadi)
    K0 = (prof[0] / cosphi) / S if S > 0 else 0.0
    theta_o = amb[0] + ((1 + R * K0**2) / (1 + R)) ** x * dor
    d_h1 = k21 * K0**y * dhr
    d_h2 = (k21 - 1) * K0**y * dhr
    ts, ko, th, to_, ks = [], [], [], [], []
    v_sum = 0.0
    for day in range(int(p["days"])):
        last = day == int(p["days"]) - 1
        for m in range(n_day):
            h = m // 60
            K = (prof[h] / cosphi) / S if S > 0 else 0.0
            ta = amb[h]
            # IEC 60076-7 §8.2.2 (10)–(12): har daqiqada K va θ_a doimiy — birinchi tartibli
            # tenglamalar aniq eksponensial qadam bilan integrallanadi (Eyler xatosi yo'q)
            o_target = ta + ((1 + R * K**2) / (1 + R)) ** x * dor
            theta_o += (o_target - theta_o) * (1 - math.exp(-dt / (k11 * tau_o)))
            d_h1 += (k21 * K**y * dhr - d_h1) * (1 - math.exp(-dt / (k22 * tau_w)))
            d_h2 += ((k21 - 1) * K**y * dhr - d_h2) * (1 - math.exp(-dt / (tau_o / k22)))
            theta_h = theta_o + d_h1 - d_h2
            if last:
                v_sum += aging_rate(theta_h, p["paper"]) * dt / 60
                if m % 15 == 0:
                    ts.append(round(m / 60, 2))
                    ko.append(round(K, 3))
                    th.append(round(theta_h, 1))
                    to_.append(round(theta_o, 1))
                    ks.append(round(prof[h], 2))
    hs_max, to_max, k_max = max(th), max(to_), max(ko)
    life_hours = p["life_hours"] or LIFE_HOURS[p["paper"]]
    aging_rel = v_sum / 24  # o'lchamsiz: kunlik o'rtacha nisbiy qarish tezligi
    life_years_at_this_load = (
        life_hours / v_sum / 365 if v_sum > 0 else None
    )  # yiliga 365·v_sum nominal soat sarflanadi
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
    if aging_rel > 2:
        problems.append(f"qarish nominaldan {aging_rel:.1f} marta tez")
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
            "aging_relative": round(aging_rel, 3),
            "loss_of_life_h": round(v_sum, 2),
            "life_hours_nominal": life_hours,
            "life_years_at_this_load": round(life_years_at_this_load, 1)
            if life_years_at_this_load
            else None,
            "gen_load_pct": gen["load_pct"] if gen else None,
            "verdict": "; ".join(problems)
            if problems
            else f"Normal: issiq nuqta {hs_max:.0f} °C, qarish {aging_rel:.2f}× nominal",
            "ok": not problems,
        },
    }
