"""Zilzila ta'siri: javob spektri, inshootlarning xususiy davri, seysmik koeffitsient, gidrodinamik bosim.

Seysmiklik → tezlanish (KMK 2.01.03 / SNiP II-7-81): 7 ball → A=0.1g, 8 → 0.2g, 9 → 0.4g.
Elastik javob spektri (Eurocode 8, 1-tur, so'nish ξ):
  0≤T≤T_B:  S_e = a_g·S·(1 + T/T_B·(2.5η − 1))
  T_B≤T≤T_C: S_e = a_g·S·2.5η
  T_C≤T≤T_D: S_e = a_g·S·2.5η·T_C/T
  T_D≤T≤4s:  S_e = a_g·S·2.5η·T_C·T_D/T²,   η = √(10/(5+ξ)) ≥ 0.55
Beton og'irlik to'g'onining xususiy davri (Chopra, 1978): T₁ = 0.38·H/√E  (H m, E MPa; bo'sh ombor),
to'la omborda T̃₁ ≈ T₁·R_r, R_r ≈ 1 + 0.25·(h/H)².
Mashina zali (EC8 4.3.3.2.2): T = C_t·H^0.75, C_t = 0.05.
Pseudo-statik seysmik koeffitsient — bitta norma yo'li, EN 1998-5:2004 §7.3.2.2:
  k_h = S·α/r,  α = a_g/g,  k_v = ±0.5·k_h (a_vg/a_g > 0.6) yoki ±0.33·k_h;
  r — 7.1-jadval: 1.0 (siljishi mumkin bo'lmagan inshoot — to'g'on), 1.5 / 2.0 (ruxsat etilgan
  siljish 200·α·S / 300·α·S mm bo'lgan erkin devorlar). Grunt sinfi S orqali natijaga kiradi.
  Ilgari ishlatilgan A·β·K₁ (SNiP II-7-81, K₁ = 0.25 — binolar normasining shikast koeffitsienti)
  EC8 elastik ordinatasi bilan aralashtirilgan edi va S qirqilib yo'qolardi — olib tashlandi.
  Muqobil: SP 358.1325800.2017 (gidrotexnik inshootlar, seysmik hududlar) — o'z β va K lari bilan,
  bu yerda amalga oshirilmagan. ICOLD Bulletin 148: dastlabki baholashda k_h = (0.5–0.67)·PGA (r ≈ 1.5–2).
Ikki kuch alohida nomlanadi: pseudo-statik F = k_h·W (barqarorlik hisobiga) va elastik spektral
  F_e = S_e(T)·m (dinamik tekshiruv uchun ordinata) — ular bitta kattalik emas.
Gidrodinamik bosim (Westergaard, 1933): p(y) = (7/8)·k_h·γ_w·√(H·y);  P_e = (7/12)·k_h·γ_w·H², 0.4H balandlikda.
"""

from __future__ import annotations

import math

from .penstock import RHO, G
from .schema import Field, Meta

GROUND = {  # EC8 1-tur: S, T_B, T_C, T_D
    "A": ("A — qoya (v_s > 800 m/s)", 1.00, 0.15, 0.40, 2.0),
    "B": ("B — zich qum/shag'al, qattiq gil", 1.20, 0.15, 0.50, 2.0),
    "C": ("C — o'rta zich qum, qattiq gil", 1.15, 0.20, 0.60, 2.0),
    "D": ("D — bo'sh qum, yumshoq gil", 1.35, 0.20, 0.80, 2.0),
    "E": ("E — yupqa yumshoq qatlam qoya ustida", 1.40, 0.15, 0.50, 2.0),
}
INTENSITY_PGA = {6: 0.05, 7: 0.10, 8: 0.20, 9: 0.40, 10: 0.80}


def pga_from_intensity(ball: int) -> float:
    return INTENSITY_PGA.get(int(ball), 0.1)


def spectrum(t: float, ag_g: float, ground: str, damping: float = 5.0) -> float:
    """Elastik javob spektri S_e(T), g birligida."""
    _, S, tb, tc, td = GROUND[ground]
    eta = max(math.sqrt(10 / (5 + damping)), 0.55)
    if t <= tb:
        return ag_g * S * (1 + t / tb * (2.5 * eta - 1))
    if t <= tc:
        return ag_g * S * 2.5 * eta
    if t <= td:
        return ag_g * S * 2.5 * eta * tc / t
    return ag_g * S * 2.5 * eta * tc * td / (t * t)


def dam_period(height_m: float, e_mpa: float, water_depth_m: float = 0.0) -> float:
    t1 = 0.38 * height_m / math.sqrt(max(e_mpa, 1.0))
    rr = 1 + 0.25 * (min(water_depth_m, height_m) / height_m) ** 2 if height_m > 0 else 1.0
    return t1 * rr


def seismic_coefficient(ag_g: float, S: float, r: float = 1.0) -> float:
    """EN 1998-5 §7.3.2.2 (7.1): k_h = S·α/r, α = a_g/g."""
    return S * ag_g / max(r, 1e-9)


def vertical_coefficient(kh: float, avg_ratio: float = 0.9) -> float:
    """EN 1998-5 §7.3.2.2 (7.2/7.3): k_v = ±0.5·k_h agar a_vg/a_g > 0.6, aks holda ±0.33·k_h."""
    return 0.5 * kh if avg_ratio > 0.6 else 0.33 * kh


def westergaard_force(kh: float, depth_m: float) -> tuple[float, float]:
    """(kuch N/m, ta'sir balandligi m) — birlik kenglik uchun."""
    return 7 / 12 * kh * RHO * G * depth_m**2, 0.4 * depth_m


META = Meta(
    id="seismic",
    title="Zilzila ta'siri",
    description="Seysmiklik (ball yoki PGA) va grunt turi bo'yicha javob spektri; to'g'on, mashina zali, "
    "quvur tayanchlari uchun xususiy davr, spektral tezlanish, seysmik kuch; Westergaard gidrodinamik bosim.",
    group="favqulodda",
    icon="earthquake",
    formulas=[
        "S_e(T) — Eurocode 8, 1-tur spektr",
        "T₁ = 0.38·H/√E (Chopra), T̃₁ = T₁·R_r",
        "k_h = A·β·K₁ (SNiP II-7-81)",
        "P_e = (7/12)·k_h·γ_w·H² (Westergaard)",
        "V = S_e(T)·m",
    ],
    viz={"color_by": "structures"},
    outputs=[
        {"key": "pga_g", "label": "Grunt tezlanishi", "unit": "g"},
        {"key": "kh", "label": "Seysmik koeffitsient k_h", "unit": ""},
        {"key": "dam_sa_g", "label": "To'g'on spektral tezlanishi", "unit": "g"},
        {"key": "westergaard_kn_m", "label": "Gidrodinamik kuch", "unit": "kN/m"},
    ],
)

FIELDS = [
    Field(
        "intensity",
        "Seysmiklik (MSK-64)",
        "ball",
        type="select",
        default="8",
        options=(("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"), ("10", "10")),
        group="Maydon",
        hint="KMK 2.01.03: 7→0.1g, 8→0.2g, 9→0.4g",
    ),
    Field(
        "pga_override_g",
        "PGA (ball o'rniga, 0 — ballga qarab)",
        "g",
        default=0,
        min=0,
        max=2,
        step=0.05,
        group="Maydon",
        advanced=True,
    ),
    Field(
        "ground",
        "Grunt turi (EC8)",
        type="select",
        default="B",
        options=tuple((k, v[0]) for k, v in GROUND.items()),
        group="Maydon",
    ),
    Field("damping", "So'nish ξ", "%", default=5, min=1, max=20, group="Maydon", advanced=True),
    Field(
        "r_reduction",
        "r — pseudo-statik kamaytirish (EC8-5 7.1-jadval)",
        "",
        default=1.0,
        min=1.0,
        max=2.0,
        step=0.5,
        group="Maydon",
        hint="1.0 — siljimaydigan inshoot (to'g'on); 1.5/2.0 — ruxsat etilgan siljishli erkin devor. "
        "ICOLD B148 dastlabki baho: (0.5–0.67)·PGA ≈ r 1.5–2",
        advanced=True,
    ),
    Field(
        "avg_ratio",
        "a_vg/a_g (vertikal/gorizontal PGA)",
        "",
        default=0.9,
        min=0.3,
        max=1.2,
        step=0.1,
        group="Maydon",
        hint="EC8-1 3.4-jadval: 1-tur 0.90; > 0.6 → k_v = 0.5·k_h, aks holda 0.33·k_h",
        advanced=True,
    ),
    Field(
        "dam_height_m",
        "To'g'on balandligi",
        "m",
        default=80,
        min=1,
        group="To'g'on",
        model="dam.height_m",
    ),
    Field(
        "dam_e_mpa",
        "Beton elastiklik moduli E",
        "MPa",
        default=25000,
        min=1000,
        group="To'g'on",
        advanced=True,
    ),
    Field(
        "water_depth_m",
        "Suv chuqurligi to'g'on oldida",
        "m",
        default=75,
        min=0,
        group="To'g'on",
        live="upstream_depth",
    ),
    Field(
        "dam_mass_t_m",
        "To'g'on massasi (1 m kenglikka)",
        "t/m",
        default=0,
        min=0,
        group="To'g'on",
        hint="0 — profil bo'yicha (uchburchak, 2400 kg/m³)",
        advanced=True,
    ),
    Field(
        "dam_base_m",
        "To'g'on tag kengligi",
        "m",
        default=64,
        min=1,
        group="To'g'on",
        model="dam.base_width_m",
    ),
    Field("ph_height_m", "Mashina zali balandligi", "m", default=30, min=1, group="Mashina zali"),
    Field("ph_mass_t", "Mashina zali massasi", "t", default=20000, min=1, group="Mashina zali"),
    Field(
        "penstock_period_s",
        "Quvur tayanch tizimi davri",
        "s",
        default=0.3,
        min=0.01,
        step=0.05,
        group="Quvur",
    ),
    Field(
        "penstock_mass_t",
        "Quvur + suv massasi (bir oraliq)",
        "t",
        default=400,
        min=1,
        group="Quvur",
    ),
]


def run(p: dict) -> dict:
    ag = p["pga_override_g"] if p["pga_override_g"] > 0 else pga_from_intensity(int(p["intensity"]))
    gr, xi = p["ground"], p["damping"]
    H, hw = p["dam_height_m"], min(p["water_depth_m"], p["dam_height_m"])
    t_dam = dam_period(H, p["dam_e_mpa"], hw)
    t_ph = 0.05 * p["ph_height_m"] ** 0.75
    t_pen = p["penstock_period_s"]
    sa_dam, sa_ph, sa_pen = (spectrum(t, ag, gr, xi) for t in (t_dam, t_ph, t_pen))
    S = GROUND[gr][1]
    beta = sa_dam / (ag * S)  # spektral kuchayish S_e/(a_g·S) — faqat ma'lumot uchun
    kh = seismic_coefficient(ag, S, p["r_reduction"])
    kv = vertical_coefficient(kh, p["avg_ratio"])
    m_dam = p["dam_mass_t_m"] if p["dam_mass_t_m"] > 0 else 0.5 * H * p["dam_base_m"] * 2.4  # t/m
    pe, ye = westergaard_force(kh, hw)
    warnings: list[str] = []
    if gr in ("C", "D", "E") and ag >= 0.2:
        warnings.append(
            f"grunt {gr} va a_g = {ag:.2f} g: EC8-1 §3.1.2(4) — maydonga xos tadqiqot (S va spektr) talab etiladi"
        )
    if p["r_reduction"] > 1.0:
        warnings.append(
            f"r = {p['r_reduction']:g}: k_h kamaytirilgan — faqat siljish ruxsat etilgan inshoot uchun (EC8-5 7.1-jadval)"
        )
    # Spektr egri chizig'i va Westergaard profil
    ts = [round(i * 0.02, 2) for i in range(0, 201)]
    se = [round(spectrum(t, ag, gr, xi), 4) for t in ts]
    ys = [round(hw * i / 20, 2) for i in range(21)]
    pw = [round(7 / 8 * kh * RHO * G * math.sqrt(hw * y) / 1000, 2) for y in ys]  # kPa
    structures = [
        {
            "name": "To'g'on — pseudo-statik k_h·W (barqarorlik)",
            "period_s": round(t_dam, 3),
            "sa_g": round(kh, 3),
            "mass_t": round(m_dam, 0),
            "force_kn": round(kh * G * m_dam, 0),
            "unit": "kN/m",
        },
        {
            "name": "To'g'on — elastik spektral S_e(T)·m (dinamik ordinata)",
            "period_s": round(t_dam, 3),
            "sa_g": round(sa_dam, 3),
            "mass_t": round(m_dam, 0),
            "force_kn": round(sa_dam * G * m_dam, 0),
            "unit": "kN/m",
        },
        {
            "name": "Mashina zali",
            "period_s": round(t_ph, 3),
            "sa_g": round(sa_ph, 3),
            "mass_t": p["ph_mass_t"],
            "force_kn": round(sa_ph * G * p["ph_mass_t"], 0),
            "unit": "kN",
        },
        {
            "name": "Bosimli quvur (tayanch)",
            "period_s": round(t_pen, 3),
            "sa_g": round(sa_pen, 3),
            "mass_t": p["penstock_mass_t"],
            "force_kn": round(sa_pen * G * p["penstock_mass_t"], 0),
            "unit": "kN",
        },
    ]
    level = "kuchli" if ag >= 0.4 else "o'rtacha" if ag >= 0.2 else "kuchsiz"
    return {
        "series": {"t": ts, "se_g": se},
        "profile": {"y": ys, "p_kpa": pw},
        "structures": structures,
        "summary": {
            "pga_g": round(ag, 3),
            "ground": GROUND[gr][0],
            "ground_class": gr,
            "soil_factor_S": S,
            "kh": round(kh, 3),
            "kv": round(kv, 3),
            "r_reduction": p["r_reduction"],
            "norm": "EN 1998-5:2004 §7.3.2.2 (k_h = S·α/r)",
            "dam_force_pseudostatic_kn_m": round(kh * G * m_dam, 0),
            "dam_force_elastic_kn_m": round(sa_dam * G * m_dam, 0),
            "beta": round(beta, 2),
            "dam_period_s": round(t_dam, 3),
            "dam_sa_g": round(sa_dam, 3),
            "powerhouse_sa_g": round(sa_ph, 3),
            "westergaard_kn_m": round(pe / 1000, 1),
            "westergaard_arm_m": round(ye, 2),
            "verdict": f"{level} zilzila ({ag:.2f} g, grunt {gr}, S = {S}); pseudo-statik k_h = {kh:.3f}, "
            f"k_v = ±{kv:.3f} (EC8-5 §7.3.2.2) — mustahkamlikni «To'g'on barqarorligi» da tekshiring",
            "ok": True,
            "warnings": warnings,
        },
    }
