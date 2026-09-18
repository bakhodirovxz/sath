"""Egizak vizualizatsiyasi uchun sof formulalar (bpy siz — pytest bilan sinaladi).

Manning (ochiq kanal, to'g'ri burchakli, normal chuqurlik):  Q = (1/n)·A·R^(2/3)·√S,  A = b·y,  R = b·y/(b + 2y).
Thoma kavitatsiya koeffitsienti:  σ = (H_atm − H_v − H_s) / H_net,  H_atm ≈ 10.1 m (0–500 m balandlik), H_v ≈ 0.24 m (20 °C);
  kritik σ_c (tur, solishtirma tezlik n_s = n·√P/H^1.25, P kVt): Francis 0.0432·(n_s/100)²  (USBR/Krivchenko),
  Kaplan 0.28 + (n_s/380)³, Pelton — kavitatsiya yo'q. σ < σ_c → kavitatsiya.
Sinxron tezlik:  n = 120·f/p  [ayl/min].
Generator FIK (turbine.py bilan bir xil):  P_loss = P_r(1/η_max − 1)·[k_fe + (1 − k_fe)·(P/P_r)²],  η = P/(P + P_loss).
Egri bosh quvur o'qi — ges_objects.penstock_path bilan bir xil (birlik: metr).
Zilzila: psevdo-spektral siljish  S_d = S_a·g·(T/2π)²  (Eurocode 8, 3.2.2.2);  u(t) = S_d·env(t)·sin(2πt/T),
  env — trapetsiya (Jennings–Housner–Tsai): ko'tarilish, tekis, eksponensial so'nish.
"""

from __future__ import annotations

import math

G = 9.80665
H_ATM = 10.1
H_VAPOR = 0.24


def manning_depth(q: float, width: float, slope: float, n: float) -> float:
    """Normal chuqurlik y (m), bisection; q ≤ 0 → 0."""
    if q <= 0 or width <= 0 or slope <= 0 or n <= 0:
        return 0.0

    def flow(y: float) -> float:
        a = width * y
        r = a / (width + 2 * y)
        return a * r ** (2 / 3) * math.sqrt(slope) / n

    lo, hi = 0.0, 1.0
    while flow(hi) < q and hi < 1e4:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        if flow(mid) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def synchronous_rpm(freq_hz: float, poles: int) -> float:
    return 120.0 * freq_hz / max(2, int(poles))


def specific_speed(n_rpm: float, p_kw: float, head_m: float) -> float:
    """n_s = n·√P/H^1.25 (metrik, P kVt)."""
    if p_kw <= 0 or head_m <= 0:
        return 0.0
    return n_rpm * math.sqrt(p_kw) / head_m**1.25


def thoma_sigma(suction_head_m: float, head_net_m: float) -> float:
    if head_net_m <= 0:
        return 0.0
    return (H_ATM - H_VAPOR - suction_head_m) / head_net_m


def sigma_critical(turbine_type: str, n_s: float) -> float:
    t = (turbine_type or "Francis").lower()
    if t == "pelton":
        return 0.0
    if t in ("kaplan", "bulb"):
        return 0.28 + (n_s / 380.0) ** 3
    return 0.0432 * (n_s / 100.0) ** 2


def cavitation(turbine_type: str, suction_head_m: float, head_net_m: float, n_rpm: float, p_kw: float) -> tuple[float, float, bool]:
    """(σ_plant, σ_c, kavitatsiya?)"""
    sp = thoma_sigma(suction_head_m, head_net_m)
    sc = sigma_critical(turbine_type, specific_speed(n_rpm, p_kw, head_net_m))
    return sp, sc, bool(sc > 0 and sp < sc)


def generator_efficiency(p_mw: float, rated_mva: float, eta_max: float = 0.985, iron_frac: float = 0.4) -> float:
    if p_mw <= 0 or rated_mva <= 0:
        return 0.0
    loss_rated = rated_mva * (1.0 / eta_max - 1.0)
    ratio = p_mw / rated_mva
    loss = loss_rated * (iron_frac + (1.0 - iron_frac) * ratio * ratio)
    return p_mw / (p_mw + loss)


def penstock_path(length: float, inclination_deg: float, bend_radius: float, outlet_length: float) -> dict:
    """Metrda: p0, p1, pm, p2, p3 (tuple), u1, alpha (rad), l1 — FreeCAD tomonidagi bilan bir xil."""
    a = math.radians(inclination_deg)
    arc = bend_radius * a
    l1 = max(length * 0.1, length - outlet_length - arc)
    u1 = (0.0, math.cos(a), -math.sin(a))
    n1 = (0.0, math.sin(a), math.cos(a))
    p0 = (0.0, 0.0, 0.0)
    p1 = (0.0, u1[1] * l1, u1[2] * l1)
    c = (0.0, p1[1] + n1[1] * bend_radius, p1[2] + n1[2] * bend_radius)
    p2 = (0.0, c[1], c[2] - bend_radius)
    nm = (0.0, n1[1], n1[2] + 1.0)
    k = math.hypot(nm[1], nm[2])
    pm = (0.0, c[1] - nm[1] / k * bend_radius, c[2] - nm[2] / k * bend_radius)
    p3 = (0.0, p2[1] + outlet_length, p2[2])
    return {"p0": p0, "p1": p1, "pm": pm, "p2": p2, "p3": p3, "u1": u1, "alpha": a, "l1": l1}


def penstock_samples(length: float, inclination_deg: float, bend_radius: float, outlet_length: float, n: int) -> list[tuple[float, float, float]]:
    """O'q bo'ylab n nuqta (kirishdan chiqishgacha teng yoy uzunligida) — bosim markerlari uchun."""
    if inclination_deg <= 0:
        return [(0.0, 0.0, length * i / max(1, n - 1)) for i in range(n)]
    p = penstock_path(length, inclination_deg, bend_radius, outlet_length)
    a, l1 = p["alpha"], p["l1"]
    arc = bend_radius * a
    total = l1 + arc + outlet_length
    c = (p["p1"][1] + math.sin(a) * bend_radius, p["p1"][2] + math.cos(a) * bend_radius)
    out = []
    for i in range(n):
        s = total * i / max(1, n - 1)
        if s <= l1:
            out.append((0.0, p["u1"][1] * s, p["u1"][2] * s))
        elif s <= l1 + arc:
            # yoy: markazdan boshlang'ich normal −n1 dan −z gacha buriladi
            phi = (s - l1) / bend_radius  # 0..a
            ang = a - phi  # markazdan nuqtaga yo'nalish: (−sin ang·?, ...) — n1 ni burish
            ny, nz = -math.sin(ang), -math.cos(ang)
            out.append((0.0, c[0] + ny * bend_radius, c[1] + nz * bend_radius))
        else:
            out.append((0.0, p["p2"][1] + (s - l1 - arc), p["p2"][2]))
    return out


def solve_penstock(dz: float, dy: float, bend_radius: float, outlet_length: float) -> tuple[float, float]:
    """Kirishdan chiqishgacha vertikal tushish dz (>0) va gorizontal masofa dy berilgan: (qiyalik °, umumiy uzunlik).
    Δz = L1·sin α + R(1 − cos α),  Δy = L1·cos α + R·sin α + L_out — α bo'yicha bisection."""
    dz, dy = max(dz, 0.01), max(dy, outlet_length + 0.01)

    def resid(a: float) -> float:
        l1 = (dz - bend_radius * (1 - math.cos(a))) / math.sin(a)
        return dy - bend_radius * math.sin(a) - outlet_length - l1 * math.cos(a)

    lo, hi = math.radians(0.5), math.radians(89.5)
    for _ in range(80):
        mid = (lo + hi) / 2
        if resid(mid) > 0:  # α katta → gorizontal masofa yetmaydi → α ni kamaytiramiz
            hi = mid
        else:
            lo = mid
    a = (lo + hi) / 2
    l1 = max(0.1, (dz - bend_radius * (1 - math.cos(a))) / math.sin(a))
    return math.degrees(a), l1 + bend_radius * a + outlet_length


def spectral_displacement(sa_g: float, period_s: float) -> float:
    return sa_g * G * (period_s / (2 * math.pi)) ** 2


def envelope(t: float, rise: float = 2.0, plateau: float = 8.0, decay: float = 6.0) -> float:
    if t < 0:
        return 0.0
    if t < rise:
        return (t / rise) ** 2
    if t < rise + plateau:
        return 1.0
    return math.exp(-3.0 * (t - rise - plateau) / decay) if t < rise + plateau + decay else 0.0


def ground_motion(sa_g: float, period_s: float, t: float, scale: float = 1.0) -> float:
    """u(t) siljish (m) — vizual ko'paytirgich scale bilan."""
    if period_s <= 0:
        return 0.0
    return spectral_displacement(sa_g, period_s) * envelope(t) * math.sin(2 * math.pi * t / period_s) * scale


def heat_color(theta_c: float) -> tuple[float, float, float, float]:
    """Harorat → rang: 40 ko'k → 80 yashil → 110 sariq → 140 qizil."""
    stops = [(40.0, (0.2, 0.45, 0.9)), (80.0, (0.23, 0.66, 0.39)), (110.0, (0.88, 0.66, 0.23)), (140.0, (0.85, 0.2, 0.15))]
    if theta_c <= stops[0][0]:
        return (*stops[0][1], 1.0)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
        if theta_c <= t1:
            k = (theta_c - t0) / (t1 - t0)
            return tuple(c0[i] + (c1[i] - c0[i]) * k for i in range(3)) + (1.0,)
    return (*stops[-1][1], 1.0)
