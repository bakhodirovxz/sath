"""Suv ombori suv balansi: kiruvchi sarf → sath, hajm, tashlama.

V[t+1] = V[t] + (Q_in − Q_turb − Q_spill − Q_other) · dt
Sath–hajm bog'liqligi nuqtalar bilan (batimetriya), chiziqli interpolyatsiya.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .climate import ClimateSpec, is_ice, open_water_evaporation_mm_day
from .penstock import G


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


@dataclass(frozen=True)
class SpillwaySpec:
    crest_m: float  # ostona belgisi
    width_m: float
    coefficient: float = 0.49  # m: Q = m·b·√(2g)·H^1.5 (Krigerning profili ≈ 0.49)
    gate_opening: float = 1.0  # 0..1 — darvoza ochiqligi (1 — to'liq/darvozasiz)

    def discharge(self, elev: float) -> float:
        h = elev - self.crest_m
        if h <= 0 or self.gate_opening <= 0:
            return 0.0
        return self.gate_opening * self.coefficient * self.width_m * math.sqrt(2 * G) * h**1.5


@dataclass(frozen=True)
class ReservoirSpec:
    curve: StorageCurve
    dead_level_m: float  # o'lik hajm sathi — turbinalar undan past suv ololmaydi
    normal_level_m: float  # NPU — normal to'ldirish sathi
    max_level_m: float | None = None  # FPU — majburiy sath (berilmasa NPU + 2)
    spillway: SpillwaySpec | None = None
    tailwater_m: float = 0.0  # quyi byef sathi (napor = sath − tailwater)
    other_outflow_m3s: float = 0.0  # sug'orish, ekologik oqim va h.k.
    evaporation_mm_day: float = 0.0  # doimiy (iqlim berilmasa)
    seepage_m3s: float = 0.0  # filtratsion yo'qotish
    climate: ClimateSpec | None = None  # berilsa bug'lanish mavsumiy (kun raqami bo'yicha)


@dataclass
class ReservoirState:
    elev_m: float
    volume_m3: float


def step(
    state: ReservoirState,
    spec: ReservoirSpec,
    inflow: float,
    turbine_demand: float,
    dt_s: float,
    day_of_year: float | None = None,
) -> tuple[ReservoirState, dict]:
    """Bitta vaqt qadami. Turbina sarfi o'lik sathdan pastga tushirmaydigan qilib cheklanadi.
    Tashlama: sath ostonadan yuqori bo'lsa suv tashlagich formulasi; suv tashlagich bo'lmasa va
    sath FPU dan oshsa — ortiqcha suv "majburiy tashlama" sifatida chiqariladi."""
    area = _surface_area(spec.curve, state.elev_m)
    ice = False
    if spec.climate is not None and day_of_year is not None:
        e_mm = open_water_evaporation_mm_day(spec.climate, day_of_year)
        ice = is_ice(spec.climate, day_of_year)
    else:
        e_mm = spec.evaporation_mm_day
    evap = e_mm / 1000 / 86400 * area  # m³/s
    losses = spec.other_outflow_m3s + evap + spec.seepage_m3s
    dead_volume = spec.curve.volume(spec.dead_level_m)
    available = max(state.volume_m3 - dead_volume, 0.0) / dt_s + inflow - losses
    q_turb = max(min(turbine_demand, available), 0.0)
    q_spill = spec.spillway.discharge(state.elev_m) if spec.spillway else 0.0
    v_next = state.volume_m3 + (inflow - q_turb - q_spill - losses) * dt_s
    v_next = max(v_next, 0.0)
    max_level = spec.max_level_m if spec.max_level_m is not None else spec.normal_level_m + 2.0
    v_max = spec.curve.volume(max_level)
    forced = 0.0
    if v_next > v_max:
        forced = (v_next - v_max) / dt_s
        q_spill += forced
        v_next = v_max
    new = ReservoirState(spec.curve.elevation(v_next), v_next)
    return new, {
        "turbine": q_turb,
        "spill": q_spill,
        "forced_spill": forced,
        "evap": evap,
        "evap_mm_day": e_mm,
        "seepage": spec.seepage_m3s,
        "ice": ice,
        "curtailed": turbine_demand - q_turb,
    }


def _surface_area(curve: StorageCurve, elev: float) -> float:
    d = 0.1
    return max((curve.volume(elev + d) - curve.volume(elev - d)) / (2 * d), 0.0)
