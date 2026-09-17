"""Beton og'irlik to'g'onining barqarorligi (1 m kenglikdagi kesim): ag'darilish, sirpanish, tag kuchlanishlari.

Kuchlar (kN/m), momentlar quyi byef tovoni (toe) atrofida:
  Og'irlik           W = γ_c·A_profil                         (ushlab turadi)
  Gidrostatik        P_w = γ_w·h²/2,  h/3 balandlikda          (ag'daradi; quyi byef — ushlab turadi)
  Qiya yuzadagi suv  W_v = γ_w·m·h²/2                          (ushlab turadi)
  Filtratsion bosim  U = ∫p(x)dx,  p: tovon h₁ → drenaj h₃ → toe h₂,  h₃ = h₂ + (1−E)(h₁−h₂)(B−x_d)/B  (USACE EM 1110-2-2200)
  Loyqa bosimi       P_s = γ_s'·h_s²/2                          (γ_s' ≈ 8.5 kN/m³ ekvivalent suyuqlik, USBR)
  Zilzila            k_h·W (og'irlik markazida), k_v·W (vertikal), Westergaard P_e = (7/12)·k_h·γ_w·h₁² (0.4h₁)
Mezonlar (USACE / SNiP 2.06.06-85 uslubida, sozlanadi):
  K_ag'd = ΣM_ushlab / ΣM_ag'dar ≥ [K],   K_sirp = (c·B + ΣV·tgφ)/ΣH ≥ [K]
  Tag kuchlanishi σ = ΣV/B·(1 ± 6e/B); statik holda e ≤ B/6 (tovonda cho'zilish yo'q).
"""

from __future__ import annotations

from .schema import Field, Meta
from .seismic import westergaard_force

GAMMA_W = 9.81  # kN/m³

META = Meta(
    id="dam_stability",
    title="To'g'on barqarorligi (zilzila, toshqin)",
    description="Beton og'irlik to'g'oni: og'irlik, gidrostatik, filtratsion, loyqa, muz va seysmik kuchlar → "
    "ag'darilish/sirpanish zaxirasi, tag kuchlanishlari; sath va seysmik koeffitsient bo'yicha skanerlash.",
    group="mustahkamlik",
    icon="dam",
    formulas=[
        "K_ag'd = ΣM_ushlab/ΣM_ag'dar",
        "K_sirp = (c·B + ΣV·tgφ)/ΣH",
        "σ_toe,heel = ΣV/B·(1 ± 6e/B)",
        "P_e = (7/12)·k_h·γ_w·h₁² (Westergaard)",
        "U — USACE EM 1110-2-2200 drenajli epyura",
    ],
    viz={"color_by": "dam", "water_level": "headwater_m"},
    outputs=[
        {"key": "fs_overturning", "label": "Ag'darilish zaxirasi", "unit": ""},
        {"key": "fs_sliding", "label": "Sirpanish zaxirasi", "unit": ""},
        {"key": "sigma_toe_mpa", "label": "Tovon kuchlanishi", "unit": "MPa"},
        {"key": "sigma_heel_mpa", "label": "Yuqori tovon kuchlanishi", "unit": "MPa"},
    ],
)

FIELDS = [
    Field(
        "height_m",
        "To'g'on balandligi H (tagdan gerbgacha)",
        "m",
        default=80,
        min=1,
        group="Profil",
        model="dam.height_m",
    ),
    Field(
        "crest_width_m",
        "Gerb kengligi",
        "m",
        default=8,
        min=0.5,
        group="Profil",
        model="dam.crest_width_m",
    ),
    Field(
        "upstream_slope",
        "Yuqori yuza qiyaligi m_u (gor./vert.)",
        "",
        default=0.05,
        min=0,
        max=1.5,
        step=0.05,
        group="Profil",
    ),
    Field(
        "downstream_slope",
        "Quyi yuza qiyaligi m_d (gor./vert.)",
        "",
        default=0.75,
        min=0,
        max=2,
        step=0.05,
        group="Profil",
    ),
    Field(
        "concrete_kn_m3",
        "Beton solishtirma og'irligi",
        "kN/m³",
        default=24,
        min=15,
        max=28,
        step=0.5,
        group="Profil",
    ),
    Field(
        "base_elev_m",
        "Tag belgisi",
        "m",
        default=830,
        group="Sathlar",
        model="dam.base_elevation_m",
    ),
    Field(
        "headwater_m", "Yuqori byef sathi", "m", default=905, group="Sathlar", live="upstream_level"
    ),
    Field(
        "tailwater_m", "Quyi byef sathi", "m", default=840, group="Sathlar", live="downstream_level"
    ),
    Field("silt_m", "Loyqa qalinligi (yuqori tovonda)", "m", default=10, min=0, group="Sathlar"),
    Field(
        "silt_kn_m3",
        "Loyqa ekvivalent og'irligi (gorizontal)",
        "kN/m³",
        default=8.5,
        min=0,
        group="Sathlar",
        advanced=True,
    ),
    Field(
        "ice_kn_m",
        "Muz bosimi (gerb sathida)",
        "kN/m",
        default=0,
        min=0,
        group="Sathlar",
        advanced=True,
    ),
    Field(
        "drain_eff",
        "Drenaj samaradorligi E",
        "",
        default=0.5,
        min=0,
        max=0.9,
        step=0.05,
        group="Tag",
        hint="0 — drenaj yo'q; USACE 0.25–0.5; 0.67 tekshirilgan",
    ),
    Field("drain_x_m", "Drenaj masofasi tovondan", "m", default=6, min=0, group="Tag"),
    Field(
        "friction",
        "Ishqalanish tgφ (beton–qoya)",
        "",
        default=0.7,
        min=0.2,
        max=1.2,
        step=0.05,
        group="Tag",
    ),
    Field(
        "cohesion_kpa",
        "Ilashish c",
        "kPa",
        default=200,
        min=0,
        group="Tag",
        hint="Ishonchsiz bo'lsa 0",
    ),
    Field(
        "allow_stress_mpa",
        "Ruxsat etilgan tag kuchlanishi",
        "MPa",
        default=4.0,
        min=0.1,
        step=0.1,
        group="Tag",
    ),
    Field(
        "kh",
        "Seysmik koeffitsient k_h",
        "",
        default=0.0,
        min=0,
        max=0.6,
        step=0.01,
        group="Zilzila",
        hint="«Zilzila ta'siri» simulyatsiyasidan; 0 — statik",
    ),
    Field(
        "kv",
        "Vertikal koeffitsient k_v (yuqoriga)",
        "",
        default=0.0,
        min=0,
        max=0.4,
        step=0.01,
        group="Zilzila",
        advanced=True,
    ),
    Field(
        "req_overturning",
        "Talab: K_ag'darilish",
        "",
        default=1.5,
        min=1,
        step=0.1,
        group="Mezon",
        hint="statik 1.5; toshqin 1.3; zilzila 1.1",
    ),
    Field(
        "req_sliding",
        "Talab: K_sirpanish",
        "",
        default=1.5,
        min=1,
        step=0.1,
        group="Mezon",
        hint="statik 1.5 (ilashishsiz) / 2.0 (ilashish bilan); zilzila 1.1",
    ),
]


def _profile(H: float, bc: float, mu: float, md: float) -> list[tuple[float, float]]:
    """Ko'pburchak (x — yuqori tovondan, y — tagdan): tovon, yuqori gerb, quyi gerb, toe."""
    return [(0.0, 0.0), (mu * H, H), (mu * H + bc, H), (mu * H + bc + md * H, 0.0)]


def _area_centroid(poly: list[tuple[float, float]]) -> tuple[float, float, float]:
    a = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    a *= 0.5
    return abs(a), cx / (6 * a), cy / (6 * a)


def analyze(p: dict, headwater: float | None = None, kh: float | None = None) -> dict:
    H, bc, mu, md = p["height_m"], p["crest_width_m"], p["upstream_slope"], p["downstream_slope"]
    gc = p["concrete_kn_m3"]
    poly = _profile(H, bc, mu, md)
    B = poly[-1][0]
    area, xg, yg = _area_centroid(poly)
    hw = (p["headwater_m"] if headwater is None else headwater) - p["base_elev_m"]
    h1 = max(min(hw, H + 5.0), 0.0)  # gerbdan 5 m gacha toshib o'tish ruxsat (tekshiruv uchun)
    h2 = max(min(p["tailwater_m"] - p["base_elev_m"], H), 0.0)
    kh = p["kh"] if kh is None else kh
    kv = p["kv"]

    W = gc * area
    forces = []  # (nom, V kN, H kN, arm_V (toe dan), arm_H (tagdan)) — V yuqoriga musbat, H quyi byef tomon musbat
    forces.append(("Og'irlik W", W * (1 - kv), 0.0, B - xg, 0.0))
    # Suv (yuqori byef)
    pw1 = GAMMA_W * h1**2 / 2
    forces.append(("Gidrostatik P_w1", 0.0, pw1, 0.0, h1 / 3))
    if mu > 0:
        hh = min(h1, H)
        wv1 = GAMMA_W * mu * hh**2 / 2 + (GAMMA_W * (h1 - hh) * mu * hh if h1 > hh else 0.0)
        forces.append(("Qiya yuzadagi suv W_v1", wv1, 0.0, B - mu * hh / 3, 0.0))
    # Quyi byef
    pw2 = GAMMA_W * h2**2 / 2
    forces.append(("Quyi byef P_w2", 0.0, -pw2, 0.0, h2 / 3))
    if md > 0 and h2 > 0:
        forces.append(("Quyi yuzadagi suv W_v2", GAMMA_W * md * h2**2 / 2, 0.0, md * h2 / 3, 0.0))
    # Loyqa
    hs = min(p["silt_m"], h1)
    if hs > 0:
        forces.append(("Loyqa P_s", 0.0, p["silt_kn_m3"] * hs**2 / 2, 0.0, hs / 3))
    if p["ice_kn_m"] > 0:
        forces.append(("Muz P_ice", 0.0, p["ice_kn_m"], 0.0, min(h1, H)))
    # Filtratsion bosim: uchta nuqtali epyura (tovon h1, drenaj h3, toe h2)
    E, xd = p["drain_eff"], min(p["drain_x_m"], B)
    h3 = h2 + (1 - E) * (h1 - h2) * (B - xd) / B if E > 0 and 0 < xd < B else None
    pts = [(0.0, h1), (B, h2)] if h3 is None else [(0.0, h1), (xd, h3), (B, h2)]
    U = MU = 0.0
    for (xa, ha), (xb, hb) in zip(pts, pts[1:], strict=False):
        seg = xb - xa
        f1, f2 = (
            GAMMA_W * ha * seg,
            GAMMA_W * (hb - ha) * seg / 2,
        )  # to'g'ri to'rtburchak + uchburchak
        x1, x2 = xa + seg / 2, xa + 2 * seg / 3
        U += f1 + f2
        MU += f1 * (B - x1) + f2 * (B - x2)
    forces.append(("Filtratsion U", -U, 0.0, MU / U if U > 0 else 0.0, 0.0))
    # Zilzila
    if kh > 0:
        forces.append(("Inersiya k_h·W", 0.0, kh * W, 0.0, yg))
        pe, ye = westergaard_force(kh, min(h1, H))
        forces.append(("Westergaard P_e", 0.0, pe / 1000, 0.0, ye))

    sum_v = sum(f[1] for f in forces)
    sum_h = sum(f[2] for f in forces)
    m_res = sum(f[1] * f[3] for f in forces if f[1] > 0) + sum(
        -f[2] * f[4] for f in forces if f[2] < 0
    )
    m_over = sum(f[2] * f[4] for f in forces if f[2] > 0) + sum(
        -f[1] * f[3] for f in forces if f[1] < 0
    )
    fs_o = m_res / m_over if m_over > 0 else 99.0
    fs_s = (p["cohesion_kpa"] * B + sum_v * p["friction"]) / sum_h if sum_h > 0 else 99.0
    fs_s_fric = sum_v * p["friction"] / sum_h if sum_h > 0 else 99.0
    x_r = (m_res - m_over) / sum_v if sum_v > 0 else 0.0  # natijaviy kuch toe dan
    e = B / 2 - x_r
    s_toe = sum_v / B * (1 + 6 * e / B) / 1000  # MPa
    s_heel = sum_v / B * (1 - 6 * e / B) / 1000
    return {
        "B": B,
        "h1": h1,
        "h2": h2,
        "W": W,
        "U": U,
        "sum_v": sum_v,
        "sum_h": sum_h,
        "m_res": m_res,
        "m_over": m_over,
        "fs_o": fs_o,
        "fs_s": fs_s,
        "fs_s_friction": fs_s_fric,
        "e": e,
        "x_r": x_r,
        "s_toe": s_toe,
        "s_heel": s_heel,
        "forces": forces,
        "overtopped": hw > H,
    }


def run(p: dict) -> dict:
    r = analyze(p)
    B = r["B"]
    seismic = p["kh"] > 0
    problems = []
    if r["fs_o"] < p["req_overturning"]:
        problems.append(f"ag'darilish zaxirasi {r['fs_o']:.2f} < {p['req_overturning']}")
    if r["fs_s"] < p["req_sliding"]:
        problems.append(f"sirpanish zaxirasi {r['fs_s']:.2f} < {p['req_sliding']}")
    if r["s_heel"] < 0 and not seismic:
        problems.append("yuqori tovonda cho'zilish (natijaviy kuch o'rta uchdan tashqarida)")
    if r["x_r"] < 0 or r["x_r"] > B:
        problems.append("natijaviy kuch tag chegarasidan tashqarida — ag'dariladi")
    if r["s_toe"] > p["allow_stress_mpa"]:
        problems.append(f"tovon kuchlanishi {r['s_toe']:.2f} MPa > ruxsat {p['allow_stress_mpa']}")
    if r["overtopped"]:
        problems.append("suv gerbdan oshib o'tadi")
    # Sath bo'yicha skanerlash (tagdan gerb+3 m gacha)
    levels, fs_o_l, fs_s_l, s_toe_l = [], [], [], []
    for i in range(41):
        lv = p["base_elev_m"] + (p["height_m"] + 3) * i / 40
        rr = analyze(p, headwater=lv)
        levels.append(round(lv, 2))
        fs_o_l.append(round(min(rr["fs_o"], 10), 3))
        fs_s_l.append(round(min(rr["fs_s"], 10), 3))
        s_toe_l.append(round(rr["s_toe"], 3))
    # Seysmik koeffitsient bo'yicha (0…0.5)
    khs, fs_o_k, fs_s_k = [], [], []
    for i in range(26):
        k = i * 0.02
        rr = analyze(p, kh=k)
        khs.append(round(k, 2))
        fs_o_k.append(round(min(rr["fs_o"], 10), 3))
        fs_s_k.append(round(min(rr["fs_s"], 10), 3))
    kh_crit = next((k for k, f in zip(khs, fs_s_k, strict=False) if f < 1.0), None)
    return {
        "series": {
            "level": levels,
            "fs_overturning": fs_o_l,
            "fs_sliding": fs_s_l,
            "sigma_toe": s_toe_l,
        },
        "seismic_scan": {"kh": khs, "fs_overturning": fs_o_k, "fs_sliding": fs_s_k},
        "forces": [
            {
                "name": n,
                "v_kn": round(v, 1),
                "h_kn": round(h, 1),
                "arm_v_m": round(av, 2),
                "arm_h_m": round(ah, 2),
            }
            for n, v, h, av, ah in r["forces"]
        ],
        "profile": {
            "points": _profile(
                p["height_m"], p["crest_width_m"], p["upstream_slope"], p["downstream_slope"]
            ),
            "h1": r["h1"],
            "h2": r["h2"],
        },
        "summary": {
            "base_width_m": round(B, 2),
            "weight_kn_m": round(r["W"], 0),
            "uplift_kn_m": round(r["U"], 0),
            "sum_v_kn_m": round(r["sum_v"], 0),
            "sum_h_kn_m": round(r["sum_h"], 0),
            "fs_overturning": round(r["fs_o"], 2),
            "fs_sliding": round(r["fs_s"], 2),
            "fs_sliding_friction_only": round(r["fs_s_friction"], 2),
            "eccentricity_m": round(r["e"], 2),
            "middle_third": abs(r["e"]) <= B / 6,
            "sigma_toe_mpa": round(r["s_toe"], 3),
            "sigma_heel_mpa": round(r["s_heel"], 3),
            "kh": p["kh"],
            "kh_critical": kh_crit,
            "verdict": "; ".join(problems) if problems else "Barqaror — barcha mezonlar bajarildi",
            "ok": not problems,
        },
    }
