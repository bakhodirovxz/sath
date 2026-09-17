"""Filtratsiya (suv sizishi) va suffoziya (piping) tekshiruvi.

Beton to'g'on — o'tkazuvchan asos (Darsi, filtratsiya to'ri):  q = k·H·N_f/N_d  (1 m kenglikka)
Lane (1935) og'irlangan yo'l:  C_w = (ΣL_v + ΣL_h/3)/H ≥ [C_w] (mayda qum 8.5; o'rta qum 6; shag'al 4; gil 1.8–3)
Xosla (Khosla, 1936) chiqish gradiyenti:  G_E = (H/d)·1/(π√λ),  λ = (1+√(1+α²))/2,  α = b/d,  d — shpunt chuqurligi
  Xavfsiz: G_E ≤ 1/5…1/7 (mayda qum), 1/4…1/5 (qo'pol qum), 1/3…1/4 (shag'al)
Tuproq to'g'on (bir jinsli, Dyupyui):  q = k·(h₁² − h₂²)/(2L),  depressiya egri chizig'i — parabola;
  chiqish gradiyenti i_exit ≈ Δh/L_d (chiqish zonasida),  kritik  i_cr = (G_s − 1)/(1 + e),  K_suffoz = i_cr/i_exit ≥ 1.5–2.
"""

from __future__ import annotations

import math

from .schema import Field, Meta

SOILS = {
    "fine_sand": ("Mayda qum", 8.5, 1 / 6),
    "medium_sand": ("O'rta qum", 6.0, 1 / 5),
    "coarse_sand": ("Qo'pol qum", 5.0, 1 / 4.5),
    "gravel": ("Shag'al", 4.0, 1 / 3.5),
    "clay": ("Gil (o'rta)", 2.0, 1 / 3),
    # qoya asos (beton to'g'on): Lane mezoni shartli — yoriqli qoya uchun sementatsiya pardasi hisobga olinadi,
    # C_w ≈ 1.8 (USBR amaliyoti, yoriqli qoya ≈ zich gil), xavfsiz gradiyent 0.4
    "rock": ("Qoya (yoriqli, sementatsiya bilan)", 1.8, 0.4),
}

META = Meta(
    id="seepage",
    title="Filtratsiya va suffoziya (piping)",
    description="To'g'on tagidan/tanasidan suv sizishi: Darsi sarfi, Lane yo'l koeffitsienti, Xosla chiqish "
    "gradiyenti (beton to'g'on) yoki Dyupyui depressiya egri chizig'i (tuproq to'g'on) va suffoziya zaxirasi.",
    group="mustahkamlik",
    icon="droplet",
    formulas=[
        "q = k·H·N_f/N_d",
        "C_w = (ΣL_v + ΣL_h/3)/H",
        "G_E = (H/d)/(π√λ)",
        "q = k(h₁²−h₂²)/(2L)",
    ],
    viz={"water_level": None},
    outputs=[
        {"key": "q_l_s_m", "label": "Sizish sarfi", "unit": "l/s/m"},
        {"key": "exit_gradient", "label": "Chiqish gradiyenti", "unit": ""},
        {"key": "fs_piping", "label": "Suffoziya zaxirasi", "unit": ""},
    ],
)

FIELDS = [
    Field(
        "dam_type",
        "To'g'on turi",
        type="select",
        default="concrete",
        options=(("concrete", "Beton (o'tkazuvchan asosda)"), ("earth", "Tuproq (bir jinsli)")),
        group="Umumiy",
    ),
    Field(
        "head_m",
        "Napor H (byeflar farqi)",
        "m",
        default=60,
        min=0.1,
        group="Umumiy",
        live="gross_head",
    ),
    Field(
        "k_m_s",
        "Filtratsiya koeffitsienti k",
        "m/s",
        default=1e-5,
        min=1e-12,
        step=1e-6,
        group="Umumiy",
        hint="qum 1e-4…1e-3; alevrit 1e-6; gil 1e-9",
    ),
    Field(
        "soil",
        "Asos grunti",
        type="select",
        default="gravel",
        options=tuple((k, v[0]) for k, v in SOILS.items()),
        group="Umumiy",
    ),
    Field(
        "base_width_m",
        "Tag kengligi b (gorizontal yo'l)",
        "m",
        default=64,
        min=1,
        group="Beton to'g'on",
        model="dam.base_width_m",
    ),
    Field("cutoff_m", "Shpunt/parda chuqurligi d", "m", default=12, min=0.1, group="Beton to'g'on"),
    Field(
        "apron_m",
        "Ponur + risberma uzunligi (gorizontal)",
        "m",
        default=40,
        min=0,
        group="Beton to'g'on",
    ),
    Field(
        "extra_vertical_m",
        "Qo'shimcha vertikal yo'llar (ΣL_v)",
        "m",
        default=0,
        min=0,
        group="Beton to'g'on",
        advanced=True,
    ),
    Field(
        "nf",
        "Oqim chiziqlari N_f",
        "",
        type="int",
        default=4,
        min=1,
        group="Beton to'g'on",
        advanced=True,
    ),
    Field(
        "nd",
        "Ekvipotensial tushishlar N_d",
        "",
        type="int",
        default=12,
        min=1,
        group="Beton to'g'on",
        advanced=True,
    ),
    Field(
        "dam_length_m",
        "To'g'on uzunligi (jami sarf uchun)",
        "m",
        default=300,
        min=1,
        group="Beton to'g'on",
        model="dam.length_m",
    ),
    Field(
        "h1_m", "Yuqori byef suv chuqurligi h₁", "m", default=60, min=0.1, group="Tuproq to'g'on"
    ),
    Field("h2_m", "Quyi byef chuqurligi h₂", "m", default=3, min=0, group="Tuproq to'g'on"),
    Field(
        "seep_length_m",
        "Sizish yo'li L (tana bo'ylab)",
        "m",
        default=250,
        min=1,
        group="Tuproq to'g'on",
    ),
    Field(
        "drain_length_m",
        "Drenaj/chiqish zonasi uzunligi",
        "m",
        default=30,
        min=0.5,
        group="Tuproq to'g'on",
    ),
    Field(
        "gs",
        "Zarrachalar zichligi G_s",
        "",
        default=2.65,
        min=2,
        max=3,
        step=0.01,
        group="Tuproq to'g'on",
        advanced=True,
    ),
    Field(
        "void_ratio",
        "G'ovaklik koeffitsienti e",
        "",
        default=0.7,
        min=0.2,
        max=1.5,
        step=0.05,
        group="Tuproq to'g'on",
        advanced=True,
    ),
]


def run(p: dict) -> dict:
    H, k = p["head_m"], p["k_m_s"]
    soil_name, cw_req, ge_safe = SOILS[p["soil"]]
    if p["dam_type"] == "concrete":
        b, d = p["base_width_m"], p["cutoff_m"]
        q = k * H * p["nf"] / p["nd"]  # m³/s / m
        lv = 2 * d + p["extra_vertical_m"]
        cw = (lv + (b + p["apron_m"]) / 3) / H
        alpha = b / d
        lam = (1 + math.sqrt(1 + alpha**2)) / 2
        ge = (H / d) / (math.pi * math.sqrt(lam))
        fs = ge_safe / ge if ge > 0 else 99.0
        probs = []
        if cw < cw_req:
            probs.append(
                f"Lane koeffitsienti {cw:.1f} < {cw_req} ({soil_name}) — yo'lni uzaytiring (shpunt, ponur)"
            )
        if ge > ge_safe:
            probs.append(f"chiqish gradiyenti {ge:.3f} > xavfsiz {ge_safe:.3f} — suffoziya xavfi")
        # Shpunt chuqurligi bo'yicha skanerlash
        ds = [round(0.5 + 30 * i / 40, 2) for i in range(41)]
        ges = []
        for dd in ds:
            al = b / dd
            la = (1 + math.sqrt(1 + al**2)) / 2
            ges.append(round((H / dd) / (math.pi * math.sqrt(la)), 4))
        return {
            "series": {"cutoff_m": ds, "exit_gradient": ges},
            "summary": {
                "q_l_s_m": round(q * 1000, 3),
                "q_total_l_s": round(q * 1000 * p["dam_length_m"], 1),
                "lane_cw": round(cw, 2),
                "lane_required": cw_req,
                "exit_gradient": round(ge, 4),
                "exit_gradient_safe": round(ge_safe, 3),
                "fs_piping": round(fs, 2),
                "verdict": "; ".join(probs)
                if probs
                else "Filtratsiya xavfsiz (Lane va Xosla mezonlari bajarildi)",
                "ok": not probs,
            },
        }
    h1, h2, L = p["h1_m"], p["h2_m"], p["seep_length_m"]
    q = k * (h1**2 - h2**2) / (2 * L)
    xs = [round(L * i / 40, 2) for i in range(41)]
    # Dyupyui parabola: h(x)² = h₁² − (h₁² − h₂²)·x/L
    ys = [round(math.sqrt(max(h1**2 - (h1**2 - h2**2) * x / L, 0.0)), 3) for x in xs]
    # Chiqish gradiyenti — depressiya chizig'ining oxirgi L_d (chiqish zonasi) bo'ylab o'rtacha nishabi
    ld = min(p["drain_length_m"], L)
    h_ld = math.sqrt(max(h1**2 - (h1**2 - h2**2) * (L - ld) / L, 0.0))
    i_exit = (h_ld - h2) / ld
    i_cr = (p["gs"] - 1) / (1 + p["void_ratio"])
    fs = i_cr / i_exit if i_exit > 0 else 99.0
    probs = []
    if fs < 1.5:
        probs.append(f"suffoziya zaxirasi {fs:.2f} < 1.5 — drenaj/filtr kerak")
    return {
        "series": {"x": xs, "phreatic": ys},
        "summary": {
            "q_l_s_m": round(q * 1000, 3),
            "q_total_l_s": round(q * 1000 * p["dam_length_m"], 1),
            "exit_gradient": round(i_exit, 4),
            "critical_gradient": round(i_cr, 3),
            "fs_piping": round(fs, 2),
            "verdict": "; ".join(probs)
            if probs
            else "Depressiya egri chizig'i va suffoziya zaxirasi qoniqarli",
            "ok": not probs,
        },
    }
