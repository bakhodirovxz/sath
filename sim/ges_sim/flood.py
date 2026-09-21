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
from .spillway import Spillway
from .validity import check_range

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
        "yoki gidrograf qiymatlari (m³/s, har inflow_dt_h soat; bo'sh — sintetik)",
        type="series",
        default=[],
        group="Toshqin",
        advanced=True,
    ),
    Field(
        "inflow_dt_h",
        "Gidrograf qadami",
        "soat",
        default=1.0,
        min=0.01,
        max=24,
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
        "spill_bays",
        "Oraliqlar soni (bykalar + 1)",
        "",
        type="int",
        default=1,
        min=1,
        max=30,
        group="Suv tashlagich",
        hint="yon siqilish ε (Kiselev): bykalar yumaloq boshli deb olinadi",
        advanced=True,
    ),
    Field(
        "spill_gate_height_m",
        "Zatvor balandligi",
        "m",
        default=0,
        min=0,
        group="Suv tashlagich",
        hint="0 — ochiqlik napor ulushi; a < 0.75·H → teshik oqimi Q = μ·b·a·√(2g(H₀ − ε_c·a))",
        advanced=True,
    ),
    Field(
        "spill_approach_area_m2",
        "Kelish o'zani kesimi (H₀ uchun)",
        "m²",
        default=0,
        min=0,
        group="Suv tashlagich",
        hint="0 — kelish tezligi napori hisobga olinmaydi",
        advanced=True,
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
        "fp_width_m",
        "Qayir kengligi (ikki tomon jami)",
        "m",
        default=0,
        min=0,
        group="Quyi byef",
        hint="0 — qayir yo'q (cheksiz trapetsiya); qirg'oq chuqurligidan yuqorida oqim qayirga chiqadi",
    ),
    Field(
        "fp_manning",
        "Qayir Manning n",
        "",
        default=0.06,
        min=0.02,
        max=0.2,
        step=0.005,
        group="Quyi byef",
        advanced=True,
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


def compound_discharge(
    y: float, b: float, z: float, s0: float, n: float, d_bank: float, fp_w: float, fp_n: float
) -> float:
    """Kompaund kesim (asosiy trapetsiya o'zan + qayir) uchun Manning sarfi, bo'laklab
    (Chow 1959 §6-5: har bo'lak o'z gidravlik radiusi bilan, ajratish chizig'i perimetrga kirmaydi)."""
    if y <= 0:
        return 0.0
    yc = min(y, d_bank) if fp_w > 0 else y
    a = (b + z * yc) * yc
    pw = b + 2 * yc * math.sqrt(1 + z * z)
    q = a * (a / pw) ** (2 / 3) * math.sqrt(s0) / n
    if fp_w > 0 and y > d_bank:
        yf = y - d_bank
        top = b + 2 * z * d_bank
        a2 = top * yf  # o'zan ustidagi qism (to'rtburchak, qirg'oq kengligida)
        q += a2 * (a2 / top) ** (2 / 3) * math.sqrt(s0) / n
        af = fp_w * yf
        pf = fp_w + 2 * yf
        q += af * (af / pf) ** (2 / 3) * math.sqrt(s0) / fp_n
    return q


def compound_depth(
    q: float, b: float, z: float, s0: float, n: float, d_bank: float = 1e9, fp_w: float = 0.0,
    fp_n: float = 0.06,
) -> float:
    """Kompaund kesimda normal chuqurlik — bisection (monoton Q(y))."""
    if q <= 0:
        return 0.0
    lo, hi = 0.0, 1.0
    while compound_discharge(hi, b, z, s0, n, d_bank, fp_w, fp_n) < q and hi < 1e4:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        if compound_discharge(mid, b, z, s0, n, d_bank, fp_w, fp_n) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def sig2(v: float) -> float:
    """2 ma'noli raqam — indikativ natijalar uchun (yolg'on aniqlik bermaslik)."""
    if v == 0:
        return 0.0
    return float(f"{v:.2g}")


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
    """Muskingum (Chow 1988 §9.4). Barqarorlik va musbat koeffitsientlar: 2KX ≤ Δt ≤ 2K(1−X)
    (c0 ≥ 0 va c2 ≥ 0) — chaqiruvchi `muskingum_reaches` bilan ta'minlaydi; qirqish yo'q."""
    den = 2 * k_s * (1 - x) + dt_s
    c0 = (dt_s - 2 * k_s * x) / den
    c1 = (dt_s + 2 * k_s * x) / den
    c2 = (2 * k_s * (1 - x) - dt_s) / den
    out = [inflow[0]]
    for i in range(1, len(inflow)):
        out.append(c0 * inflow[i] + c1 * inflow[i - 1] + c2 * out[-1])
    return out


def muskingum_plan(
    length_m: float, c_ms: float, x: float, dt_s: float, n_user: int, warnings: list[str]
) -> tuple[int, float, int]:
    """Oraliqlar soni n, X va ichki qadam bo'linishi `sub` — 2KX ≤ Δt_r ≤ 2K(1−X), Δt_r = Δt/sub.

    - c0 ≥ 0 (Δt_r ≥ 2KX): K juda katta bo'lsa n oshiriladi (n_lo = ⌈2XL/(cΔt)⌉);
    - c2 ≥ 0 (Δt_r ≤ 2K(1−X)): K juda kichik bo'lsa hisob qadami sub ga bo'linadi
      (sub = ⌈Δt/(2K(1−X))⌉) — oraliqlar soni foydalanuvchiniki qoladi;
    - ikkalasi birga bajarilmasa (X > 1/3 da yaxlitlash) X kamaytiriladi, ogohlantirish bilan.
    Chow, Maidment & Mays (1988) §9.4; NRCS NEH-630 17-bob."""
    k_total = length_m / c_ms
    n_lo = max(int(-(-2 * x * k_total // dt_s)), 1)  # ceil
    n = max(n_user, n_lo)
    if n != n_user:
        warnings.append(
            f"Muskingum: oraliqlar soni {n_user} → {n} (Δt ≥ 2KX sharti, L = {length_m/1000:.1f} km, "
            f"c = {c_ms} m/s, Δt = {dt_s/60:.0f} min)"
        )
    k = k_total / n
    sub = max(int(-(-dt_s // (2 * k * (1 - x)))), 1) if x < 1 else 1
    dt_r = dt_s / sub
    if dt_r < 2 * k * x - 1e-9:
        x_new = max(dt_r / (2 * k) * 0.9, 0.0)
        warnings.append(f"Muskingum: X = {x} bilan barqaror qadam yo'q — X = {x_new:.3f}")
        x = x_new
    return n, x, sub


def _resample(series: list[float], factor: int) -> list[float]:
    """Har nuqta orasiga (factor−1) ta chiziqli oraliq nuqta qo'shadi."""
    if factor <= 1:
        return list(series)
    out = []
    for a, b in zip(series, series[1:], strict=False):
        out.extend(a + (b - a) * j / factor for j in range(factor))
    out.append(series[-1])
    return out


def run(p: dict) -> dict:
    warnings: list[str] = []
    dt = p["dt_min"] * 60
    if p["inflow_series"]:
        # Kiruvchi gidrograf qadami hisob qadamidan mayda bo'lsa — uni olamiz (cho'qqi yo'qolmasin)
        dt = min(dt, p["inflow_dt_h"] * 3600)
    dt_h = dt / 3600
    curve = StorageCurve(tuple(p["curve_elev"]), tuple(p["curve_vol"]))
    if p["inflow_series"]:
        series, sdt = p["inflow_series"], p["inflow_dt_h"]
        n = int((len(series) - 1) * sdt / dt_h) + 1
        inflow = [float(_interp(series, i * dt_h / sdt)) for i in range(n)]
    else:
        n = int(p["duration_h"] / dt_h) + 1
        inflow = synthetic_hydrograph(p["peak_m3s"], p["time_to_peak_h"], p["base_m3s"], n, dt_h)
    crest, lcrest = p["crest_m"], p["crest_length_m"]
    sb = p["spill_width_m"]
    spillway = Spillway(
        p["spill_crest_m"],
        sb,
        m=p["spill_coeff"],
        bays=int(p["spill_bays"]),
        approach_area_m2=p["spill_approach_area_m2"],
        gate_opening=p["gate_opening"],
        gate_height_m=p["spill_gate_height_m"],
    )
    qt = p["turbine_m3s"]

    breach_geom: dict | None = None  # {t0, tf, b_avg, z_top, z_bot}

    def breach_q(level: float, t: float) -> float:
        """Yorilish orqali oqim: t_f davomida chiziqli o'sadigan trapetsiya tirqish (DAMBRK, Fread 1988):
        Q = 1.7·b_tub(t)·H^1.5 + 1.35·z·H^2.5,  H = sath − z_b(t); z — yon qiyalik (Froehlich 2008:
        gerbdan oshish 1.4, piping 0.9), b_tub = b_avg − z·h_b (o'rtacha kenglik o'rta balandlikda)."""
        if breach_geom is None or t < breach_geom["t0"]:
            return 0.0
        f = min((t - breach_geom["t0"]) / max(breach_geom["tf"], 1.0), 1.0)
        b_t = breach_geom["b_bot"] * f
        z_t = breach_geom["z_top"] - (breach_geom["z_top"] - breach_geom["z_bot"]) * f
        h = max(level - z_t, 0.0)
        return 1.7 * b_t * h**1.5 + 1.35 * breach_geom["z_side"] * f * h**2.5

    def outflow(level: float, t: float = -1.0) -> tuple[float, float, float, float, float]:
        spill = spillway.discharge(level) if sb > 0 else 0.0
        ho = max(level - p["outlet_sill_m"], 0.0)
        outlet = (
            0.6 * p["outlet_area_m2"] * math.sqrt(2 * G * ho) if p["outlet_area_m2"] > 0 else 0.0
        )
        over = 1.7 * lcrest * max(level - crest, 0.0) ** 1.5
        br = breach_q(level, t)
        return spill, outlet, over, br, spill + outlet + over + br + qt

    def route() -> dict:
        level = p["initial_level_m"]
        S = curve.volume(level)
        ts, levels, outs, spills, overs, brs = [], [], [], [], [], []
        over_start = None
        for i in range(n):
            t = i * dt
            q_in = inflow[i]
            q_in_next = inflow[min(i + 1, n - 1)]
            # Yarim qadam iteratsiya (Puls): O sath (va vaqt) funksiyasi, 3 marta takrorlash yetarli
            o1 = outflow(level, t)[4]
            lv = level
            for _ in range(3):
                o2 = outflow(lv, t + dt)[4]
                s_next = S + ((q_in + q_in_next) / 2 - (o1 + o2) / 2) * dt
                lv = curve.elevation(max(s_next, 0.0))
            sp, ou, ov, br, o = outflow(lv, t + dt)
            ts.append(round(i * dt_h, 3))
            levels.append(round(lv, 3))
            outs.append(round(o, 2))
            spills.append(round(sp, 2))
            overs.append(round(ov, 2))
            brs.append(round(br, 2))
            if ov > 0 and over_start is None:
                over_start = i * dt_h
            S, level = max(s_next, 0.0), lv
        return {
            "ts": ts, "levels": levels, "outs": outs, "spills": spills, "overs": overs,
            "brs": brs, "over_start": over_start,
        }

    # 1-o'tish: yorilishsiz — gerbdan oshish vaqti va maksimal sath
    r0 = route()
    max_level0 = max(r0["levels"])
    overtopped0 = crest - max_level0 < 0
    mode = p["breach"]
    breach = None
    do_breach = mode == "force" or (mode == "auto" and overtopped0)
    if do_breach:
        # Froehlich (1995): V_w, h_w bo'yicha o'rtacha kenglik, hosil bo'lish vaqti, cho'qqi (regressiya)
        if mode == "auto":
            t0_h = r0["over_start"] if r0["over_start"] is not None else r0["ts"][r0["levels"].index(max_level0)]
        else:
            t0_h = r0["ts"][r0["levels"].index(max_level0)]
        z_top = min(max_level0, crest)
        hb = max(z_top - p["breach_bottom_m"], 1.0)  # yorilish balandligi
        vw = max(curve.volume(max_level0) - curve.volume(p["breach_bottom_m"]), 1.0)  # m³
        check_range(warnings, "Yorilish: suv hajmi V_w (Froehlich 1995)", vw / 1e6, 0.0139, 660, "mln m³")
        check_range(warnings, "Yorilish: suv balandligi h_w (Froehlich 1995)", hb, 3.66, 77, "m")
        k0 = 1.3 if mode == "auto" else 1.0
        b_avg = 0.27 * k0 * vw**0.32 * hb**0.04
        tf = 63.2 * math.sqrt(vw / (G * hb**2))  # s
        qp_regr = 0.607 * vw**0.295 * hb**1.24
        z_side = 1.4 if mode == "auto" else 0.9  # Froehlich 2008
        breach_geom = {
            "t0": t0_h * 3600,
            "tf": tf,
            "b_bot": max(b_avg - z_side * hb, 0.1 * b_avg),
            "z_side": z_side,
            "z_top": z_top,
            "z_bot": p["breach_bottom_m"],
        }
        # 2-o'tish: yorilish ombor balansiga ulangan (sath tushadi, oqim sathga bog'liq)
        r1 = route()
        qp_sim = max(r1["brs"])
        if qp_sim > 0 and not (0.5 <= qp_sim / qp_regr <= 2.0):
            warnings.append(
                f"yorilish cho'qqisi: simulyatsiya {qp_sim:.0f} m³/s, Froehlich regressiyasi {qp_regr:.0f} m³/s "
                "— 2 barobardan ko'p farq (yorilish geometriyasi/ombor egri chizig'ini tekshiring)"
            )
        breach = {
            "width_m": round(b_avg, 1),
            "bottom_width_m": round(breach_geom["b_bot"], 1),
            "side_slope": z_side,
            "height_m": round(hb, 1),
            "volume_mcm": round(vw / 1e6, 2),
            "start_h": round(t0_h, 2),
            "formation_h": round(tf / 3600, 2),
            "peak_m3s": round(qp_sim, 0),
            "peak_froehlich_m3s": round(qp_regr, 0),
            # regressiya sochilishi ≈ 2 barobar (Froehlich 1995, Wahl 2004)
            "peak_range_m3s": [round(qp_regr / 2, 0), round(qp_regr * 2, 0)],
            "hydrograph": r1["brs"],
        }
        rr = r1
    else:
        rr = r0
    ts, levels, outs, spills, overs = rr["ts"], rr["levels"], rr["outs"], rr["spills"], rr["overs"]
    over_start = rr["over_start"]
    max_level = max(levels)
    i_max = levels.index(max_level)
    peak_in = max(inflow)
    peak_out = max(outs)
    freeboard = crest - max_level
    overtopped = freeboard < 0

    # Quyi byef: ombor umumiy chiqimi (tashlama + yorilish + ... vaqtda birga) marshrutlanadi
    ds_in = outs
    n_reach, x, sub = muskingum_plan(
        p["reach_length_km"] * 1000, p["wave_speed_ms"], p["musk_x"], dt, p["reach_count"], warnings
    )
    k_s = p["reach_length_km"] * 1000 / n_reach / p["wave_speed_ms"]
    fine = _resample(ds_in, sub)
    for _ in range(n_reach):
        fine = muskingum(fine, k_s, x, dt / sub)
    routed = fine[::sub]
    peak_ds = max(fine)  # cho'qqi ichki qadamda bo'lishi mumkin
    if min(fine) < -1e-6:
        warnings.append("Muskingum: manfiy sarf paydo bo'ldi — koeffitsientlar tekshirilsin")
    # Massa balansi (marshrutlash chiziqli — hajm saqlanishi kerak; seriya oxirida to'lqin qolgan bo'lsa farq)
    v_in, v_out = sum(ds_in) * dt, sum(fine) * dt / sub
    if v_in > 0 and abs(v_out - v_in) / v_in > 0.02:
        warnings.append(
            f"Muskingum massa balansi: chiquvchi hajm kiruvchidan {100*(v_out-v_in)/v_in:+.1f}% farq qiladi "
            "(seriya oxiri to'lqinni to'liq o'tkazmagan bo'lishi mumkin — davomiylikni oshiring)"
        )
    t_peak_ds = fine.index(peak_ds) * dt_h / sub
    fp_w = p["fp_width_m"]
    depth_ds = [
        round(
            compound_depth(
                q, p["ch_width_m"], p["ch_side_slope"], p["ch_slope"], p["ch_manning"],
                p["ch_bank_depth_m"] if fp_w > 0 else 1e9, fp_w, p["fp_manning"],
            ),
            2,
        )
        for q in routed
    ]
    max_depth = max(depth_ds)
    if breach:
        warnings.append(
            "quyi byef natijalari INDIKATIV: yorilish to'lqini gidrologik (Muskingum) usul bilan "
            "marshrutlangan — front uchun dinamik model (Sen-Venan) kerak; chuqurlik normal chuqurlik "
            "(Manning), 2 ma'noli raqamgacha"
        )
    if fp_w <= 0 and max_depth > p["ch_bank_depth_m"]:
        warnings.append(
            "qirg'oqdan oshgan oqim cheksiz trapetsiyada hisoblandi (qayir kengligi berilmagan) — "
            "chuqurlik oshirib ko'rsatilgan bo'lishi mumkin"
        )
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
            f"yorilish (t = {breach['start_h']:.1f} soat): Q_p ≈ {sig2(breach['peak_m3s']):.0f} m³/s "
            f"({breach['formation_h']:.1f} soatda; Froehlich {breach['peak_froehlich_m3s']:.0f}, "
            f"±2×), ombor bo'shaydi"
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
            "breach": rr["brs"],
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
            "breach_peak_froehlich_m3s": breach["peak_froehlich_m3s"] if breach else 0.0,
            "breach_start_h": breach["start_h"] if breach else None,
            "downstream_peak_m3s": sig2(peak_ds) if breach else round(peak_ds, 1),
            "downstream_peak_time_h": round(t_peak_ds, 2),
            "downstream_max_depth_m": sig2(max_depth) if breach else round(max_depth, 2),
            "downstream_indicative": bool(breach),
            "bank_overflow_q_m3s": round(bank_q, 1) if bank_q else None,
            "muskingum_reaches": n_reach,
            "muskingum_x": round(x, 3),
            "muskingum_substeps": sub,
            "verdict": "; ".join(verdict) if verdict else "Toshqin xavfsiz o'tkaziladi",
            "ok": not verdict,
            "warnings": warnings,
        },
    }


def _interp(hourly: list[float], t_h: float) -> float:
    i = int(t_h)
    if i >= len(hourly) - 1:
        return hourly[-1]
    f = t_h - i
    return hourly[i] * (1 - f) + hourly[i + 1] * f
