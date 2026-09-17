"""Yorilish xavfi: beton og'irlik to'g'onida kuchlanishlar balandlik bo'yicha (gravitatsion usul),
cho'zilish zonalari (yoriq boshlanishi), toe da ezilish, issiqlik yorilishi indeksi; tuproq to'g'onida
gidravlik yorilish va cho'kish yoriqlari.

Gravitatsion usul (USBR "Design of Gravity Dams", 1976; SNiP 2.06.06-85): har sathda y:
  ΣV = W_y + W_v − U_y (− k_v·W_y),  M — kesim markazi atrofida (yuqori yuzada cho'zilish musbat)
  σ_u = ΣV/B − 6M/B²,  σ_d = ΣV/B + 6M/B²   (siqilish musbat, MPa)
  Quyi yuzada bosh kuchlanish: σ_p = σ_d·(1 + m_d²) − p₂·m_d²
  Yoriq: σ_u < −R_bt (hisobiy cho'zilish qarshiligi); statik holda har qanday cho'zilish — xavf zonasi.
  Westergaard (sathdan yuqori qism): P_e(y) = (7/12)·k_h·γ_w·√h₁·(h₁−y)^1.5, 0.4(h₁−y) balandlikda.
Issiqlik (JCI "Guidelines for control of cracking of mass concrete", 2016; ACI 207):
  ΔT_ad = q·C (q — sement turi, C kg/m³),  T_max = T_qo'yish + 0.85·ΔT_ad,  ΔT = T_max − T_muhit
  σ_T = K_R · E/(1+φ) · α · ΔT,   I_cr = R_btn/σ_T:  ≥1.5 yoriq yo'q; 1.2–1.5 ehtimol; <1.2 kutiladi
Tuproq to'g'on: gidravlik yorilish K = σ'_v·A_ark/u ≥ 1.3 (A_ark — arka effekti 0.5–0.9, tor yadro);
  cho'kish yorig'i: ko'ndalang yoriq abutment yonida — cho'kish gradiyenti > 1 % (Sherard, 1973).
"""

from __future__ import annotations

import math

from . import materials
from .dam_stability import GAMMA_W, _area_centroid, _profile
from .schema import Field, Meta

META = Meta(
    id="cracking",
    title="Yorilish xavfi (qayerda va qachon)",
    description="Beton to'g'on: balandlik bo'yicha kuchlanishlar, cho'zilish (yoriq) zonalari, toe ezilishi, "
    "issiqlik yorilishi indeksi; tuproq to'g'on: gidravlik yorilish va cho'kish yoriqlari. "
    "Eng moyil joylar ro'yxati va beton klassi tanlovi.",
    group="mustahkamlik",
    icon="shield-alert",
    formulas=[
        "σ_u,d = ΣV/B ∓ 6M/B² (gravitatsion usul)",
        "σ_p = σ_d(1+m_d²) − p₂m_d²",
        "ΔT_ad = q·C; σ_T = K_R·E/(1+φ)·α·ΔT; I_cr = R_btn/σ_T",
        "K_gf = σ'_v·A_ark/u (gidravlik yorilish)",
    ],
    viz={"color_by": "dam", "water_level": "headwater_m", "field": "dam"},
    outputs=[
        {"key": "max_tension_mpa", "label": "Maks. cho'zilish (yuqori yuza)", "unit": "MPa"},
        {"key": "max_compression_mpa", "label": "Maks. siqilish (quyi yuza)", "unit": "MPa"},
        {"key": "thermal_index", "label": "Issiqlik yorilishi indeksi", "unit": ""},
        {"key": "crack_zone_pct", "label": "Yoriq zonasi (balandlikdan)", "unit": "%"},
    ],
)

FIELDS = [
    Field(
        "dam_type",
        "To'g'on turi",
        type="select",
        default="concrete",
        options=(("concrete", "Beton og'irlik"), ("earth", "Tuproq (yadroli)")),
        group="Umumiy",
    ),
    Field("height_m", "Balandlik H", "m", default=80, min=1, group="Profil", model="dam.height_m"),
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
        "Yuqori yuza qiyaligi m_u",
        "",
        default=0.05,
        min=0,
        max=1.5,
        step=0.05,
        group="Profil",
    ),
    Field(
        "downstream_slope",
        "Quyi yuza qiyaligi m_d",
        "",
        default=0.75,
        min=0,
        max=2,
        step=0.05,
        group="Profil",
    ),
    Field(
        "concrete_class",
        "Beton klassi (massiv)",
        type="select",
        default="B20",
        options=materials.concrete_options(),
        group="Material",
    ),
    Field(
        "face_class",
        "Beton klassi (yuqori yuza zonasi)",
        type="select",
        default="B25",
        options=materials.concrete_options(),
        group="Material",
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
    Field(
        "drain_eff",
        "Drenaj samaradorligi E",
        "",
        default=0.5,
        min=0,
        max=0.9,
        step=0.05,
        group="Sathlar",
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
        hint="«Zilzila ta'siri» dan; 0 — statik",
    ),
    Field(
        "cement_kg_m3",
        "Sement miqdori C",
        "kg/m³",
        default=220,
        min=80,
        max=500,
        group="Issiqlik",
        hint="massiv 150–250; yuza 280–350",
    ),
    Field(
        "cement_type",
        "Sement turi",
        type="select",
        default="cem2",
        options=tuple((k, v["name"]) for k, v in materials.CEMENT.items()),
        group="Issiqlik",
    ),
    Field(
        "place_temp", "Beton qo'yish harorati", "°C", default=18, min=-5, max=40, group="Issiqlik"
    ),
    Field(
        "ambient_temp",
        "Barqarorlashgan (o'rtacha yillik) harorat",
        "°C",
        default=12,
        min=-40,
        max=45,
        group="Issiqlik",
    ),
    Field(
        "restraint",
        "Cheklov koeffitsienti K_R",
        "",
        default=0.5,
        min=0.1,
        max=1.0,
        step=0.05,
        group="Issiqlik",
        hint="asosga yaqin blok 0.8–1.0; balandda 0.3–0.5",
    ),
    Field(
        "creep",
        "Sudralish koeffitsienti φ",
        "",
        default=2.0,
        min=0,
        max=3,
        step=0.1,
        group="Issiqlik",
        advanced=True,
    ),
    # Tuproq to'g'on
    Field(
        "core_width_base_m", "Yadro kengligi tagda", "m", default=30, min=1, group="Tuproq to'g'on"
    ),
    Field(
        "core_width_top_m", "Yadro kengligi tepada", "m", default=6, min=0.5, group="Tuproq to'g'on"
    ),
    Field(
        "core_gamma",
        "Yadro grunti og'irligi",
        "kN/m³",
        default=19,
        min=14,
        max=24,
        step=0.5,
        group="Tuproq to'g'on",
    ),
    Field(
        "arching",
        "Arka effekti koeffitsienti A_ark",
        "",
        default=0.7,
        min=0.3,
        max=1.0,
        step=0.05,
        group="Tuproq to'g'on",
        hint="tor yadro 0.5–0.7; keng 0.9",
    ),
    Field(
        "settlement_pct",
        "Kutilayotgan cho'kish",
        "% H",
        default=1.0,
        min=0,
        max=5,
        step=0.1,
        group="Tuproq to'g'on",
        hint="tosh to'kma 0.2–0.5; tuproq 1–2",
    ),
    Field(
        "abutment_slope_deg",
        "Abutment (yon) qiyaligi",
        "°",
        default=40,
        min=5,
        max=85,
        group="Tuproq to'g'on",
    ),
]


def _stress_profile(p: dict, cls_mass: dict, cls_face: dict) -> dict:
    H, bc, mu, md = p["height_m"], p["crest_width_m"], p["upstream_slope"], p["downstream_slope"]
    gc = cls_mass["gamma"]
    h1 = max(min(p["headwater_m"] - p["base_elev_m"], H + 3), 0.0)
    h2 = max(min(p["tailwater_m"] - p["base_elev_m"], H), 0.0)
    kh, E = p["kh"], p["drain_eff"]
    B0 = mu * H + bc + md * H
    xu = lambda y: mu * y  # noqa: E731
    xd = lambda y: mu * H + bc + md * (H - y)  # noqa: E731
    n = 40
    levels, s_u, s_d, s_p, allow_t = [], [], [], [], []
    crack_levels = []
    for i in range(n + 1):
        y = H * i / n
        if y >= H - 1e-9:
            break
        # Sathdan yuqori ko'pburchak (kesim y dan gerbgacha)
        poly = [(xu(y), y), (xd(y), y), (xd(H), H), (xu(H), H)]
        area, xg, yg = _area_centroid(poly)
        B = xd(y) - xu(y)
        xc = xu(y) + B / 2
        W = gc * area
        V = W
        M = W * (
            xg - xc
        )  # og'irlik markazi kesim markazidan pastga (downstream) bo'lsa yuqori yuzada cho'zilish
        d1 = max(h1 - y, 0.0)
        d2 = max(h2 - y, 0.0)
        if d1 > 0:
            P = GAMMA_W * d1**2 / 2
            M += P * d1 / 3
            if mu > 0:
                Wv = GAMMA_W * mu * d1**2 / 2
                V += Wv
                M += Wv * (xu(y) + mu * d1 / 3 - xc)
        if d2 > 0:
            P2 = GAMMA_W * d2**2 / 2
            M -= P2 * d2 / 3
        # Filtratsion bosim kesimda: yuqori yuzada γ_w·d1, drenaj chizig'ida kamaygan, quyi yuzada γ_w·d2
        pu, pd = GAMMA_W * d1, GAMMA_W * d2
        p_dr = pd + (1 - E) * (pu - pd)
        # trapetsiya: yuqori yuzadan drenajgacha (B·0.1) va drenajdan quyigacha
        xdr = 0.1 * B
        U1 = (pu + p_dr) / 2 * xdr
        U2 = (p_dr + pd) / 2 * (B - xdr)
        x1 = xu(y) + xdr * (pu + 2 * p_dr) / (3 * (pu + p_dr)) if (pu + p_dr) > 0 else xu(y)
        x2 = (
            xu(y) + xdr + (B - xdr) * (p_dr + 2 * pd) / (3 * (p_dr + pd))
            if (p_dr + pd) > 0
            else xu(y) + xdr
        )
        U = U1 + U2
        V -= U
        M -= U1 * (x1 - xc) + U2 * (x2 - xc)
        if kh > 0:
            M += kh * W * (yg - y)
            if d1 > 0:
                Pe = 7 / 12 * kh * GAMMA_W * math.sqrt(h1) * d1**1.5
                M += Pe * 0.4 * d1
        su = (V / B - 6 * M / B**2) / 1000  # MPa
        sd = (V / B + 6 * M / B**2) / 1000
        sp = sd * (1 + md**2) - (pd / 1000) * md**2
        levels.append(round(p["base_elev_m"] + y, 2))
        s_u.append(round(su, 3))
        s_d.append(round(sd, 3))
        s_p.append(round(sp, 3))
        ft = (
            cls_face["Rbt"] if y < 4 else cls_mass["Rbt"]
        )  # yuza zonasi tagda ham massiv klass bo'lishi mumkin
        allow_t.append(-round(ft, 3))
        if su < 0:
            crack_levels.append((y, su, ft))
    return {
        "levels": levels,
        "sigma_up": s_u,
        "sigma_down": s_d,
        "sigma_principal_down": s_p,
        "allow_tension": allow_t,
        "cracks": crack_levels,
        "B0": B0,
        "h1": h1,
        "h2": h2,
    }


def _thermal(p: dict, cls: dict) -> dict:
    cem = materials.CEMENT[p["cement_type"]]
    dT_ad = cem["q"] * p["cement_kg_m3"]
    t_max = p["place_temp"] + 0.85 * dT_ad
    dT = max(t_max - p["ambient_temp"], 0.0)
    E_eff = cls["E"] / (1 + p["creep"])
    sigma_t = p["restraint"] * E_eff * materials.ALPHA_CONCRETE * dT
    idx = cls["Rbtn"] / sigma_t if sigma_t > 0 else 9.9
    if idx >= 1.5:
        risk, prob = "past", 5
    elif idx >= 1.2:
        risk, prob = "o'rtacha", 30
    elif idx >= 1.0:
        risk, prob = "yuqori", 60
    else:
        risk, prob = "juda yuqori", 85
    # Ruxsat etilgan ΔT (I=1.5 uchun) → tavsiya: sovutish / sement kamaytirish
    dT_allow = cls["Rbtn"] / (1.5 * p["restraint"] * E_eff * materials.ALPHA_CONCRETE)
    c_allow = max((dT_allow + p["ambient_temp"] - p["place_temp"]) / (0.85 * cem["q"]), 0.0)
    return {
        "dT_adiabatic": round(dT_ad, 1),
        "t_max": round(t_max, 1),
        "dT": round(dT, 1),
        "sigma_t_mpa": round(sigma_t, 3),
        "index": round(min(idx, 9.9), 2),
        "risk": risk,
        "probability_pct": prob,
        "dT_allow": round(dT_allow, 1),
        "cement_allow_kg_m3": round(c_allow, 0),
        "cement": cem["name"],
    }


def _earth(p: dict) -> dict:
    H = p["height_m"]
    h1 = max(min(p["headwater_m"] - p["base_elev_m"], H), 0.0)
    levels, k_hf, zones = [], [], []
    n = 20
    for i in range(n + 1):
        y = H * i / n
        depth = H - y
        u = GAMMA_W * max(h1 - y, 0.0)  # suv bosimi yadroda (to'la sath)
        # Vertikal effektiv kuchlanish: yadro og'irligi minus arka (tor yadro prizmalarga osilib qoladi)
        w = max(
            p["core_width_base_m"] + (p["core_width_top_m"] - p["core_width_base_m"]) * y / H, 0.5
        )
        sigma_v = p["core_gamma"] * depth * (p["arching"] if w / max(depth, 1) < 1.0 else 1.0)
        k = sigma_v / u if u > 0 else 9.9
        levels.append(round(p["base_elev_m"] + y, 2))
        k_hf.append(round(min(k, 9.9), 2))
        if u > 0 and k < 1.3:
            zones.append(round(p["base_elev_m"] + y, 1))
    # Cho'kish gradiyenti abutment yonida: s = settlement% · H; gorizontal masofa ≈ H / tan(β)
    s = p["settlement_pct"] / 100 * H
    L = H / math.tan(math.radians(p["abutment_slope_deg"]))
    grad = s / L * 100 if L > 0 else 99
    transverse = grad > 1.0
    return {
        "levels": levels,
        "k_hydraulic": k_hf,
        "hf_zones": zones,
        "settlement_m": round(s, 2),
        "settlement_gradient_pct": round(grad, 2),
        "transverse_crack": transverse,
    }


def _risk_field(
    by_height: list[float],
    nx: int = 24,
    crest_extra: float = 0.0,
    abutment_extra: float = 0.25,
    thermal: float = 0.0,
) -> dict:
    """Yuqori yuza uchun yoriq xavfi xaritasi (0..1): balandlik bo'yicha hisoblangan qiymat + qirg'oq
    (abutment) yaqinida kuchlanish konsentratsiyasi + gerb (zilzila) + issiqlik. Web 3D da to'g'on yuzasiga
    rangli maydon sifatida chiziladi (chapdan o'ngga — uzunlik, pastdan yuqoriga — balandlik)."""
    ny = max(len(by_height), 2)
    vals: list[float] = []
    for j in range(ny):
        base = by_height[min(j, len(by_height) - 1)] if by_height else 0.0
        frac = j / (ny - 1)
        for i in range(nx):
            x = i / (nx - 1)
            edge = max(0.0, 1.0 - min(x, 1.0 - x) / 0.15)  # 15 % chetlarda 1 → markazda 0
            v = base * (1.0 + abutment_extra * edge) + thermal * (0.5 + 0.5 * edge)
            if frac > 0.85:
                v += crest_extra * (frac - 0.85) / 0.15
            vals.append(round(min(max(v, 0.0), 1.0), 3))
    return {
        "nx": nx,
        "ny": ny,
        "values": vals,
        "legend": "Yoriq xavfi: ko'k — past, qizil — yuqori",
    }


def run(p: dict) -> dict:
    prone: list[dict] = []
    if p["dam_type"] == "earth":
        e = _earth(p)
        probs = []
        if e["hf_zones"]:
            probs.append(
                f"gidravlik yorilish xavfi (K < 1.3) {e['hf_zones'][0]}–{e['hf_zones'][-1]} m sathlarda — yadro ustki qismi"
            )
            prone.append(
                {
                    "where": "Yadro yuqori qismi (tor yadro, arka effekti)",
                    "why": "vertikal effektiv kuchlanish suv bosimidan kam — yoriq suv bilan ochiladi",
                    "severity": "yuqori",
                }
            )
        if e["transverse_crack"]:
            probs.append(
                f"ko'ndalang cho'kish yoriqlari: cho'kish gradiyenti {e['settlement_gradient_pct']:.1f} % > 1 % (abutmentlar yonida)"
            )
            prone.append(
                {
                    "where": "Gerb — abutmentlar (yon qirg'oq) yaqinida",
                    "why": "notekis cho'kish, tik abutment",
                    "severity": "yuqori",
                }
            )
        prone += [
            {
                "where": "Yadro–filtr–prizma chegarasi",
                "why": "materiallar bikrligi farqi, ichki eroziya (suffoziya)",
                "severity": "o'rtacha",
            },
            {
                "where": "Gerb bo'ylab (uzunasiga)",
                "why": "yuqori/quyi prizmalarning turlicha cho'kishi, qurish",
                "severity": "o'rtacha",
            },
            {
                "where": "Quvurlar/galereya atrofi",
                "why": "qattiq element atrofida zichlanmaydi",
                "severity": "o'rtacha",
            },
        ]
        return {
            "field": _risk_field(
                [max(1.3 - k, 0.0) / 1.3 for k in e["k_hydraulic"]],  # K < 1.3 → xavf
                abutment_extra=0.5 if e["transverse_crack"] else 0.2,
            ),
            "series": {"level": e["levels"], "k_hydraulic": e["k_hydraulic"]},
            "prone": prone,
            "summary": {
                "settlement_m": e["settlement_m"],
                "settlement_gradient_pct": e["settlement_gradient_pct"],
                "min_k_hydraulic": min(e["k_hydraulic"]),
                "verdict": "; ".join(probs)
                if probs
                else "Gidravlik yorilish va cho'kish yoriqlari xavfi past",
                "ok": not probs,
            },
        }

    cls_mass = materials.concrete(p["concrete_class"])
    cls_face = materials.concrete(p["face_class"])
    sp = _stress_profile(p, cls_mass, cls_face)
    th = _thermal(p, cls_mass)
    H = p["height_m"]
    probs = []
    min_su = min(sp["sigma_up"])
    max_sd = max(sp["sigma_principal_down"])
    cracks = sp["cracks"]
    zone_pct = 0.0
    if cracks:
        ys = [c[0] for c in cracks]
        zone_pct = (max(ys) - min(ys) + H / 40) / H * 100
        worst = min(cracks, key=lambda c: c[1])
        opened = [c for c in cracks if c[1] < -c[2]]
        loc = f"{p['base_elev_m'] + min(ys):.1f}–{p['base_elev_m'] + max(ys):.1f} m"
        if opened:
            probs.append(
                f"yuqori yuzada YORIQ: cho'zilish {-worst[1]:.2f} MPa > R_bt {worst[2]:.2f} MPa ({loc})"
            )
            prone.append(
                {
                    "where": f"Yuqori tovon / yuqori yuza, {loc}",
                    "why": "cho'zilish kuchlanishi beton qarshiligidan yuqori — yoriq ochiladi, filtratsion bosim to'liq kiradi",
                    "severity": "kritik",
                }
            )
        else:
            probs.append(
                f"yuqori yuzada cho'zilish {-worst[1]:.2f} MPa ({loc}) — statik holda ruxsat etilmaydi (o'rta uch qoidasi)"
            )
            prone.append(
                {
                    "where": f"Yuqori tovon, {loc}",
                    "why": "cho'zilish zonasi — mikroyoriqlar, sizish",
                    "severity": "yuqori",
                }
            )
    if max_sd > cls_mass["Rb"]:
        probs.append(
            f"quyi yuzada (toe) bosh kuchlanish {max_sd:.2f} MPa > R_b {cls_mass['Rb']} MPa — ezilish"
        )
        prone.append(
            {
                "where": "Quyi tovon (toe) — quyi yuza tagida",
                "why": "maksimal siqilish; beton klassi yetarli emas",
                "severity": "kritik",
            }
        )
    elif max_sd > 0.6 * cls_mass["Rb"]:
        prone.append(
            {
                "where": "Quyi tovon (toe)",
                "why": f"siqilish R_b ning {max_sd / cls_mass['Rb'] * 100:.0f} % i",
                "severity": "o'rtacha",
            }
        )
    if th["index"] < 1.2:
        probs.append(
            f"issiqlik yorilishi kutiladi: I_cr = {th['index']} (ΔT = {th['dT']} °C, σ_T = {th['sigma_t_mpa']} MPa); "
            + (
                f"sement ≤ {th['cement_allow_kg_m3']:.0f} kg/m³"
                if th["cement_allow_kg_m3"] > 80
                else "oldindan sovutish (muz/sovuq suv), quvurli sovutish, yupqa qatlamlar, past issiqlikli sement"
            )
        )
        prone.append(
            {
                "where": "Asosga yaqin bloklar (birinchi 0.2H), yuza qatlami",
                "why": "asos cheklovi + sovuq davrda yuza sovishi → uzunasiga/ko'ndalang issiqlik yoriqlari",
                "severity": "yuqori",
            }
        )
    elif th["index"] < 1.5:
        prone.append(
            {
                "where": "Blok yuzalari, ko'ndalang choklar",
                "why": f"issiqlik indeksi {th['index']} — cheklangan yoriqlar ehtimoli",
                "severity": "o'rtacha",
            }
        )
    prone += [
        {
            "where": "Galereyalar va teshiklar atrofi",
            "why": "kuchlanish konsentratsiyasi (2–3 marta)",
            "severity": "o'rtacha",
        },
        {
            "where": "Quyi yuza qiyaligi o'zgargan joy (gerb osti)",
            "why": "geometrik konsentrator, zilzilada gerb tezlanishi 3–5 marta katta",
            "severity": "o'rtacha" if p["kh"] > 0 else "past",
        },
        {
            "where": "Ko'ndalang (temperatura) choklar",
            "why": "mavsumiy harorat, monolitlanmasa sizish",
            "severity": "past",
        },
    ]
    # Tavsiya: beton klassi
    need_ft = max(-min_su, 0)
    rec = next(
        (
            k
            for k, v in materials.CONCRETE.items()
            if v["Rbt"] >= need_ft * 1.2 and v["Rb"] >= max_sd * 1.5
        ),
        "B60",
    )
    return {
        "field": _risk_field(
            [
                max(-s, 0.0) / max(a, 1e-6)  # cho'zilish / ruxsat etilgan → 0..1+
                for s, a in zip(sp["sigma_up"], sp["allow_tension"], strict=False)
            ],
            crest_extra=0.35 if p["kh"] > 0 else 0.0,
            thermal=max(0.0, 1.0 - th["index"] / 1.5) * 0.6,
        ),
        "series": {
            "level": sp["levels"],
            "sigma_up": sp["sigma_up"],
            "sigma_down": sp["sigma_down"],
            "sigma_principal_down": sp["sigma_principal_down"],
            "allow_tension": sp["allow_tension"],
        },
        "thermal": th,
        "prone": prone,
        "profile": {
            "points": _profile(H, p["crest_width_m"], p["upstream_slope"], p["downstream_slope"]),
            "h1": sp["h1"],
            "h2": sp["h2"],
        },
        "summary": {
            "max_tension_mpa": round(max(-min_su, 0.0), 3),
            "max_compression_mpa": round(max_sd, 3),
            "concrete_Rbt": cls_mass["Rbt"],
            "concrete_Rb": cls_mass["Rb"],
            "crack_zone_pct": round(zone_pct, 1),
            "thermal_index": th["index"],
            "thermal_risk": th["risk"],
            "thermal_dT": th["dT"],
            "recommended_class": rec,
            "verdict": "; ".join(probs)
            if probs
            else "Cho'zilish zonasi yo'q, toe siqilishi va issiqlik indeksi qoniqarli — yoriq kutilmaydi",
            "ok": not probs,
        },
    }
