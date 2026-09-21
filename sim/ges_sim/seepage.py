"""Filtratsiya (suv sizishi) va suffoziya (piping) tekshiruvi.

Beton to'g'on — o'tkazuvchan asos: oqim to'ri GEOMETRIYADAN quriladi — Laplas tenglamasi ∇²φ = 0
  chekli farqlar bilan (tekis pol b, ponur, shpunt/parda d yuqori yoki quyi tomonda, o'tkazuvchan
  qatlam qalinligi T); sarf q = k·∮∂φ/∂n bo'yicha, chiqish gradiyenti — quyi byef tubida shpunt
  tovonidan keyingi birinchi kataklardagi maksimal vertikal gradient (Terzaghi/USACE EM 1110-2-1901
  §4: to'r bo'yicha i_e = Δh/Δl). Xosla (1936) G_E = (H/d)/(π√λ) faqat quyi shpunt va cheksiz chuqur
  asos uchun — tekshiruv/qiyoslash qiymati sifatida beriladi (`exit_gradient_khosla`).
Lane (1935) og'irlangan yo'l: C_w = (ΣL_v + ΣL_h/3)/H ≥ [C_w] — Lane jadvali: juda mayda qum/loyqa 8.5,
  mayda qum 7.0, o'rta qum 6.0, qo'pol qum 5.0, mayda shag'al 4.0, yirik shag'al 3.0, yumshoq gil 3.0,
  o'rta gil 2.0, qattiq gil 1.8. Xavfsiz chiqish gradiyenti (Khosla): shingil 1/4–1/5, qo'pol qum
  1/5–1/6, mayda qum 1/6–1/7. Qoya asos — bu mezonlar qo'llanilmaydi (sementatsiya pardasi bo'yicha alohida).
Filtr mezonlari (Terzaghi; USBR/NRCS): D15f/d85b ≤ 4 (zarralar o'tmasin), D15f/d15b ≥ 4 (o'tkazuvchanlik).
Tuproq to'g'on (bir jinsli, Dyupyui): q = k(h₁² − h₂²)/(2L); gorizontal (tovon) drenajga kirish
  gradiyenti (Casagrande): i_e = q/(k·L_d) — drenaj yuzasidan vertikal oqim; kritik (Terzaghi
  ko'tarilish) i_cr = (G_s − 1)/(1 + e); K = i_cr/i_e ≥ 1.5.
"""

from __future__ import annotations

import math

import numpy as np

from .schema import Field, Meta
from .validity import check_budget, check_range

SOILS = {  # kalit → (nom, Lane [C_w], Khosla xavfsiz chiqish gradiyenti)
    "very_fine_sand": ("Juda mayda qum / loyqa", 8.5, 1 / 7),
    "fine_sand": ("Mayda qum", 7.0, 1 / 6.5),
    "medium_sand": ("O'rta qum", 6.0, 1 / 5.5),
    "coarse_sand": ("Qo'pol qum", 5.0, 1 / 5),
    "gravel": ("Mayda shag'al", 4.0, 1 / 4.5),
    "coarse_gravel": ("Yirik shag'al", 3.0, 1 / 4),
    "clay": ("Gil (o'rta)", 2.0, 1 / 3),
    "hard_clay": ("Qattiq gil", 1.8, 1 / 3),
}

META = Meta(
    id="seepage",
    title="Filtratsiya va suffoziya (piping)",
    description="To'g'on tagidan/tanasidan suv sizishi: geometriyadan qurilgan oqim to'ri (Laplas, chekli farqlar) — "
    "sarf va chiqish gradiyenti; Lane yo'l koeffitsienti; filtr mezonlari; tuproq to'g'on uchun Dyupyui "
    "depressiya egri chizig'i va drenajga kirish gradiyenti.",
    group="mustahkamlik",
    icon="droplet",
    formulas=[
        "∇²φ = 0 (oqim to'ri, chekli farqlar); q = k·ΣΔφ/Δy",
        "C_w = (ΣL_v + ΣL_h/3)/H (Lane 1935)",
        "G_E = (H/d)/(π√λ) (Xosla, qiyoslash)",
        "D15f/d85b ≤ 4, D15f/d15b ≥ 4 (Terzaghi)",
        "q = k(h₁²−h₂²)/(2L); i_e = q/(k·L_d)",
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
        max=1,
        group="Umumiy",
        hint="qum 1e-4…1e-3; alevrit 1e-6; gil 1e-9",
    ),
    Field(
        "soil",
        "Asos grunti",
        type="select",
        default="gravel",
        options=tuple((k, v[0]) for k, v in SOILS.items()) + (("rock", "Qoya (mezonlar qo'llanilmaydi)"),),
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
        "cutoff_position",
        "Shpunt joylashuvi",
        type="select",
        default="downstream",
        options=(("downstream", "Quyi (toe) — chiqish gradiyentini kamaytiradi"), ("upstream", "Yuqori (poshna) — sarfni kamaytiradi")),
        group="Beton to'g'on",
    ),
    Field(
        "apron_m",
        "Ponur uzunligi (yuqori byef, gorizontal)",
        "m",
        default=40,
        min=0,
        group="Beton to'g'on",
    ),
    Field(
        "stratum_depth_m",
        "O'tkazuvchan qatlam qalinligi T (suv o'tkazmas tubgacha)",
        "m",
        default=30,
        min=1,
        group="Beton to'g'on",
        hint="Oqim to'ri shu chuqurlikda yopiladi; shpuntdan kamida 1.5 marta chuqur bo'lsin",
    ),
    Field(
        "extra_vertical_m",
        "Qo'shimcha vertikal yo'llar (ΣL_v, Lane uchun)",
        "m",
        default=0,
        min=0,
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
    Field("filter_d15_mm", "Filtr D15 (0 — tekshirilmasin)", "mm", default=0, min=0, group="Filtr"),
    Field("base_d85_mm", "Asos grunti d85", "mm", default=0.5, min=0.001, group="Filtr"),
    Field("base_d15_mm", "Asos grunti d15", "mm", default=0.1, min=0.0001, group="Filtr"),
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
        "Tovon drenaji uzunligi L_d (gorizontal)",
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


def flow_net(
    H: float,
    b: float,
    d: float,
    T: float,
    apron: float = 0.0,
    cutoff_downstream: bool = True,
    dx: float | None = None,
) -> dict:
    """Tekis pol (kengligi b, ponur `apron` yuqorida) + bitta shpunt (chuqurligi d) ostidagi
    o'tkazuvchan qatlamda (qalinligi T) statsionar filtratsiya: ∇²φ = 0, chekli farqlar (5 nuqtali),
    to'g'ridan-to'g'ri siyrak yechim. φ — pyezometrik napor (yuqori byef tubi H, quyi 0).

    Qaytaradi: q_over_kH (o'lchamsiz sarf q/(k·H)), i_exit (quyi tubda maksimal vertikal gradient,
    shpunt tovonidan keyingi 0.5·d oraliqda), va tarmoq (potentsiallar) ko'rish uchun."""
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve

    Lu, Ld = 3.0 * max(b, T), 3.0 * max(b, T)  # yon chegaralar (Neumann) ta'sir qilmasin
    dx = dx or max(min(b, T, d if d > 0 else T) / 12.0, 0.25)
    dx = min(dx, T / 8)
    x0, x1 = -(apron + Lu), b + Ld
    nx, ny = int(round((x1 - x0) / dx)) + 1, int(round(T / dx)) + 1
    check_budget(nx * ny * 5, "Oqim to'ri", "qatlam qalinligi T yoki tag kengligini kamaytiring")
    xs = x0 + dx * np.arange(nx)
    x_cut = b if cutoff_downstream else 0.0
    ic = int(round((x_cut - x0) / dx))  # shpunt ustunlar orasida: ic-1 | ic
    jd = int(round(d / dx))  # shpunt qatorlar 0..jd-1
    N = nx * ny
    idx = lambda i, j: j * nx + i  # noqa: E731
    A = lil_matrix((N, N))
    rhs = np.zeros(N)
    floor_i0, floor_i1 = int(round((-apron - x0) / dx)), int(round((b - x0) / dx))
    if cutoff_downstream:
        # pol shpunt devorida tugaydi (devor ic-1 | ic orasida) — chiqish devordan boshlanadi;
        # aks holda pol shpuntdan bir katak o'tib "erkin uch" singulyarligini hosil qiladi
        floor_i1 = ic - 1
    for j in range(ny):
        for i in range(nx):
            n = idx(i, j)
            if j == 0 and (i < floor_i0 or i > floor_i1):
                A[n, n] = 1.0
                rhs[n] = H if i < floor_i0 else 0.0  # Dirixle: byef tublari
                continue
            diag = 0.0
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + di, j + dj
                if ii < 0 or ii >= nx or jj < 0 or jj >= ny:
                    continue  # Neumann (yon/tub va pol ostida)
                if j == 0 and jj < 0:
                    continue
                # shpunt: ic-1 ↔ ic o'tish, qatorlar j < jd, taqiqlangan
                if dj == 0 and j < jd and {i, ii} == {ic - 1, ic}:
                    continue
                A[n, idx(ii, jj)] = 1.0
                diag -= 1.0
            A[n, n] = diag if diag != 0 else 1.0
    phi = spsolve(A.tocsr(), rhs).reshape(ny, nx)
    # Sarf: quyi byef tubi orqali chiqayotgan oqim, q/k = Σ (φ[1,i] − φ[0,i])/dx · dx = Σ Δφ
    exit_cols = range(floor_i1 + 1, nx)
    q_over_k = float(sum(phi[1, i] - phi[0, i] for i in exit_cols))
    grads = [(phi[1, i] - phi[0, i]) / dx for i in exit_cols]
    # Chiqish gradiyenti: shpunt tovonidan (toe) keyingi 0.5·d (kamida 3 katak) oralig'idagi maksimum
    n_look = max(int(0.5 * d / dx), 3)
    i_exit = float(max(grads[:n_look])) if grads else 0.0
    step = max(1, nx // 120)
    return {
        "q_over_kH": q_over_k / H,
        "i_exit": i_exit,
        "dx": dx,
        "x": [float(v) for v in xs[::step]],
        "y": [float(j * dx) for j in range(0, ny, max(1, ny // 40))],
        "phi": [[float(v) for v in row[::step]] for row in phi[:: max(1, ny // 40)]],
        "toe_gradients": [round(g, 4) for g in grads[: min(len(grads), 3 * n_look)]],
    }


def khosla_exit_gradient(H: float, b: float, d: float) -> float:
    """Xosla (1936): quyi shpunt, cheksiz chuqur asos: G_E = (H/d)/(π√λ), λ = (1+√(1+α²))/2, α = b/d."""
    alpha = b / d
    lam = (1 + math.sqrt(1 + alpha**2)) / 2
    return (H / d) / (math.pi * math.sqrt(lam))


def filter_check(d15f: float, d85b: float, d15b: float) -> list[str]:
    """Terzaghi filtr mezonlari (USACE EM 1110-2-1901 §D; USBR): qaytaradi bajarilmagan shartlar."""
    out = []
    if d15f / d85b > 4:
        out.append(f"D15f/d85b = {d15f / d85b:.1f} > 4 — asos zarralari filtrga o'tadi (suffoziya)")
    if d15f / d15b < 4:
        out.append(f"D15f/d15b = {d15f / d15b:.1f} < 4 — filtr yetarli o'tkazuvchan emas (bosim to'planadi)")
    return out


def run(p: dict) -> dict:
    H, k = p["head_m"], p["k_m_s"]
    warnings: list[str] = []
    if p["soil"] == "rock":
        raise ValueError(
            "qoya asos: Lane/Xosla va suffoziya mezonlari o'tkazuvchan gruntlar uchun — qoya uchun "
            "sementatsiya pardasi va drenaj bo'yicha alohida baho kerak (modul qo'llanilmaydi)"
        )
    soil_name, cw_req, ge_safe = SOILS[p["soil"]]
    filt = []
    if p["filter_d15_mm"] > 0:
        filt = filter_check(p["filter_d15_mm"], p["base_d85_mm"], p["base_d15_mm"])
    if p["dam_type"] == "concrete":
        b, d, T = p["base_width_m"], p["cutoff_m"], p["stratum_depth_m"]
        down = p["cutoff_position"] == "downstream"
        if T < 1.5 * d:
            warnings.append(
                f"o'tkazuvchan qatlam T = {T} m shpunt d = {d} m ga yaqin — to'r tub bilan chegaralangan, "
                "sarf kam ko'rsatilishi mumkin"
            )
        net = flow_net(H, b, d, T, p["apron_m"], down)
        q = k * H * net["q_over_kH"]  # m³/s / m
        ge = net["i_exit"]
        ge_kh = khosla_exit_gradient(H, b, d) if down else None
        lv = 2 * d + p["extra_vertical_m"]
        cw = (lv + (b + p["apron_m"]) / 3) / H
        fs = ge_safe / ge if ge > 0 else 99.0
        probs = []
        if cw < cw_req:
            probs.append(
                f"Lane koeffitsienti {cw:.1f} < {cw_req} ({soil_name}) — yo'lni uzaytiring (shpunt, ponur)"
            )
        if ge > ge_safe:
            probs.append(f"chiqish gradiyenti {ge:.3f} > xavfsiz {ge_safe:.3f} — suffoziya xavfi")
        probs += filt
        if not down:
            warnings.append(
                "shpunt yuqori (poshna) tomonda: chiqish gradiyenti to'rdan (quyi tub), Xosla qiyoslashi yo'q"
            )
        # Shpunt chuqurligi bo'yicha skanerlash (to'r bilan, siyrakroq to'r)
        ds = [round(max(0.5, d * 0.25) + (min(2.5 * d, 0.9 * T) - max(0.5, d * 0.25)) * i / 8, 2) for i in range(9)]
        ges, qs = [], []
        for dd in ds:
            nn = flow_net(H, b, dd, T, p["apron_m"], down, dx=max(net["dx"] * 2, 0.5))
            ges.append(round(nn["i_exit"], 4))
            qs.append(round(k * H * nn["q_over_kH"] * 1000, 3))
        return {
            "series": {"cutoff_m": ds, "exit_gradient": ges, "q_l_s_m": qs},
            "net": {"x": net["x"], "y": net["y"], "phi": net["phi"]},
            "summary": {
                "q_l_s_m": round(q * 1000, 3),
                "q_total_l_s": round(q * 1000 * p["dam_length_m"], 1),
                "shape_factor": round(net["q_over_kH"], 4),
                "lane_cw": round(cw, 2),
                "lane_required": cw_req,
                "exit_gradient": round(ge, 4),
                "exit_gradient_khosla": round(ge_kh, 4) if ge_kh is not None else None,
                "exit_gradient_safe": round(ge_safe, 3),
                "fs_piping": round(fs, 2),
                "verdict": "; ".join(probs)
                if probs
                else "Filtratsiya xavfsiz (Lane, chiqish gradiyenti va filtr mezonlari bajarildi)",
                "ok": not probs,
                "warnings": warnings,
            },
        }
    h1, h2, L = p["h1_m"], p["h2_m"], p["seep_length_m"]
    q = k * (h1**2 - h2**2) / (2 * L)
    xs = [round(L * i / 40, 2) for i in range(41)]
    # Dyupyui parabola: h(x)² = h₁² − (h₁² − h₂²)·x/L
    ys = [round(math.sqrt(max(h1**2 - (h1**2 - h2**2) * x / L, 0.0)), 3) for x in xs]
    # Gorizontal tovon drenajiga kirish gradiyenti (Casagrande): butun sarf drenaj yuzasi L_d orqali
    # vertikal kiradi → i_e = q/(k·L_d); kritik — Terzaghi ko'tarilish gradiyenti
    ld = min(p["drain_length_m"], L)
    i_exit = q / (k * ld)
    i_cr = (p["gs"] - 1) / (1 + p["void_ratio"])
    fs = i_cr / i_exit if i_exit > 0 else 99.0
    check_range(warnings, "L/h₁ (Dyupyui)", L / h1, 2.0, None, "", "Dyupyui taxmini L ≫ h", "depressiya chizig'i taxminiy")
    probs = []
    if fs < 1.5:
        probs.append(f"suffoziya zaxirasi {fs:.2f} < 1.5 — drenaj uzunligini oshiring / filtr")
    probs += filt
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
            "warnings": warnings,
        },
    }
