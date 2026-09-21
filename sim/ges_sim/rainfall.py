"""Yog'ingarchilik → oqim (havza) → suv ombori: jala/selni hisobga olgan toshqin ssenariysi.

SCS-CN oqim (USDA NRCS TR-55):  S = 25400/CN − 254 (mm),  I_a = λ·S (λ = 0.2),
  P_e = (P − I_a)² / (P − I_a + S)  (P > I_a), kumulyativ, qadamma-qadam differensiali.
Yig'ilish vaqti (Kirpich):  t_c = 0.0195·L^0.77·S^−0.385  [min], L — m, S — o'rtacha nishab.
SCS birlik gidrografi:  T_p = 0.6·t_c + Δt/2,  q_p = 0.208·A·Q/T_p  (A km², Q mm, T_p h → m³/s),
  o'lchovsiz egri chiziq (NRCS NEH-630, 16-bob) bilan konvolyutsiya.
Yog'in vaqt taqsimoti: bir tekis, "alternating block" (IDF berilsa — i = a/(t+b)^c dan haqiqiy bloklar;
  bo'lmasa shartli kamayuvchi shakl, ogohlantirish bilan), oldingi/keyingi jadal.
Hisob qadami: Δt ≤ 0.133·t_c (NRCS NEH-630 16-bob), 1 soatdan katta emas — avtomatik tanlanadi.
Amal doirasi (summary.warnings): Kirpich 0.004–0.45 km² havzalarda kalibrovkalangan (Kirpich 1940);
  SCS UH — sub-havza ≤ 8 km² (TR-55), jami ≈ 65 km² gacha; Froehlich (1995) V_w 0.0139–660 mln m³,
  h_w 3.66–77 m.
Qor erishi (daraja-kun):  M = k·(T − T_0)·A_qor  [mm/kun], k ≈ 3–6 mm/°C/kun (yomg'ir ustiga qo'shiladi).
Muzlik ko'li toshqini (GLOF, Nepal 2025 kabi): ko'l hajmi V → Froehlich Q_p = 0.607·V^0.295·h^1.24,
  uchburchak gidrograf, kiruvchi oqimga qo'shiladi.
Natija: kiruvchi gidrograf → ombor orqali o'tkazish (flood moduli: sath, zaxira, gerbdan oshish, yorilish).
"""

from __future__ import annotations

from . import flood
from .schema import Field, Meta, parse
from .validity import check_budget, check_range, nice_step

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
    Field(
        "idf_a",
        "IDF: a (i = a/(t+b)^c, mm/soat, t — min)",
        "",
        default=0,
        min=0,
        group="Yog'in",
        hint="0 — IDF yo'q: taqsimot shartli shakl; berilsa alternating block IDF dan, jami P ga normallanadi",
        advanced=True,
    ),
    Field("idf_b", "IDF: b", "min", default=10, min=0, group="Yog'in", advanced=True),
    Field("idf_c", "IDF: c", "", default=0.7, min=0.1, max=1.5, group="Yog'in", advanced=True),
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


def _pattern(
    total: float, n: int, kind: str, dt_h: float = 1.0, idf: tuple[float, float, float] | None = None
) -> list[float]:
    """n ta Δt blokga jami `total` mm ni taqsimlaydi.

    idf=(a, b, c) berilsa: alternating block (Chow, Maidment & Mays 1988 §14.4) — P(t) = i(t)·t,
    i = a/(t+b)^c (t daqiqada), bloklar ΔP_k = P(kΔt) − P((k−1)Δt) kamayuvchi tartibda, markazga.
    Bo'lmasa — shartli kamayuvchi og'irlik (1/(k+1)^0.6), chaqiruvchi ogohlantiradi."""
    if n <= 1:
        return [total]
    if kind == "uniform":
        return [total / n] * n
    if idf is not None and idf[0] > 0:
        a, b, c = idf
        cum = [a / (k * dt_h * 60 + b) ** c * (k * dt_h) for k in range(n + 1)]  # mm, i(t)·t
        raw = [max(cum[k] - cum[k - 1], 0.0) for k in range(1, n + 1)]
        raw.sort(reverse=True)
    else:
        raw = [1 / (i + 1) ** 0.6 for i in range(n)]
    s = sum(raw) or 1.0
    blocks = [total * x / s for x in raw]
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
    warnings: list[str] = []
    cn = (
        p["cn_override"]
        if p["cn_override"] > 0
        else curve_number(p["land_cover"], p["soil_group"], p["amc"])
    )
    S = 25400 / cn - 254
    ia = 0.2 * S
    A = p["basin_km2"]
    tc = kirpich_tc_h(p["basin_length_km"] * 1000, p["basin_slope"])
    # Amal doirasi
    check_range(warnings, "Havza maydoni (Kirpich t_c)", A, 0.004, 0.45, "km²", "Kirpich 1940, Tennessi")
    check_range(
        warnings, "Havza maydoni (SCS birlik gidrografi)", A, None, 65, "km²",
        "TR-55: sub-havza ≤ 8 km², jami ≈ 65 km²", "havzani bo'lib hisoblash tavsiya etiladi",
    )
    # Hisob qadami: NRCS Δt ≤ 0.133·t_c, 1 soatdan katta emas; GLOF bo'lsa ko'tarilish vaqtining
    # 1/4 idan katta emas (qisqa hodisa cho'qqisi o'rtachalanib yo'qolmasin); chiroyli qadam
    dt_max = min(1.0, 0.133 * tc)
    if p["glof"]:
        _vw, _hb = p["lake_mcm"] * 1e6, p["lake_depth_m"]
        _q = 0.607 * _vw**0.295 * _hb**1.24
        dt_max = min(dt_max, 0.3 * (2 * _vw / _q / 3600) / 4)
    dt = nice_step(dt_max)
    n_rain = int(round(p["rain_hours"] / dt))
    idf = (p["idf_a"], p["idf_b"], p["idf_c"])
    rain = _pattern(p["rain_mm"], n_rain, p["pattern"], dt, idf)
    if p["pattern"] != "uniform" and not idf[0] > 0:
        warnings.append(
            "yog'in taqsimoti shartli shakl (IDF berilmagan) — cho'qqi sarf taqsimotga sezgir, "
            "IDF (a, b, c) kiriting"
        )
    # kumulyativ samarali yog'in (SCS-CN)
    cum_p, cum_pe = 0.0, 0.0
    excess = []
    for r in rain:
        cum_p += r
        pe = (cum_p - ia) ** 2 / (cum_p - ia + S) if cum_p > ia else 0.0
        excess.append(max(pe - cum_pe, 0.0))
        cum_pe = pe
    # qor erishi (har qadam, yog'in davomida + 24 soat)
    melt_mm_h = 0.0
    if p["snowmelt"] and p["air_temp"] > 0:
        melt_mm_h = p["melt_factor"] * p["air_temp"] * p["snow_area_pct"] / 100 / 24
    n_melt = n_rain + int(round(24 / dt))
    # birlik gidrograf (SCS)
    tp = 0.6 * tc + dt / 2
    qp = 0.208 * A * 1.0 / tp  # 1 mm uchun, m³/s
    duh_len = int(5 * tp / dt) + 1
    uh = [qp * _interp(_DUH, (k * dt) / tp) for k in range(duh_len)]
    n_total = max(n_rain + int(round(48 / dt)), duh_len + n_rain + int(round(24 / dt)))
    check_budget(n_total * duh_len, "Yog'in-oqim", "yog'in davomiyligini kamaytiring")
    q = [0.0] * n_total
    inputs = [
        (excess[k] if k < n_rain else 0.0) + (melt_mm_h * dt if k < n_melt else 0.0)
        for k in range(n_total)
    ]
    for k, ex in enumerate(inputs):
        if ex <= 0:
            continue
        for j, u in enumerate(uh):
            if k + j < n_total:
                q[k + j] += ex * u
    glof = None
    if p["glof"]:
        vw = p["lake_mcm"] * 1e6
        hb = p["lake_depth_m"]
        check_range(warnings, "GLOF ko'l hajmi (Froehlich 1995)", p["lake_mcm"], 0.0139, 660, "mln m³")
        check_range(warnings, "GLOF ko'l chuqurligi (Froehlich 1995)", hb, 3.66, 77, "m")
        qpk = 0.607 * vw**0.295 * hb**1.24
        t_tot = 2 * vw / qpk / 3600  # soat
        tf = t_tot * 0.3
        st = p["glof_start_h"]
        if tf < 2 * dt:
            warnings.append(
                f"GLOF ko'tarilish vaqti ({tf:.2f} soat) hisob qadamiga ({dt} soat) nisbatan qisqa — "
                "seriyadagi cho'qqi hajm saqlangan holda pasaytirilgan"
            )

        def tri(t: float) -> float:
            if t < 0 or t > t_tot:
                return 0.0
            return qpk * (t / tf if t <= tf else max(1 - (t - tf) / (t_tot - tf), 0.0))

        # Har qadamni 20 bo'lakda integrallaymiz (hajm saqlanadi); qadam Δt ≤ 0.133·t_c
        for k in range(n_total):
            t0 = k * dt - st
            if t0 + dt < 0 or t0 > t_tot:
                continue
            q[k] += sum(tri(t0 + (j + 0.5) * dt / 20) for j in range(20)) / 20
        glof = {
            "peak_formula_m3s": round(qpk, 0),  # Froehlich cho'qqisi (nuqtaviy); seriyadagi — asosiy
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
        "dt_h": dt,
        "snowmelt_mm_day": round(melt_mm_h * 24, 1),
        "rain": [round(r, 3) for r in rain],
        "excess": [round(e, 3) for e in excess],
        "inflow": inflow,
        "glof": glof,
        "warnings": warnings,
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
    dt = h["dt_h"]
    peak = max(h["inflow"])
    tpk = h["inflow"].index(peak) * dt
    out = {
        "series": {
            "t": [round(k * dt, 4) for k in range(len(h["inflow"]))],
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
            "dt_h": dt,
            "peak_inflow_m3s": round(peak, 1),
            "time_to_peak_h": round(tpk, 2),
            "volume_mcm": round(sum(x - p["base_m3s"] for x in h["inflow"]) * dt * 3600 / 1e6, 2),
            "snowmelt_mm_day": h["snowmelt_mm_day"],
            "warnings": list(h["warnings"]),
        },
    }
    if p["route"]:
        fp = parse(
            flood.FIELDS,
            {
                "inflow_series": h["inflow"],
                "inflow_dt_h": dt,
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
        # flood seriyasi o'z qadamida — vaqt o'qini unga keltirish (yog'in: shu qadamga tushgan blok)
        out["series"]["t"] = fr["series"]["t"]
        out["series"]["inflow"] = fr["series"]["inflow"]
        n = len(fr["series"]["t"])
        out["series"]["rain_mm"] = [
            h["rain"][int(t / dt)] if int(t / dt) < len(h["rain"]) else 0.0
            for t in fr["series"]["t"]
        ][:n]
        out["series"]["excess_mm"] = [
            h["excess"][int(t / dt)] if int(t / dt) < len(h["excess"]) else 0.0
            for t in fr["series"]["t"]
        ][:n]
        out["summary"]["warnings"].extend(fs_w for fs_w in fr["summary"].get("warnings", []))
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
        verdict = f"CN {h['cn']}: {p['rain_mm']} mm yog'indan {h['runoff_mm']} mm oqim, cho'qqi {peak:.0f} m³/s ({tpk:.1f} soatda)"
        if h["glof"]:
            verdict += " (GLOF bilan)"
        out["summary"]["verdict"] = verdict + "; ombor: " + fs["verdict"]
        out["summary"]["ok"] = fs["ok"]
    else:
        out["summary"]["verdict"] = (
            f"CN {h['cn']}: {p['rain_mm']} mm → {h['runoff_mm']} mm oqim, cho'qqi {peak:.0f} m³/s ({tpk:.1f} soatda)"
        )
        out["summary"]["ok"] = True
    return out
