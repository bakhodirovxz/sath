"""Suv toshqini: toshqin to'lqinini suv ombori orqali o'tkazish (level-pool), gerbdan oshish, to'g'on yorilishi,
quyi byefda to'lqinning tarqalishi (Muskingum) va suv chuqurligi (Manning).

Toshqin gidrografi (sintetik, SCS gamma shakli):  Q(t) = Q_p·(t/t_p)^m·exp(m·(1 − t/t_p)),  m = 3.7
Ombor balansi (Puls):  S(t+Δt) = S(t) + (Ī − Ō)·Δt,  sath = f(S) batimetriya bo'yicha
Suv tashlagich (ogee):  Q = m·b·√(2g)·H^1.5  (m — sarf koeff., 0.49), darvoza ochiqligi bilan
Tubi suv chiqargich (orifice): Q = μ·A·√(2g·H)
Gerbdan oshish (keng ostonali):  Q = 1.7·L_crest·h^1.5
Yorilish (Froehlich 2008):  B_avg = 0.27·k₀·V_w^0.32·h_b^0.04,  t_f = 63.2·√(V_w/(g·h_b²)),  k₀ = 1.3 (oshib o'tish) / 1.0 (piping)
Yorilish maksimal sarfi (Froehlich 1995):  Q_p = 0.607·V_w^0.295·h_w^1.24
Muskingum:  O₂ = C₀I₂ + C₁I₁ + C₂O₁,  K, X har oraliq uchun
Manning normal chuqurlik:  Q = (1/n)·A·R^(2/3)·√S₀  (trapetsiya kesim), Nyuton usuli bilan yechiladi
"""

from __future__ import annotations

import math

from .penstock import G
from .reservoir import StorageCurve
from .schema import Field, Meta

META = Meta(
    id="flood",
    title="Suv toshqini (ombor, gerbdan oshish, yorilish)",
    description="Loyihaviy toshqin ombor orqali o'tkaziladi: maksimal sath, zaxira balandligi, gerbdan oshish; "
    "yorilish ssenariysi (Froehlich) va quyi byefdagi to'lqin (Muskingum) hamda suv chuqurligi (Manning).",
    group="favqulodda",
    icon="flood",
    formulas=[
        "S(t+Δt) = S(t) + (Ī − Ō)·Δt",
        "Q_spill = m·b·√(2g)·H^1.5",
        "Q_over = 1.7·L·h^1.5",
        "Q_p = 0.607·V_w^0.295·h_w^1.24 (Froehlich)",
        "O₂ = C₀I₂ + C₁I₁ + C₂O₁ (Muskingum)",
        "Q = (1/n)·A·R^(2/3)·√S₀ (Manning)",
    ],
    viz={"water_level": "level", "downstream_depth": "depth_ds"},
    outputs=[
        {"key": "max_level_m", "label": "Maksimal sath", "unit": "m"},
        {"key": "freeboard_m", "label": "Qolgan zaxira (gerbgacha)", "unit": "m"},
        {"key": "peak_outflow_m3s", "label": "Maksimal chiqim", "unit": "m³/s"},
        {"key": "breach_peak_m3s", "label": "Yorilish maks. sarfi", "unit": "m³/s"},
    ],
)

FIELDS = [
    Field(
        "peak_m3s",
        "Toshqin cho'qqisi Q_p",
        "m³/s",
        default=2500,
        min=1,
        group="Toshqin",
        hint="Loyihaviy (0.1 %) yoki tekshiruv (0.01 %) toshqin",
    ),
    Field("time_to_peak_h", "Cho'qqigacha vaqt t_p", "soat", default=18, min=0.5, group="Toshqin"),
    Field("duration_h", "Umumiy davomiylik", "soat", default=96, min=1, group="Toshqin"),
    Field("base_m3s", "Bazaviy sarf", "m³/s", default=100, min=0, group="Toshqin", live="inflow"),
    Field(
        "inflow_series",
        "yoki gidrograf qiymatlari (m³/s, har soat; bo'sh — sintetik)",
        type="series",
        default=[],
        group="Toshqin",
        advanced=True,
    ),
    Field(
        "curve_elev",
        "Sath–hajm: sathlar",
        "m",
        type="series",
        default=[850, 870, 890, 905, 915],
        group="Ombor",
        model="reservoir.curve_elev",
    ),
    Field(
        "curve_vol",
        "Sath–hajm: hajmlar",
        "mln m³",
        type="series",
        default=[0, 60, 220, 480, 700],
        group="Ombor",
        model="reservoir.curve_vol",
    ),
    Field(
        "initial_level_m",
        "Boshlang'ich sath",
        "m",
        default=905,
        group="Ombor",
        live="upstream_level",
    ),
    Field(
        "crest_m",
        "To'g'on gerbi belgisi",
        "m",
        default=912,
        group="Ombor",
        model="dam.crest_elevation_m",
    ),
    Field(
        "crest_length_m",
        "Gerb uzunligi (oshib o'tish uchun)",
        "m",
        default=300,
        min=1,
        group="Ombor",
        model="dam.length_m",
    ),
    Field(
        "spill_crest_m",
        "Suv tashlagich ostonasi",
        "m",
        default=905,
        group="Suv tashlagich",
        model="spillway.crest_m",
    ),
    Field(
        "spill_width_m",
        "Suv tashlagich kengligi",
        "m",
        default=40,
        min=0,
        group="Suv tashlagich",
        model="spillway.width_m",
    ),
    Field(
        "spill_coeff",
        "Sarf koeffitsienti m",
        "",
        default=0.49,
        min=0.3,
        max=0.6,
        step=0.01,
        group="Suv tashlagich",
    ),
    Field(
        "gate_opening",
        "Darvozalar ochiqligi",
        "0–1",
        default=1.0,
        min=0,
        max=1,
        step=0.1,
        group="Suv tashlagich",
        hint="0 — darvoza ochilmadi (avariya ssenariysi)",
    ),
    Field(
        "outlet_area_m2",
        "Tubi suv chiqargich yuzasi",
        "m²",
        default=0,
        min=0,
        group="Suv tashlagich",
        hint="0 — yo'q",
    ),
    Field(
        "outlet_sill_m",
        "Tubi suv chiqargich o'qi belgisi",
        "m",
        default=860,
        group="Suv tashlagich",
        advanced=True,
    ),
    Field(
        "turbine_m3s",
        "Turbinalar sarfi (doimiy)",
        "m³/s",
        default=150,
        min=0,
        group="Suv tashlagich",
        live="penstock_flow",
    ),
    Field(
        "breach",
        "Yorilish ssenariysi",
        type="select",
        default="auto",
        options=(
            ("none", "Hisoblanmasin"),
            ("auto", "Gerbdan oshsa — yorilish"),
            ("force", "Majburan (piping)"),
        ),
        group="Yorilish",
    ),
    Field("breach_bottom_m", "Yorilish tubi belgisi", "m", default=850, group="Yorilish"),
    Field(
        "reach_length_km",
        "Quyi byef oralig'i uzunligi",
        "km",
        default=20,
        min=0.1,
        group="Quyi byef",
    ),
    Field(
        "reach_count",
        "Oraliqlar soni (Muskingum)",
        "",
        type="int",
        default=4,
        min=1,
        max=20,
        group="Quyi byef",
        advanced=True,
    ),
    Field(
        "wave_speed_ms",
        "To'lqin tezligi c (K = L/c)",
        "m/s",
        default=3.0,
        min=0.2,
        step=0.1,
        group="Quyi byef",
    ),
    Field(
        "musk_x",
        "Muskingum X",
        "",
        default=0.2,
        min=0,
        max=0.5,
        step=0.05,
        group="Quyi byef",
        advanced=True,
    ),
    Field("ch_width_m", "Daryo o'zani tubi kengligi", "m", default=80, min=1, group="Quyi byef"),
    Field(
        "ch_side_slope", "Qirg'oq qiyaligi (gor./vert.)", "", default=3.0, min=0, group="Quyi byef"
    ),
    Field(
        "ch_slope",
        "O'zan nishabi S₀",
        "",
        default=0.002,
        min=0.00001,
        step=0.0005,
        group="Quyi byef",
    ),
    Field(
        "ch_manning",
        "Manning n",
        "",
        default=0.035,
        min=0.01,
        max=0.2,
        step=0.005,
        group="Quyi byef",
    ),
    Field(
        "ch_bank_depth_m",
        "Qirg'oq balandligi (toshqin boshlanadi)",
        "m",
        default=5,
        min=0.1,
        group="Quyi byef",
    ),
    Field(
        "dt_min", "Hisob qadami", "min", default=15, min=1, max=60, group="Quyi byef", advanced=True
    ),
]


def synthetic_hydrograph(
    qp: float, tp_h: float, base: float, n: int, dt_h: float, m: float = 3.7
) -> list[float]:
    out = []
    for i in range(n):
        t = i * dt_h
        x = t / tp_h
        out.append(base + (qp - base) * (x**m) * math.exp(m * (1 - x)) if x > 0 else base)
    return out


def manning_depth(q: float, b: float, z: float, s0: float, n: float) -> float:
    """Trapetsiya o'zanda normal chuqurlik (Nyuton)."""
    if q <= 0:
        return 0.0
    y = max((q * n / (b * math.sqrt(s0))) ** 0.6, 0.05)
    for _ in range(60):
        a = (b + z * y) * y
        pw = b + 2 * y * math.sqrt(1 + z * z)
        r = a / pw
        f = a * r ** (2 / 3) * math.sqrt(s0) / n - q
        dy = 1e-4 * max(y, 1.0)
        a2 = (b + z * (y + dy)) * (y + dy)
        p2 = b + 2 * (y + dy) * math.sqrt(1 + z * z)
        f2 = a2 * (a2 / p2) ** (2 / 3) * math.sqrt(s0) / n - q
        d = (f2 - f) / dy
        if abs(d) < 1e-12:
            break
        y_new = y - f / d
        if y_new <= 0:
            y_new = y / 2
        if abs(y_new - y) < 1e-6:
            y = y_new
            break
        y = y_new
    return y


def muskingum(inflow: list[float], k_s: float, x: float, dt_s: float) -> list[float]:
    den = 2 * k_s * (1 - x) + dt_s
    c0 = (dt_s - 2 * k_s * x) / den
    c1 = (dt_s + 2 * k_s * x) / den
    c2 = (2 * k_s * (1 - x) - dt_s) / den
    out = [inflow[0]]
    for i in range(1, len(inflow)):
        out.append(max(c0 * inflow[i] + c1 * inflow[i - 1] + c2 * out[-1], 0.0))
    return out


def run(p: dict) -> dict:
    dt = p["dt_min"] * 60
    dt_h = dt / 3600
    curve = StorageCurve(tuple(p["curve_elev"]), tuple(p["curve_vol"]))
    if p["inflow_series"]:
        hourly = p["inflow_series"]
        n = int((len(hourly) - 1) / dt_h) + 1
        inflow = [float(_interp(hourly, i * dt_h)) for i in range(n)]
    else:
        n = int(p["duration_h"] / dt_h) + 1
        inflow = synthetic_hydrograph(p["peak_m3s"], p["time_to_peak_h"], p["base_m3s"], n, dt_h)
    crest, lcrest = p["crest_m"], p["crest_length_m"]
    sc, sb, sm, gate = p["spill_crest_m"], p["spill_width_m"], p["spill_coeff"], p["gate_opening"]
    qt = p["turbine_m3s"]

    def outflow(level: float) -> tuple[float, float, float, float]:
        h = max(level - sc, 0.0)
        spill = sm * sb * math.sqrt(2 * G) * h**1.5 * gate if sb > 0 else 0.0
        ho = max(level - p["outlet_sill_m"], 0.0)
        outlet = (
            0.6 * p["outlet_area_m2"] * math.sqrt(2 * G * ho) if p["outlet_area_m2"] > 0 else 0.0
        )
        over = 1.7 * lcrest * max(level - crest, 0.0) ** 1.5
        return spill, outlet, over, spill + outlet + over + qt

    level = p["initial_level_m"]
    S = curve.volume(level)
    ts, levels, outs, spills, overs = [], [], [], [], []
    over_start = None
    for i in range(n):
        q_in = inflow[i]
        q_in_next = inflow[min(i + 1, n - 1)]
        # Yarim qadam iteratsiya (Puls): O sath funksiyasi, 3 marta takrorlash yetarli
        o1 = outflow(level)[3]
        lv = level
        for _ in range(3):
            o2 = outflow(lv)[3]
            s_next = S + ((q_in + q_in_next) / 2 - (o1 + o2) / 2) * dt
            lv = curve.elevation(max(s_next, 0.0))
        sp, ou, ov, o = outflow(lv)
        ts.append(round(i * dt_h, 3))
        levels.append(round(lv, 3))
        outs.append(round(o, 2))
        spills.append(round(sp, 2))
        overs.append(round(ov, 2))
        if ov > 0 and over_start is None:
            over_start = i * dt_h
        S, level = max(s_next, 0.0), lv

    max_level = max(levels)
    i_max = levels.index(max_level)
    peak_in = max(inflow)
    peak_out = max(outs)
    freeboard = crest - max_level
    overtopped = freeboard < 0

    # Yorilish
    mode = p["breach"]
    breach = None
    do_breach = mode == "force" or (mode == "auto" and overtopped)
    if do_breach:
        hb = max(max_level - p["breach_bottom_m"], 1.0)  # yorilish balandligi
        vw = max(curve.volume(max_level) - curve.volume(p["breach_bottom_m"]), 1.0)  # m³
        k0 = 1.3 if mode == "auto" else 1.0
        b_avg = 0.27 * k0 * vw**0.32 * hb**0.04
        tf = 63.2 * math.sqrt(vw / (G * hb**2))  # s
        qp = 0.607 * vw**0.295 * hb**1.24
        # Uchburchak gidrograf: cho'qqi t_f da, hajm V_w → davomiyligi T = 2V_w/Q_p
        t_total = 2 * vw / qp
        n_b = int(t_total / dt) + 2
        bh = [
            max(qp * (t / tf) if t <= tf else qp * (1 - (t - tf) / (t_total - tf)), 0.0)
            for t in (k * dt for k in range(n_b))
        ]
        breach = {
            "width_m": round(b_avg, 1),
            "height_m": round(hb, 1),
            "volume_mcm": round(vw / 1e6, 2),
            "formation_h": round(tf / 3600, 2),
            "peak_m3s": round(qp, 0),
            "duration_h": round(t_total / 3600, 1),
            "hydrograph": [round(v, 1) for v in bh],
        }

    # Quyi byef: yorilish bo'lsa yorilish gidrografi (+ bazaviy), bo'lmasa ombor chiqimi
    ds_in = [b + p["base_m3s"] for b in breach["hydrograph"]] if breach else outs
    seg = p["reach_length_km"] * 1000 / p["reach_count"]
    k_s = seg / p["wave_speed_ms"]
    x = p["musk_x"]
    # Barqarorlik: dt >= 2KX; kerak bo'lsa X ni kamaytiramiz
    if dt < 2 * k_s * x:
        x = max(dt / (2 * k_s) * 0.9, 0.0)
    routed = list(ds_in)
    for _ in range(p["reach_count"]):
        routed = muskingum(routed, k_s, x, dt)
    peak_ds = max(routed)
    t_peak_ds = routed.index(peak_ds) * dt_h
    depth_ds = [
        round(
            manning_depth(q, p["ch_width_m"], p["ch_side_slope"], p["ch_slope"], p["ch_manning"]), 2
        )
        for q in routed
    ]
    max_depth = max(depth_ds)
    bank_q = None
    if max_depth > p["ch_bank_depth_m"]:
        bank_q = next(
            (q for q, d in zip(routed, depth_ds, strict=False) if d > p["ch_bank_depth_m"]), None
        )
    t_ds = [round(k * dt_h, 3) for k in range(len(routed))]

    verdict = []
    if overtopped:
        verdict.append(f"suv gerbdan {-freeboard:.2f} m oshadi (t = {over_start:.1f} soat)")
    elif freeboard < 1.0:
        verdict.append(f"zaxira balandlik faqat {freeboard:.2f} m")
    if breach:
        verdict.append(
            f"yorilish: Q_p = {breach['peak_m3s']:.0f} m³/s, {breach['formation_h']:.1f} soatda"
        )
    if max_depth > p["ch_bank_depth_m"]:
        verdict.append(
            f"quyi byefda suv qirg'oqdan {max_depth - p['ch_bank_depth_m']:.1f} m oshadi ({p['reach_length_km']} km da, {t_peak_ds:.1f} soatdan keyin)"
        )
    return {
        "series": {
            "t": ts,
            "inflow": [round(v, 2) for v in inflow],
            "outflow": outs,
            "level": levels,
            "spill": spills,
            "overtop": overs,
        },
        "downstream": {"t": t_ds, "q": [round(v, 1) for v in routed], "depth": depth_ds},
        "breach": breach,
        "summary": {
            "peak_inflow_m3s": round(peak_in, 1),
            "peak_outflow_m3s": round(peak_out, 1),
            "attenuation_pct": round((1 - peak_out / peak_in) * 100, 1) if peak_in > 0 else 0.0,
            "max_level_m": round(max_level, 3),
            "t_max_level_h": round(ts[i_max], 2),
            "freeboard_m": round(freeboard, 2),
            "overtopped": overtopped,
            "overtop_start_h": round(over_start, 2) if over_start is not None else None,
            "max_spill_m3s": round(max(spills), 1),
            "breach_peak_m3s": breach["peak_m3s"] if breach else 0.0,
            "downstream_peak_m3s": round(peak_ds, 1),
            "downstream_peak_time_h": round(t_peak_ds, 2),
            "downstream_max_depth_m": round(max_depth, 2),
            "bank_overflow_q_m3s": round(bank_q, 1) if bank_q else None,
            "verdict": "; ".join(verdict) if verdict else "Toshqin xavfsiz o'tkaziladi",
            "ok": not verdict,
        },
    }


def _interp(hourly: list[float], t_h: float) -> float:
    i = int(t_h)
    if i >= len(hourly) - 1:
        return hourly[-1]
    f = t_h - i
    return hourly[i] * (1 - f) + hourly[i + 1] * f
