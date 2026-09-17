"""Tog' ko'chishi (yonbag'ir surilishi) suv omboriga tushganda hosil bo'ladigan impuls to'lqin.

Manba: Heller, Hager & Minor (2009), "Landslide generated impulse waves in reservoirs — Basics and
computation", VAW Mitteilung 211 (ETH Zürich); Heller & Hager (2010), J. Hydraul. Eng. 136(3).
  Ko'chki tezligi:      v_s = √(2·g·Δz·(1 − tgδ / tgα))
  Frud soni             F = v_s/√(g·h);  S = s/h;  M = m_s/(ρ_w·b·h²)
  Impuls parametri      P = F·S^½·M^¼·[cos(6α/7)]^½          (amal doirasi 0.17 ≤ P ≤ 8.1)
  Maksimal amplituda    a_M = (4/9)·P^(4/5)·h,  H_M = (5/9)·P^(4/5)·h,  x_M = 5.5·P^½·h,  T_M = 9·P^½·√(h/g)
  Tarqalish, 2D (kanal) a(x) = (3/5)·(P·X^(−1/3))^(4/5)·h,  X = x/h
  Tarqalish, 3D (ko'l)  a(r,γ) = (3/2)·P^(4/5)·cos²(2γ/3)·(r/h)^(−2/3)·h
  To'g'onga chiqish     R = 1.25·h·(H/h)^(5/4)·(H/L)^(−3/20)·(90°/β)^(1/5)   (Müller 1995)
  Gerbdan oshish        R > f (f — gerbgacha zaxira) bo'lsa; hajm ≈ 0.6·1.7·(R−f)^1.5·T/2 (baholash)
"""

from __future__ import annotations

import math

from .penstock import RHO, G
from .schema import Field, Meta

META = Meta(
    id="landslide",
    title="Tog' ko'chishi → impuls to'lqin",
    description="Yonbag'ir surilishi omborga tushganda to'lqin balandligi, to'g'ongacha tarqalishi, to'g'on yuzasiga "
    "chiqish balandligi va gerbdan oshish xavfi (Heller–Hager usuli, ETH Zürich).",
    group="favqulodda",
    icon="mountain",
    formulas=[
        "P = F·S^½·M^¼·[cos(6α/7)]^½",
        "a_M = (4/9)·P^0.8·h",
        "a(r,γ) = 1.5·P^0.8·cos²(2γ/3)·(r/h)^−⅔·h",
        "R = 1.25·h·(H/h)^1.25·(H/L)^−0.15·(90°/β)^0.2",
    ],
    viz={"water_level": "runup_level_m"},
    outputs=[
        {"key": "a_max_m", "label": "Maks. amplituda (hosil bo'lish joyida)", "unit": "m"},
        {"key": "h_at_dam_m", "label": "To'lqin balandligi to'g'onda", "unit": "m"},
        {"key": "runup_m", "label": "To'g'onga chiqish R", "unit": "m"},
        {"key": "overtop_m", "label": "Gerbdan oshish", "unit": "m"},
    ],
)

FIELDS = [
    Field("volume_m3", "Ko'chki hajmi V_s", "m³", default=500000, min=100, group="Ko'chki"),
    Field("thickness_m", "Ko'chki qalinligi s", "m", default=15, min=0.5, group="Ko'chki"),
    Field("width_m", "Ko'chki kengligi b", "m", default=150, min=1, group="Ko'chki"),
    Field(
        "density_kg_m3",
        "Ko'chki zichligi ρ_s",
        "kg/m³",
        default=2200,
        min=1000,
        max=3000,
        group="Ko'chki",
        hint="qoya 2500–2700, tuproq 1800–2200",
    ),
    Field(
        "drop_m", "Og'irlik markazi tushish balandligi Δz", "m", default=120, min=1, group="Ko'chki"
    ),
    Field("slope_deg", "Yonbag'ir qiyaligi α", "°", default=35, min=10, max=85, group="Ko'chki"),
    Field(
        "friction_deg",
        "Dinamik ishqalanish burchagi δ",
        "°",
        default=20,
        min=5,
        max=45,
        group="Ko'chki",
        hint="Δz ni to'g'ridan-to'g'ri tezlikka aylantirish uchun",
    ),
    Field(
        "velocity_override",
        "Tushish tezligi (0 — formula bo'yicha)",
        "m/s",
        default=0,
        min=0,
        group="Ko'chki",
        advanced=True,
    ),
    Field(
        "depth_m",
        "Suv chuqurligi tushish joyida h",
        "m",
        default=60,
        min=1,
        group="Ombor",
        live="upstream_depth",
    ),
    Field("distance_m", "Tushish joyidan to'g'ongacha r", "m", default=1500, min=1, group="Ombor"),
    Field(
        "angle_deg",
        "To'lqin yo'nalishi burchagi γ (ko'chki o'qidan)",
        "°",
        default=0,
        min=0,
        max=90,
        group="Ombor",
        hint="0 — to'g'on ko'chki o'qida",
    ),
    Field(
        "geometry",
        "Ombor shakli",
        type="select",
        default="3d",
        options=(("3d", "Keng ko'l (3D radial tarqalish)"), ("2d", "Tor kanal/dara (2D)")),
        group="Ombor",
    ),
    Field(
        "freeboard_m",
        "Gerbgacha zaxira f (sathdan gerbgacha)",
        "m",
        default=7,
        min=0,
        group="To'g'on",
        live="freeboard",
    ),
    Field(
        "dam_face_deg",
        "To'g'on yuqori yuzasi burchagi β",
        "°",
        default=90,
        min=10,
        max=90,
        group="To'g'on",
        hint="90 — vertikal (beton); 30–40 — tuproq to'g'on",
    ),
    Field(
        "water_level_m",
        "Joriy sath (3D ko'rsatish uchun)",
        "m",
        default=0,
        group="To'g'on",
        live="upstream_level",
        advanced=True,
    ),
]


def run(p: dict) -> dict:
    h = p["depth_m"]
    alpha = math.radians(p["slope_deg"])
    delta = math.radians(p["friction_deg"])
    if p["velocity_override"] > 0:
        vs = p["velocity_override"]
    else:
        k = 1 - math.tan(delta) / math.tan(alpha)
        if k <= 0:
            raise ValueError(
                "Ishqalanish burchagi yonbag'ir qiyaligidan katta — ko'chki harakatlanmaydi"
            )
        vs = math.sqrt(2 * G * p["drop_m"] * k)
    ms = p["density_kg_m3"] * p["volume_m3"]
    F = vs / math.sqrt(G * h)
    S = p["thickness_m"] / h
    M = ms / (RHO * p["width_m"] * h**2)
    P = F * math.sqrt(S) * M**0.25 * math.sqrt(max(math.cos(6 / 7 * alpha), 0.05))
    a_max = 4 / 9 * P**0.8 * h
    h_max = 5 / 9 * P**0.8 * h
    x_max = 5.5 * math.sqrt(P) * h
    r = p["distance_m"]
    gamma = math.radians(p["angle_deg"])

    def amp(dist: float) -> float:
        if dist <= x_max:
            return a_max
        if p["geometry"] == "2d":
            return 3 / 5 * (P * (dist / h) ** (-1 / 3)) ** 0.8 * h
        return min(1.5 * P**0.8 * math.cos(2 * gamma / 3) ** 2 * (dist / h) ** (-2 / 3) * h, a_max)

    a_dam = amp(r)
    H_dam = a_dam / 0.8
    T = 9 * math.sqrt(P) * (max(r / h, 1.0)) ** 0.25 * math.sqrt(h / G)
    c = math.sqrt(G * (h + a_dam))
    L = c * T
    beta = p["dam_face_deg"]
    R = 1.25 * h * (H_dam / h) ** 1.25 * (H_dam / L) ** (-0.15) * (90 / beta) ** 0.2
    f = p["freeboard_m"]
    overtop = max(R - f, 0.0)
    vol = 0.6 * 1.7 * overtop**1.5 * T / 2 if overtop > 0 else 0.0  # m³ / m gerb uzunligi
    force_static = RHO * G * h**2 / 2 / 1000  # kN/m
    force_wave = (
        RHO * G * (h + R) ** 2 / 2 / 1000 if beta >= 89 else RHO * G * (h + a_dam) ** 2 / 2 / 1000
    )
    dists = (
        [round(x_max + (r * 1.5 - x_max) * i / 40, 1) for i in range(41)]
        if r * 1.5 > x_max
        else [round(r * i / 40, 1) for i in range(41)]
    )
    amps = [round(amp(d), 3) for d in dists]
    arrival = r / c
    warn = []
    if not (0.17 <= P <= 8.13):
        warn.append(f"P = {P:.2f} usul amal doirasidan tashqarida (0.17–8.13) — natija taxminiy")
    if overtop > 0:
        warn.append(f"to'lqin gerbdan {overtop:.1f} m oshadi (≈ {vol:.0f} m³/m)")
    elif R > 0.8 * f:
        warn.append("chiqish balandligi zaxiraga yaqin")
    lvl = p["water_level_m"]
    return {
        "series": {"x": dists, "amplitude": amps},
        "summary": {
            "slide_velocity_ms": round(vs, 1),
            "slide_mass_t": round(ms / 1000, 0),
            "froude": round(F, 3),
            "impulse_product_P": round(P, 3),
            "a_max_m": round(a_max, 2),
            "h_max_m": round(h_max, 2),
            "x_max_m": round(x_max, 0),
            "period_s": round(T, 1),
            "wavelength_m": round(L, 0),
            "a_at_dam_m": round(a_dam, 2),
            "h_at_dam_m": round(H_dam, 2),
            "arrival_s": round(arrival, 0),
            "runup_m": round(R, 2),
            "overtop_m": round(overtop, 2),
            "overtop_volume_m3_m": round(vol, 1),
            "force_static_kn_m": round(force_static, 0),
            "force_wave_kn_m": round(force_wave, 0),
            "runup_level_m": round(lvl + R, 2) if lvl else None,
            "verdict": "; ".join(warn)
            if warn
            else f"To'lqin {R:.1f} m ga chiqadi, gerbdan oshmaydi (zaxira {f} m)",
            "ok": overtop <= 0,
        },
    }
