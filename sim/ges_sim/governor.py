"""Gidroagregat–regulyator dinamikasi: HYGOV modeli (IEEE Std 421.5 / IEEE 1207, IEC 61362).

Regulyator (PI, vaqtinchalik va doimiy statizm):
  e = ω_ref − ω − R·(g − g_ref)            (isolyatsiyalangan tarmoq; R — doimiy statizm)
  dx/dt = (e − x)/T_f ... soddalashtirib: T_f filtri, vaqtinchalik statizm r bilan reset T_r:
  Regulyator holati: de/dt filtri T_f; c (buyruq) = ∫ e/(r·T_r) + e/r; servo: dg/dt = (c − g)/T_g, |dg/dt| ≤ V_elm, 0 ≤ g ≤ 1
Turbina (elastik bo'lmagan suv ustuni, Tw — suv ishga tushish vaqti):
  h = (q/g)²;  dq/dt = (1 − h)/T_w;  P_m = A_t·h·(q − q_nl) − D_turb·g·Δω
Tarmoq: izolyatsiyalangan yuk yoki cheksiz tarmoq:
  izolyatsiyalangan: 2H·dΔω/dt = P_m − P_L − D·Δω;   cheksiz tarmoq: Δω = 0, P_m ni kuzatamiz
Hodisalar: yuk qadam (ΔP_L), to'liq yuk tashlash (P_L → 0, ortiqcha tezlik), setpoint qadam.
Sozlash qoidalari (Hovey / Paynter): r ≈ 2.5·T_w/T_m (T_m = 2H), T_r ≈ 5·T_w; barqarorlik chegarasi T_w/T_m.
Ko'rsatkichlar: chastota maksimal og'ishi, o'rnashish vaqti (±0.2 %), tebranish so'nishi, gate max tezlik.
"""

from __future__ import annotations

from .schema import Field, Meta

META = Meta(
    id="governor",
    title="Agregat–regulyator dinamikasi (HYGOV)",
    description="Yuk qadam / yuk tashlash / setpoint o'zgarishida chastota, gate va quvvat javobi; regulyator "
    "sozlamalarini (statizm, T_r, T_g) ishga tushirishdan oldin sinash, barqarorlik va tavsiya (Hovey).",
    group="gidravlika",
    icon="activity",
    formulas=[
        "dq/dt = (1 − h)/T_w, h = (q/g)²",
        "P_m = A_t·h·(q − q_nl) − D_t·g·Δω",
        "2H·dΔω/dt = P_m − P_L − D·Δω",
        "r_tavsiya = 2.5·T_w/T_m, T_r = 5·T_w",
    ],
    outputs=[
        {"key": "freq_max_dev_pct", "label": "Chastota maks. og'ishi", "unit": "%"},
        {"key": "settling_s", "label": "O'rnashish vaqti", "unit": "s"},
        {"key": "overspeed_pct", "label": "Ortiqcha tezlik", "unit": "%"},
        {"key": "stable", "label": "Barqaror", "unit": ""},
    ],
)

FIELDS = [
    Field(
        "event",
        "Hodisa",
        type="select",
        default="load_step",
        options=(
            ("load_step", "Yuk qadam (izolyatsiyalangan tarmoq)"),
            ("rejection", "To'liq yuk tashlash (ortiqcha tezlik)"),
            ("setpoint", "Quvvat setpoint qadam (cheksiz tarmoq)"),
        ),
        group="Hodisa",
    ),
    Field(
        "step_pu",
        "Qadam kattaligi",
        "p.u.",
        default=0.1,
        min=-0.9,
        max=0.9,
        step=0.05,
        group="Hodisa",
        hint="yuk qadam: +0.1 = 10 % yuk qo'shildi",
    ),
    Field(
        "p0_pu",
        "Boshlang'ich yuk",
        "p.u.",
        default=0.8,
        min=0.05,
        max=1.0,
        step=0.05,
        group="Hodisa",
    ),
    Field(
        "tw",
        "Suv ishga tushish vaqti T_w",
        "s",
        default=1.5,
        min=0.2,
        max=6,
        step=0.1,
        group="Turbina",
        hint="T_w = L·v/(g·H): uzun quvur — katta",
    ),
    Field(
        "at",
        "Turbina kuchaytirish A_t",
        "",
        default=1.2,
        min=0.8,
        max=1.5,
        step=0.05,
        group="Turbina",
        advanced=True,
    ),
    Field(
        "qnl",
        "Bo'sh yurish sarfi q_nl",
        "p.u.",
        default=0.08,
        min=0,
        max=0.2,
        step=0.01,
        group="Turbina",
        advanced=True,
    ),
    Field(
        "dturb",
        "Turbina so'ndirishi D_turb",
        "",
        default=0.5,
        min=0,
        max=2,
        step=0.1,
        group="Turbina",
        advanced=True,
    ),
    Field(
        "h_inertia",
        "Inersiya doimiysi H",
        "s",
        default=3.5,
        min=1,
        max=10,
        step=0.1,
        group="Agregat",
        hint="gidroagregat 2–5 s",
    ),
    Field(
        "d_load",
        "Yuk so'ndirishi D",
        "",
        default=1.0,
        min=0,
        max=3,
        step=0.1,
        group="Agregat",
        advanced=True,
    ),
    Field(
        "r_perm",
        "Doimiy statizm R",
        "",
        default=0.05,
        min=0.01,
        max=0.1,
        step=0.005,
        group="Regulyator",
    ),
    Field(
        "r_temp",
        "Vaqtinchalik statizm r",
        "",
        default=0.4,
        min=0.05,
        max=2,
        step=0.05,
        group="Regulyator",
        hint="tavsiya 2.5·T_w/(2H)",
    ),
    Field(
        "tr",
        "Reset vaqti T_r",
        "s",
        default=6,
        min=0.5,
        max=30,
        step=0.5,
        group="Regulyator",
        hint="tavsiya 5·T_w",
    ),
    Field(
        "tf",
        "Filtr vaqti T_f",
        "s",
        default=0.05,
        min=0.01,
        max=1,
        step=0.01,
        group="Regulyator",
        advanced=True,
    ),
    Field("tg", "Servo vaqti T_g", "s", default=0.5, min=0.1, max=3, step=0.1, group="Regulyator"),
    Field(
        "velm",
        "Gate maks. tezligi",
        "p.u./s",
        default=0.15,
        min=0.02,
        max=1,
        step=0.01,
        group="Regulyator",
        hint="1/T_yopilish",
    ),
    Field(
        "gmax",
        "Gate maks. ochilish",
        "p.u.",
        default=1.0,
        min=0.5,
        max=1.0,
        step=0.05,
        group="Regulyator",
        advanced=True,
    ),
    Field("sim_s", "Hisob davomiyligi", "s", default=60, min=5, max=600, group="Hodisa"),
]


def run(p: dict) -> dict:
    tw, at, qnl, dt_ = p["tw"], p["at"], p["qnl"], p["dturb"]
    H, D = p["h_inertia"], p["d_load"]
    R, r, tr, tf, tg, velm, gmax = (
        p["r_perm"],
        p["r_temp"],
        p["tr"],
        p["tf"],
        p["tg"],
        p["velm"],
        p["gmax"],
    )
    event, step, p0 = p["event"], p["step_pu"], p["p0_pu"]
    infinite = event == "setpoint"
    # Boshlang'ich statsionar holat: h=1 → q=g; P_m = A_t·(g − q_nl) = p0 → g0
    g = q = p0 / at + qnl
    g = min(g, gmax)
    pl = p0
    dw = 0.0  # Δω, p.u.
    xf = 0.0  # filtrlangan xato
    xi = 0.0  # integral (vaqtinchalik statizm)
    g_ref = g
    p_ref = p0
    dt = 0.01
    n = int(p["sim_s"] / dt)
    ts, fs, gs, pms, qs = [], [], [], [], []
    t_event = 1.0
    max_rate = 0.0
    for i in range(n):
        t = i * dt
        if t >= t_event:
            if event == "load_step":
                pl = p0 + step
            elif event == "rejection":
                pl = 0.0
            elif event == "setpoint":
                p_ref = p0 + step
        # Regulyator xatosi
        if infinite:
            err = (
                (p_ref - pl_est(at, q, g, qnl)) * R * 5
            )  # quvvat regulyatori (soddalashtirilgan PI kirish)
        else:
            err = -dw - R * (g - g_ref)
        xf += dt * (err - xf) / tf
        xi += dt * xf / (r * tr)
        c = xi + xf / r + g_ref
        rate = max(min((c - g) / tg, velm), -velm)
        max_rate = max(max_rate, abs(rate))
        g = max(min(g + dt * rate, gmax), 0.0)
        # Turbina
        hq = (q / max(g, 1e-3)) ** 2
        q += dt * (1 - hq) / tw
        q = max(q, 0.0)
        pm = at * hq * (q - qnl) - dt_ * g * dw
        if not infinite:
            dw += dt * (pm - pl - D * dw) / (2 * H)
        if i % 5 == 0:
            ts.append(round(t, 2))
            fs.append(round(50 * (1 + dw), 4))
            gs.append(round(g, 4))
            pms.append(round(pm, 4))
            qs.append(round(q, 4))
    # Ko'rsatkichlar
    dev = [abs(f - 50) / 50 * 100 for f in fs]
    fmax = max(dev)
    i_ev = next((k for k, t in enumerate(ts) if t >= t_event), 0)
    # O'rnashish: yakuniy (statizm bilan siljigan) qiymatdan ±0.2 % ichida qolish
    f_final = fs[-1]
    tail = [abs(f - f_final) / 50 * 100 for f in fs[i_ev:]]
    settle = None
    for k in range(len(tail)):
        if all(x <= 0.2 for x in tail[k:]):
            settle = round(ts[i_ev + k] - t_event, 1)
            break
    # Barqarorlik: oxirgi chorakdagi tebranish amplitudasi kichik yoki oldingi chorakdan kamaygan
    q4 = len(fs) // 4
    last_q, prev_q = fs[-q4:], fs[-2 * q4 : -q4]
    p2p_last = (max(last_q) - min(last_q)) / 50 * 100
    p2p_prev = (max(prev_q) - min(prev_q)) / 50 * 100 if prev_q else p2p_last
    stable = infinite or p2p_last < 0.3 or p2p_last < 0.6 * p2p_prev
    steady_offset_pct = round((f_final - 50) / 50 * 100, 3)
    overspeed = max((f - 50) / 50 * 100 for f in fs)
    tm = 2 * H
    r_rec, tr_rec = 2.5 * tw / tm, 5 * tw
    notes = []
    if not stable:
        notes.append(
            "javob so'nmaydi (tebranish) — vaqtinchalik statizm r / T_r ni oshiring yoki T_w ni kamaytiring"
        )
    if event == "rejection" and overspeed > 50:
        notes.append(
            f"ortiqcha tezlik {overspeed:.0f} % > 50 % — gate yopilish tezligini oshiring (gidravlik zarbaga e'tibor!)"
        )
    if tw / tm > 0.5:
        notes.append(
            f"T_w/T_m = {tw / tm:.2f} > 0.5 — barqaror sozlash qiyin, bosim tenglashtiruvchi minora/inersiya kerak"
        )
    if abs(r - r_rec) / r_rec > 0.5 or abs(tr - tr_rec) / tr_rec > 0.5:
        notes.append(f"Hovey tavsiyasi: r ≈ {r_rec:.2f}, T_r ≈ {tr_rec:.1f} s (hozir {r}, {tr})")
    return {
        "series": {"t": ts, "frequency_hz": fs, "gate": gs, "p_mech": pms, "flow_pu": qs},
        "summary": {
            "freq_max_dev_pct": round(fmax, 3),
            "settling_s": settle,
            "overspeed_pct": round(overspeed, 2),
            "gate_rate_max": round(max_rate, 3),
            "stable": stable,
            "r_recommended": round(r_rec, 3),
            "tr_recommended_s": round(tr_rec, 1),
            "tw_tm_ratio": round(tw / tm, 3),
            "steady_offset_pct": steady_offset_pct,
            "verdict": "; ".join(notes)
            if notes
            else f"Barqaror: maks. og'ish {fmax:.2f} %, o'rnashish {settle if settle is not None else '>' + str(p['sim_s'])} s",
            "ok": stable and not notes,
        },
    }


def pl_est(at: float, q: float, g: float, qnl: float) -> float:
    hq = (q / max(g, 1e-3)) ** 2
    return at * hq * (q - qnl)
