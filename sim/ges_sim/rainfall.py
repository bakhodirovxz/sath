"""Yog'ingarchilik → oqim (havza) → suv ombori: jala/selni hisobga olgan toshqin ssenariysi.

SCS-CN oqim (USDA NRCS TR-55):  S = 25400/CN − 254 (mm),  I_a = λ·S (λ = 0.2),
  P_e = (P − I_a)² / (P − I_a + S)  (P > I_a), kumulyativ, qadamma-qadam differensiali.
Yig'ilish vaqti (Kirpich):  t_c = 0.0195·L^0.77·S^−0.385  [min], L — m, S — o'rtacha nishab.
SCS birlik gidrografi:  T_p = 0.6·t_c + Δt/2,  q_p = 0.208·A·Q/T_p  (A km², Q mm, T_p h → m³/s),
  o'lchovsiz egri chiziq (NRCS NEH-630, 16-bob) bilan konvolyutsiya.
Yog'in vaqt taqsimoti: bir tekis, "alternating block" (markazda maksimum), oldingi/keyingi jadal.
Qor erishi (daraja-kun):  M = k·(T − T_0)·A_qor  [mm/kun], k ≈ 3–6 mm/°C/kun (yomg'ir ustiga qo'shiladi).
Muzlik ko'li toshqini (GLOF, Nepal 2025 kabi): ko'l hajmi V → Froehlich Q_p = 0.607·V^0.295·h^1.24,
  uchburchak gidrograf, kiruvchi oqimga qo'shiladi.
Natija: kiruvchi gidrograf → ombor orqali o'tkazish (flood moduli: sath, zaxira, gerbdan oshish, yorilish).
"""

from __future__ import annotations

from . import flood
from .schema import Field, Meta, parse

# NRCS o'lchovsiz birlik gidrografi (t/T_p → q/q_p)
_DUH = [
    (0.0, 0.0),
    (0.1, 0.03),
    (0.2, 0.1),
    (0.3, 0.19),
    (0.4, 0.31),
    (0.5, 0.47),
    (0.6, 0.66),
    (0.7, 0.82),
    (0.8, 0.93),
    (0.9, 0.99),
    (1.0, 1.0),
    (1.1, 0.99),
    (1.2, 0.93),
    (1.3, 0.86),
    (1.4, 0.78),
    (1.5, 0.68),
    (1.6, 0.56),
    (1.7, 0.46),
    (1.8, 0.39),
    (1.9, 0.33),
    (2.0, 0.28),
    (2.2, 0.207),
    (2.4, 0.147),
    (2.6, 0.107),
    (2.8, 0.077),
    (3.0, 0.055),
    (3.2, 0.04),
    (3.4, 0.029),
    (3.6, 0.021),
    (3.8, 0.015),
    (4.0, 0.011),
    (4.5, 0.005),
    (5.0, 0.0),
]

CN_TABLE = {  # (yer qoplami, gidrologik grunt guruhi) → CN; NRCS TR-55 2-2 jadval (soddalashtirilgan)
    "forest": {"A": 30, "B": 55, "C": 70, "D": 77},
    "pasture": {"A": 39, "B": 61, "C": 74, "D": 80},
    "crop": {"A": 67, "B": 78, "C": 85, "D": 89},
    "bare_rock": {"A": 77, "B": 86, "C": 91, "D": 94},
    "urban": {"A": 77, "B": 85, "C": 90, "D": 92},
    "glacier_snow": {"A": 85, "B": 90, "C": 94, "D": 96},
}

META = Meta(
    id="rainfall",
    title="Yog'ingarchilik → toshqin (havza oqimi, sel, GLOF)",
    description="Jala (loyihaviy yog'in), qor erishi va muzlik ko'li toshqini (GLOF) dan havza kiruvchi gidrografi "
    "(SCS-CN + birlik gidrograf), so'ng suv ombori orqali o'tkazish: sath, zaxira, gerbdan oshish, yorilish. "
    "Xitoy/Nepal 2025 hodisalari kabi jadal yog'in ssenariylari.",
    group="favqulodda",
    icon="flood",
    formulas=[
        "S = 25400/CN − 254; P_e = (P−0.2S)²/(P+0.8S)",
        "t_c = 0.0195·L^0.77·S^−0.385 (Kirpich)",
        "q_p = 0.208·A·Q/T_p (SCS UH)",
        "M = k·(T−T₀)·A_qor (daraja-kun)",
        "Q_p,GLOF = 0.607·V^0.295·h^1.24",
    ],
    viz={"water_level": "level"},
    outputs=[
        {"key": "peak_inflow_m3s", "label": "Maks. kiruvchi sarf", "unit": "m³/s"},
        {"key": "runoff_mm", "label": "Samarali oqim qatlami", "unit": "mm"},
        {"key": "max_level_m", "label": "Maksimal sath", "unit": "m"},
        {"key": "freeboard_m", "label": "Qolgan zaxira", "unit": "m"},
    ],
)

FIELDS = [
    Field(
        "basin_km2",
        "Havza maydoni A",
        "km²",
        default=1200,
        min=1,
        group="Havza",
        model="site.basin_km2",
    ),
    Field(
        "basin_length_km",
        "Havza uzunligi (eng uzoq oqim yo'li) L",
        "km",
        default=60,
        min=0.5,
        group="Havza",
    ),
    Field(
        "basin_slope",
        "O'rtacha nishab S",
        "m/m",
        default=0.02,
        min=0.0005,
        max=1,
        step=0.005,
        group="Havza",
    ),
    Field(
        "land_cover",
        "Yer qoplami",
        type="select",
        default="pasture",
        options=(
            ("forest", "O'rmon"),
            ("pasture", "Yaylov / buta"),
            ("crop", "Ekin maydoni"),
            ("bare_rock", "Yalang'och qoya / tog'"),
            ("urban", "Shahar"),
            ("glacier_snow", "Muzlik / qor"),
        ),
        group="Havza",
    ),
    Field(
        "soil_group",
        "Gidrologik grunt guruhi",
        type="select",
        default="C",
        options=(
            ("A", "A — qum, chuqur (past oqim)"),
            ("B", "B — qumloq"),
            ("C", "C — soz tuproq"),
            ("D", "D — gil, qoya (yuqori oqim)"),
        ),
        group="Havza",
    ),
    Field(
        "cn_override",
        "CN (0 — jadvaldan)",
        "",
        default=0,
        min=0,
        max=100,
        group="Havza",
        advanced=True,
    ),
    Field(
        "amc",
        "Oldingi namlik (AMC)",
        type="select",
        default="II",
        options=(
            ("I", "I — quruq"),
            ("II", "II — o'rtacha"),
            ("III", "III — nam (oldin yomg'ir yoqqan)"),
        ),
        group="Havza",
        hint="Nam tuproq — oqim 1.5–2 marta ko'p",
    ),
    Field(
        "rain_mm",
        "Yog'in miqdori P",
        "mm",
        default=150,
        min=1,
        group="Yog'in",
        hint="24 soatlik 1 % (100 yillik) jala: tog'larda 100–300 mm",
    ),
    Field("rain_hours", "Yog'in davomiyligi", "soat", default=24, min=1, max=240, group="Yog'in"),
    Field(
        "pattern",
        "Vaqt taqsimoti",
        type="select",
        default="block",
        options=(
            ("uniform", "Bir tekis"),
            ("block", "Markazda jadal (alternating block)"),
            ("front", "Boshida jadal"),
            ("back", "Oxirida jadal"),
        ),
        group="Yog'in",
    ),
    Field("snowmelt", "Qor erishi hisobga olinsin", type="bool", default=False, group="Qor"),
    Field(
        "snow_area_pct", "Qor bilan qoplangan ulush", "%", default=30, min=0, max=100, group="Qor"
    ),
    Field(
        "air_temp", "Havo harorati (qor zonasida)", "°C", default=8, min=-20, max=30, group="Qor"
    ),
    Field(
        "melt_factor",
        "Erish koeffitsienti k",
        "mm/°C/kun",
        default=4.0,
        min=1,
        max=10,
        step=0.5,
        group="Qor",
    ),
    Field(
        "glof", "Muzlik ko'li toshqini (GLOF) qo'shilsin", type="bool", default=False, group="GLOF"
    ),
    Field("lake_mcm", "Ko'l hajmi V", "mln m³", default=5, min=0.01, group="GLOF"),
    Field(
        "lake_depth_m",
        "Ko'l chuqurligi (to'g'on/morena balandligi)",
        "m",
        default=30,
        min=1,
        group="GLOF",
    ),
    Field("glof_start_h", "Boshlanish vaqti", "soat", default=12, min=0, group="GLOF"),
    Field(
        "base_m3s",
        "Bazaviy (yog'ingacha) sarf",
        "m³/s",
        default=100,
        min=0,
        group="Ombor",
        live="inflow",
    ),
    Field(
        "route",
        "Ombor orqali o'tkazilsin (sath, gerbdan oshish)",
        type="bool",
        default=True,
        group="Ombor",
    ),
    Field(
        "curve_elev",
        "Sath–hajm: sathlar",
        "m",
        type="series",
        default=[850, 870, 890, 905, 915],
        group="Ombor",
    ),
    Field(
        "curve_vol",
        "Sath–hajm: hajmlar",
        "mln m³",
        type="series",
        default=[0, 60, 220, 480, 700],
        group="Ombor",
    ),
    Field(
        "initial_level_m",
        "Boshlang'ich sath",
        "m",
        default=905,
        group="Ombor",
        live="upstream_level",
    ),
    Field("crest_m", "Gerb belgisi", "m", default=912, group="Ombor"),
    Field("crest_length_m", "Gerb uzunligi", "m", default=300, min=1, group="Ombor"),
    Field("spill_crest_m", "Suv tashlagich ostonasi", "m", default=905, group="Ombor"),
    Field("spill_width_m", "Suv tashlagich kengligi", "m", default=40, min=0, group="Ombor"),
    Field(
        "gate_opening",
        "Darvozalar ochiqligi",
        "0–1",
        default=1.0,
        min=0,
        max=1,
        step=0.1,
        group="Ombor",
    ),
    Field("turbine_m3s", "Turbinalar sarfi", "m³/s", default=150, min=0, group="Ombor"),
    Field(
        "breach_bottom_m", "Yorilish tubi belgisi", "m", default=850, group="Ombor", advanced=True
    ),
]


def curve_number(land: str, soil: str, amc: str) -> float:
    cn = float(CN_TABLE[land][soil])
    if amc == "I":
        cn = 4.2 * cn / (10 - 0.058 * cn)
    elif amc == "III":
        cn = 23 * cn / (10 + 0.13 * cn)
    return max(min(cn, 99.0), 1.0)


def kirpich_tc_h(length_m: float, slope: float) -> float:
    return 0.0195 * length_m**0.77 * slope ** (-0.385) / 60.0


def _pattern(total: float, n: int, kind: str) -> list[float]:
    if n <= 1:
        return [total]
    if kind == "uniform":
        return [total / n] * n
    # nisbiy og'irliklar: alternating block ~ kamayuvchi, markazga joylash
    w = [1 / (i + 1) ** 0.6 for i in range(n)]
    s = sum(w)
    blocks = [total * x / s for x in w]
    if kind == "front":
        return blocks
    if kind == "back":
        return blocks[::-1]
    out: list[float] = [0.0] * n
    c = n // 2
    left, right = c - 1, c + 1
    out[c] = blocks[0]
    for k, b in enumerate(blocks[1:]):
        if k % 2 == 0 and left >= 0:
            out[left] = b
            left -= 1
        elif right < n:
            out[right] = b
            right += 1
        elif left >= 0:
            out[left] = b
            left -= 1
    return out


def hydrograph(p: dict) -> dict:
    cn = (
        p["cn_override"]
        if p["cn_override"] > 0
        else curve_number(p["land_cover"], p["soil_group"], p["amc"])
    )
    S = 25400 / cn - 254
    ia = 0.2 * S
    dt = 1.0  # soat
    n_rain = int(p["rain_hours"])
    rain = _pattern(p["rain_mm"], n_rain, p["pattern"])
    # kumulyativ samarali yog'in
    cum_p, cum_pe = 0.0, 0.0
    excess = []
    for r in rain:
        cum_p += r
        pe = (cum_p - ia) ** 2 / (cum_p - ia + S) if cum_p > ia else 0.0
        excess.append(max(pe - cum_pe, 0.0))
        cum_pe = pe
    # qor erishi (har soat, yog'in davomida + 24 soat)
    melt_mm_h = 0.0
    if p["snowmelt"] and p["air_temp"] > 0:
        melt_mm_h = p["melt_factor"] * p["air_temp"] * p["snow_area_pct"] / 100 / 24
    # birlik gidrograf
    A = p["basin_km2"]
    tc = kirpich_tc_h(p["basin_length_km"] * 1000, p["basin_slope"])
    tp = 0.6 * tc + dt / 2
    qp = 0.208 * A * 1.0 / tp  # 1 mm uchun, m³/s
    duh_len = int(5 * tp / dt) + 1
    uh = [qp * _interp(_DUH, (k * dt) / tp) for k in range(duh_len)]
    total_h = max(n_rain + 48, duh_len + n_rain + 24)
    q = [0.0] * total_h
    inputs = [
        (excess[k] if k < n_rain else 0.0) + (melt_mm_h if k < n_rain + 24 else 0.0)
        for k in range(total_h)
    ]
    for k, ex in enumerate(inputs):
        if ex <= 0:
            continue
        for j, u in enumerate(uh):
            if k + j < total_h:
                q[k + j] += ex * u
    glof = None
    if p["glof"]:
        vw = p["lake_mcm"] * 1e6
        hb = p["lake_depth_m"]
        qpk = 0.607 * vw**0.295 * hb**1.24
        t_tot = 2 * vw / qpk / 3600  # soat
        tf = t_tot * 0.3
        st = int(p["glof_start_h"])

        def tri(t: float) -> float:
            if t < 0 or t > t_tot:
                return 0.0
            return qpk * (t / tf if t <= tf else max(1 - (t - tf) / (t_tot - tf), 0.0))

        # Soatlik o'rtacha (qisqa hodisa — hajm saqlanadi): har soatni 20 bo'lakda integrallaymiz
        for k in range(total_h):
            t0 = k - st
            if t0 + 1 < 0 or t0 > t_tot:
                continue
            q[k] += sum(tri(t0 + (j + 0.5) / 20) for j in range(20)) / 20
        glof = {
            "peak_m3s": round(qpk, 0),
            "duration_h": round(t_tot, 1),
            "volume_mcm": p["lake_mcm"],
        }
    inflow = [round(x + p["base_m3s"], 2) for x in q]
    return {
        "cn": round(cn, 1),
        "S_mm": round(S, 1),
        "runoff_mm": round(cum_pe, 1),
        "runoff_coeff": round(cum_pe / p["rain_mm"], 3) if p["rain_mm"] > 0 else 0,
        "tc_h": round(tc, 2),
        "tp_h": round(tp, 2),
        "snowmelt_mm_day": round(melt_mm_h * 24, 1),
        "rain": [round(r, 2) for r in rain],
        "excess": [round(e, 2) for e in excess],
        "inflow": inflow,
        "glof": glof,
    }


def _interp(pts, x):
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 0.0


def run(p: dict) -> dict:
    h = hydrograph(p)
    peak = max(h["inflow"])
    tpk = h["inflow"].index(peak)
    out = {
        "series": {
            "t": list(range(len(h["inflow"]))),
            "inflow": h["inflow"],
            "rain_mm": h["rain"] + [0.0] * (len(h["inflow"]) - len(h["rain"])),
            "excess_mm": h["excess"] + [0.0] * (len(h["inflow"]) - len(h["excess"])),
        },
        "glof": h["glof"],
        "summary": {
            "cn": h["cn"],
            "runoff_mm": h["runoff_mm"],
            "runoff_coeff": h["runoff_coeff"],
            "tc_h": h["tc_h"],
            "peak_inflow_m3s": round(peak, 1),
            "time_to_peak_h": tpk,
            "volume_mcm": round(sum(x - p["base_m3s"] for x in h["inflow"]) * 3600 / 1e6, 2),
            "snowmelt_mm_day": h["snowmelt_mm_day"],
        },
    }
    if p["route"]:
        fp = parse(
            flood.FIELDS,
            {
                "inflow_series": h["inflow"],
                "base_m3s": p["base_m3s"],
                "curve_elev": p["curve_elev"],
                "curve_vol": p["curve_vol"],
                "initial_level_m": p["initial_level_m"],
                "crest_m": p["crest_m"],
                "crest_length_m": p["crest_length_m"],
                "spill_crest_m": p["spill_crest_m"],
                "spill_width_m": p["spill_width_m"],
                "gate_opening": p["gate_opening"],
                "turbine_m3s": p["turbine_m3s"],
                "breach_bottom_m": p["breach_bottom_m"],
                "breach": "auto",
            },
        )
        fr = flood.run(fp)
        out["series"].update(
            {
                "level": fr["series"]["level"],
                "outflow": fr["series"]["outflow"],
                "overtop": fr["series"]["overtop"],
            }
        )
        # flood seriyasi 15 daqiqalik — vaqt o'qini soatga keltirish
        out["series"]["t"] = fr["series"]["t"]
        out["series"]["inflow"] = fr["series"]["inflow"]
        n = len(fr["series"]["t"])
        out["series"]["rain_mm"] = [
            h["rain"][int(t)] if int(t) < len(h["rain"]) else 0.0 for t in fr["series"]["t"]
        ][:n]
        out["series"]["excess_mm"] = [
            h["excess"][int(t)] if int(t) < len(h["excess"]) else 0.0 for t in fr["series"]["t"]
        ][:n]
        out["downstream"] = fr["downstream"]
        out["breach"] = fr["breach"]
        fs = fr["summary"]
        out["summary"].update(
            {
                k: fs[k]
                for k in (
                    "max_level_m",
                    "freeboard_m",
                    "overtopped",
                    "peak_outflow_m3s",
                    "breach_peak_m3s",
                    "downstream_max_depth_m",
                    "overtop_start_h",
                    "t_max_level_h",
                )
            }
        )
        verdict = f"CN {h['cn']}: {p['rain_mm']} mm yog'indan {h['runoff_mm']} mm oqim, cho'qqi {peak:.0f} m³/s ({tpk} soatda)"
        if h["glof"]:
            verdict += f"; GLOF cho'qqisi {h['glof']['peak_m3s']:.0f} m³/s"
        out["summary"]["verdict"] = verdict + "; ombor: " + fs["verdict"]
        out["summary"]["ok"] = fs["ok"]
    else:
        out["summary"]["verdict"] = (
            f"CN {h['cn']}: {p['rain_mm']} mm → {h['runoff_mm']} mm oqim, cho'qqi {peak:.0f} m³/s ({tpk} soatda)"
        )
        out["summary"]["ok"] = True
    return out
