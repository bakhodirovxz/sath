"""Iqlim: suv ombori yuzasidan bug'lanish, muz qoplami, mavsumiy harorat.

Atmosfera tashqarisi radiatsiyasi (FAO-56, 21–24-tengl.):
  Ra = 24·60/π · G_sc · d_r · [ω_s·sinφ·sinδ + cosφ·cosδ·sinω_s]   [MJ/m²/kun],  G_sc = 0.0820 MJ/m²/min
  d_r = 1 + 0.033·cos(2πJ/365),  δ = 0.409·sin(2πJ/365 − 1.39),  ω_s = arccos(−tanφ·tanδ)
Hargreaves–Samani (1985) etalon bug'lanish:  ET₀ = 0.0023 · 0.408·Ra · (T_mean + 17.8) · √(T_max − T_min)  [mm/kun]
Ochiq suv yuzasi:  E = k_w · ET₀,  k_w ≈ 1.05 (ko'l koeffitsienti, FAO-56 / Allen 2005),  muz qoplamida E ≈ 0.
Mavsumiy harorat (sinusoida):  T(J) = T_yil − A·cos(2π(J − 15)/365)   (minimum ~15-yanvar, maksimum ~iyul).
Muz: T_mean < T_muz (−1 °C) — qoplam; bug'lanish to'xtaydi, tashlama/turbina o'zgarmaydi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G_SC = 0.0820  # MJ/m²/min
LAKE_COEFF = 1.05


@dataclass(frozen=True)
class ClimateSpec:
    latitude_deg: float = 41.6
    t_mean_annual_c: float = 13.0  # yillik o'rtacha harorat
    t_amplitude_c: float = 14.0  # yillik tebranish amplitudasi (yoz−qish yarmi)
    diurnal_range_c: float = 12.0  # sutkalik T_max − T_min
    lake_coeff: float = LAKE_COEFF
    ice_threshold_c: float = -1.0


def extraterrestrial_radiation(lat_deg: float, doy: float) -> float:
    """Ra, MJ/m²/kun (FAO-56)."""
    phi = math.radians(lat_deg)
    j = 2 * math.pi * doy / 365.0
    dr = 1 + 0.033 * math.cos(j)
    delta = 0.409 * math.sin(j - 1.39)
    x = -math.tan(phi) * math.tan(delta)
    ws = math.acos(max(-1.0, min(1.0, x)))
    ra = (24 * 60 / math.pi) * G_SC * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )
    return max(ra, 0.0)


def hargreaves_et0(t_mean: float, t_max: float, t_min: float, lat_deg: float, doy: float) -> float:
    """Etalon bug'lanish ET₀, mm/kun (Hargreaves–Samani 1985)."""
    ra_mm = 0.408 * extraterrestrial_radiation(lat_deg, doy)
    return max(0.0023 * ra_mm * (t_mean + 17.8) * math.sqrt(max(t_max - t_min, 0.0)), 0.0)


def seasonal_temperature(spec: ClimateSpec, doy: float) -> float:
    return spec.t_mean_annual_c - spec.t_amplitude_c * math.cos(2 * math.pi * (doy - 15) / 365.0)


def is_ice(spec: ClimateSpec, doy: float) -> bool:
    return seasonal_temperature(spec, doy) < spec.ice_threshold_c


def open_water_evaporation_mm_day(spec: ClimateSpec, doy: float) -> float:
    """Ochiq suv yuzasidan bug'lanish, mm/kun (muz bo'lsa 0)."""
    t = seasonal_temperature(spec, doy)
    if t < spec.ice_threshold_c:
        return 0.0
    half = spec.diurnal_range_c / 2
    return spec.lake_coeff * hargreaves_et0(t, t + half, t - half, spec.latitude_deg, doy)


def annual_evaporation_mm(spec: ClimateSpec) -> float:
    return sum(open_water_evaporation_mm_day(spec, d) for d in range(1, 366))
