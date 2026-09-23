"""Suv ombori suv balansi: kiruvchi sarf → sath, hajm, tashlama.

Sath-hovuz marshrutlash (level-pool routing), o'zgartirilgan Puls / "storage-indication" usuli
(Chow, Maidment & Mays, "Applied Hydrology", 1988, 8.2 "Level pool routing"; USACE EM 1110-2-1417):
    (2S₂/Δt + O₂) = (I₁ + I₂) + (2S₁/Δt − O₁)
ya'ni dS/dt = I − O(S) ning trapetsiya (Krank–Nikolson) implicit sxemasi — 2-tartibli aniqlik,
har qanday Δt da barqaror. Holatga bog'liq HAMMA hadlar O(S) ichida qadam boshi VA oxirida
baholanadi: suv tashlagich Q(H), bug'lanish E·A(S) (yuza sathga bog'liq), filtratsiya, boshqa chiqim.
S₂ monoton tenglamadan (g(S₂) = 0) chegaralangan sekant (Illinois) usuli bilan aniq topiladi —
belgilangan iteratsiya soni yo'q. Turbina sarfi — boshqaruv qarori (qadam ichida doimiy), o'lik
hajmdan pastga tushirmaydigan qilib cheklanadi. Kiruvchi sarf qadam ichida doimiy (I₁ = I₂).
Massa balansi yopiq (`mass_residual_m3` ≈ 0), hajm manfiy bo'lsa xato (jim nol emas). Suv tashlagich formulasi — `spillway.py` (flood.py bilan bir xil).
Sath–hajm bog'liqligi nuqtalar bilan (batimetriya), chiziqli interpolyatsiya.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .climate import ClimateSpec, is_ice, open_water_evaporation_mm_day
from .spillway import Spillway


@dataclass(frozen=True)
class StorageCurve:
    """Sath (m, abs) ↔ hajm (mln m³). Nuqtalar sath bo'yicha o'sib borishi kerak."""

    elevations_m: tuple[float, ...]
    volumes_mcm: tuple[float, ...]

    def __post_init__(self):
        if len(self.elevations_m) < 2 or len(self.elevations_m) != len(self.volumes_mcm):
            raise ValueError("Kamida 2 nuqta, sath va hajm soni teng bo'lishi kerak")
        if any(b <= a for a, b in zip(self.elevations_m, self.elevations_m[1:], strict=False)):
            raise ValueError("Sathlar qat'iy o'sib borishi kerak")
        if any(b < a for a, b in zip(self.volumes_mcm, self.volumes_mcm[1:], strict=False)):
            raise ValueError("Hajm kamaymasligi kerak")

    def volume(self, elev: float) -> float:
        """m³ (chegaradan tashqarida chetki nishab bilan davom etadi)."""
        if self.elevations_m[0] <= elev <= self.elevations_m[-1]:
            return float(np.interp(elev, self.elevations_m, self.volumes_mcm)) * 1e6
        return self._extrap_volume(elev)

    def elevation(self, volume_m3: float) -> float:
        v = volume_m3 / 1e6
        if self.volumes_mcm[0] <= v <= self.volumes_mcm[-1]:
            return float(np.interp(v, self.volumes_mcm, self.elevations_m))
        return self._extrap_elev(v)

    def _slope(self, top: bool) -> float:
        e, v = self.elevations_m, self.volumes_mcm
        de = (e[-1] - e[-2]) if top else (e[1] - e[0])
        dv = (v[-1] - v[-2]) if top else (v[1] - v[0])
        return max(dv / de, 1e-9)  # mln m³ / m

    def _extrap_volume(self, elev: float) -> float:
        if elev < self.elevations_m[0]:
            return (
                max(self.volumes_mcm[0] - self._slope(False) * (self.elevations_m[0] - elev), 0.0)
                * 1e6
            )
        return (self.volumes_mcm[-1] + self._slope(True) * (elev - self.elevations_m[-1])) * 1e6

    def _extrap_elev(self, v_mcm: float) -> float:
        if v_mcm < self.volumes_mcm[0]:
            return self.elevations_m[0] - (self.volumes_mcm[0] - v_mcm) / self._slope(False)
        return self.elevations_m[-1] + (v_mcm - self.volumes_mcm[-1]) / self._slope(True)

    @classmethod
    def prismatic(cls, bottom_m: float, top_m: float, area_km2: float) -> StorageCurve:
        """Doimiy yuza (sinov va taxminiy hisoblar uchun)."""
        return cls((bottom_m, top_m), (0.0, area_km2 * (top_m - bottom_m)))


def SpillwaySpec(  # noqa: N802 — eski nom saqlanadi (scenario, testlar)
    crest_m: float,
    width_m: float,
    coefficient: float = 0.49,
    gate_opening: float = 1.0,
    **kw,
) -> Spillway:
    """`spillway.Spillway` ga o'tish: coefficient → m; qo'shimcha (bays, pier, approach_area_m2,
    gate_height_m ...) kw orqali."""
    return Spillway(crest_m, width_m, m=coefficient, gate_opening=gate_opening, **kw)


@dataclass(frozen=True)
class ReservoirSpec:
    curve: StorageCurve
    dead_level_m: float  # o'lik hajm sathi — turbinalar undan past suv ololmaydi
    normal_level_m: float  # NPU — normal to'ldirish sathi
    max_level_m: float | None = None  # FPU — majburiy sath (berilmasa NPU + 2)
    spillway: Spillway | None = None
    tailwater_m: float = 0.0  # quyi byef sathi (napor = sath − tailwater)
    other_outflow_m3s: float = 0.0  # sug'orish, ekologik oqim va h.k.
    evaporation_mm_day: float = 0.0  # doimiy (iqlim berilmasa)
    seepage_m3s: float = 0.0  # filtratsion yo'qotish
    climate: ClimateSpec | None = None  # berilsa bug'lanish mavsumiy (kun raqami bo'yicha)


@dataclass
class ReservoirState:
    elev_m: float
    volume_m3: float


def route_step(
    s1: float,
    dt_s: float,
    inflow: float,
    outflow: Callable[[float], float],
    tol: float = 1e-9,
) -> float:
    """Bitta qadam, trapetsiya implicit sxemasi (modified Puls): S₂ = S₁ + Δt·(I − (O(S₁) + O(S₂))/2).
    O(S) — kamaymaydigan funksiya (m³/s); g(S₂) monoton o'suvchi → yagona ildiz, Illinois usuli.
    I — qadam o'rtacha kiruvchi sarf (m³/s). Qaytaradi S₂ (m³), manfiy bo'lishi mumkin (chaqiruvchi
    tekshiradi)."""
    o1 = outflow(s1)
    base = s1 + dt_s * (inflow - o1 / 2)

    def g(s2: float) -> float:
        return s2 - base + dt_s * outflow(max(s2, 0.0)) / 2

    # Chegaralar: g(lo) ≤ 0 ≤ g(hi). O ≥ 0 → S₂ ≤ base; pastki chegara — kerak bo'lsa kengaytiriladi
    hi = max(base, 0.0)
    g_hi = g(hi)
    if g_hi <= 0:
        return hi
    lo = min(base - dt_s * o1, 0.0)
    g_lo = g(lo)
    span = max(abs(hi - lo), 1.0)
    while g_lo > 0 and span < 1e18:
        lo -= span
        span *= 2
        g_lo = g(lo)
    side = 0
    x = hi
    for _ in range(200):
        x = (lo * g_hi - hi * g_lo) / (g_hi - g_lo) if g_hi != g_lo else (lo + hi) / 2
        gx = g(x)
        if abs(gx) <= tol * max(1.0, abs(s1), abs(dt_s * inflow)) or (hi - lo) <= tol * max(1.0, abs(x)):
            return x
        if gx > 0:
            hi, g_hi = x, gx
            if side == 1:
                g_lo /= 2
            side = 1
        else:
            lo, g_lo = x, gx
            if side == -1:
                g_hi /= 2
            side = -1
    return x


def step(
    state: ReservoirState,
    spec: ReservoirSpec,
    inflow: float,
    turbine_demand: float,
    dt_s: float,
    day_of_year: float | None = None,
) -> tuple[ReservoirState, dict]:
    """Bitta vaqt qadami (modified Puls, `route_step`). Turbina sarfi o'lik sathdan pastga
    tushirmaydigan qilib cheklanadi. Tashlama: sath ostonadan yuqori bo'lsa suv tashlagich formulasi
    (qadam boshi va oxiri sathlarida — trapetsiya); suv tashlagich bo'lmasa va sath FPU dan oshsa —
    ortiqcha suv "majburiy tashlama" sifatida chiqariladi. Natijadagi tashlama/bug'lanish — qadam
    o'rtachasi (massa balansi shu qiymatlar bilan yopiladi). Hajm manfiy bo'lsa ValueError."""
    ice = False
    if spec.climate is not None and day_of_year is not None:
        e_mm = open_water_evaporation_mm_day(spec.climate, day_of_year)
        ice = is_ice(spec.climate, day_of_year)
    else:
        e_mm = spec.evaporation_mm_day
    tw = spec.tailwater_m if spec.tailwater_m > 0 else None
    fixed_losses = spec.other_outflow_m3s + spec.seepage_m3s

    def parts(v: float) -> tuple[float, float]:
        """(tashlama, bug'lanish) m³/s — hajm (sath) funksiyasi."""
        elev = spec.curve.elevation(max(v, 0.0))
        q_sp = spec.spillway.discharge(elev, tw) if spec.spillway else 0.0
        evap = e_mm / 1000 / 86400 * _surface_area(spec.curve, elev)
        return q_sp, evap

    def outflow(v: float) -> float:
        q_sp, evap = parts(v)
        return q_sp + evap + fixed_losses

    s1 = state.volume_m3
    dead_volume = spec.curve.volume(spec.dead_level_m)
    q_turb = max(turbine_demand, 0.0)
    s2 = route_step(s1, dt_s, inflow - q_turb, outflow)
    if s2 < dead_volume and q_turb > 0:
        # Turbina o'lik hajmgacha: S₂ = S_dead bo'ladigan sarf (trapetsiya balansidan aniq)
        q_turb = inflow - (outflow(s1) + outflow(dead_volume)) / 2 - (dead_volume - s1) / dt_s
        q_turb = min(max(q_turb, 0.0), turbine_demand)
        s2 = route_step(s1, dt_s, inflow - q_turb, outflow)
    sp1, ev1 = parts(s1)
    sp2, ev2 = parts(s2)
    q_spill = (sp1 + sp2) / 2
    evap = (ev1 + ev2) / 2
    losses = fixed_losses + evap
    v_next = s1 + (inflow - q_turb - q_spill - losses) * dt_s
    if v_next < -1e-6:
        raise ValueError(
            f"ombor hajmi manfiy ({v_next / 1e6:.3f} mln m³): yo'qotishlar/tashlama kiruvchi oqimdan "
            "katta — kiritmalarni tekshiring"
        )
    v_next = max(v_next, 0.0)
    max_level = spec.max_level_m if spec.max_level_m is not None else spec.normal_level_m + 2.0
    v_max = spec.curve.volume(max_level)
    forced = 0.0
    if v_next > v_max:
        forced = (v_next - v_max) / dt_s
        q_spill += forced
        v_next = v_max
    residual = v_next - (s1 + (inflow - q_turb - q_spill - losses) * dt_s)
    new = ReservoirState(spec.curve.elevation(v_next), v_next)
    return new, {
        "turbine": q_turb,
        "spill": q_spill,
        "forced_spill": forced,
        "mass_residual_m3": residual,
        "evap": evap,
        "evap_mm_day": e_mm,
        "seepage": spec.seepage_m3s,
        "ice": ice,
        "curtailed": turbine_demand - q_turb,
    }


def _surface_area(curve: StorageCurve, elev: float) -> float:
    d = 0.1
    return max((curve.volume(elev + d) - curve.volume(elev - d)) / (2 * d), 0.0)
