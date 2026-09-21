"""Bosimli quvur (penstock) gidravlikasi: Darcy–Weisbach napor yo'qotishi.

Barcha kattaliklar SI: m, m³/s, s. G'adir-budirlik millimetrda beriladi (odatiy ma'lumotnoma birligi).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.80665
RHO = 998.2  # suv zichligi, kg/m³ (15–20 °C)
NU = 1.14e-6  # kinematik qovushqoqlik, m²/s (15 °C)


@dataclass(frozen=True)
class PenstockSpec:
    length_m: float
    diameter_m: float
    roughness_mm: float = 0.1  # po'lat: 0.05–0.15, temir-beton: 0.3–1.0
    minor_loss_k: float = 0.5  # kirish + burilishlar + zadvijka (yig'ma koeffitsient)

    @property
    def area(self) -> float:
        return math.pi * self.diameter_m**2 / 4


def velocity(q: float, spec: PenstockSpec) -> float:
    return q / spec.area


def reynolds(q: float, spec: PenstockSpec) -> float:
    return velocity(q, spec) * spec.diameter_m / NU


def friction_factor(re: float, rel_roughness: float) -> float:
    """Ishqalanish koeffitsienti: laminar 64/Re (Re < 2300); Swamee–Jain (1976, Colebrook ga ±1 %,
    amal doirasi 5·10³ ≤ Re ≤ 10⁸, 10⁻⁶ ≤ ε/D ≤ 10⁻²) Re ≥ 4000 da; 2300–4000 o'tish zonasida
    laminar (Re = 2300) va turbulent (Re = 4000) qiymatlar orasida chiziqli interpolyatsiya —
    uzilish yo'q (Cengel & Cimbala, §8-5)."""
    if re < 1e-9:
        return 0.0
    if re < 2300:
        return 64.0 / re

    def sj(r: float) -> float:
        return 0.25 / (math.log10(rel_roughness / 3.7 + 5.74 / r**0.9)) ** 2

    if re < 4000:
        f_lam, f_turb = 64.0 / 2300, sj(4000)
        return f_lam + (f_turb - f_lam) * (re - 2300) / (4000 - 2300)
    return sj(re)


def head_loss(q: float, spec: PenstockSpec) -> float:
    """Umumiy napor yo'qotishi, m: ishqalanish (Darcy–Weisbach) + mahalliy."""
    if q <= 0:
        return 0.0
    v = velocity(q, spec)
    f = friction_factor(reynolds(q, spec), spec.roughness_mm / 1000 / spec.diameter_m)
    velocity_head = v**2 / (2 * G)
    return (f * spec.length_m / spec.diameter_m + spec.minor_loss_k) * velocity_head


def net_head(gross_head: float, q: float, spec: PenstockSpec | None) -> float:
    """Sof napor = yalpi napor − yo'qotishlar (manfiy bo'lmaydi)."""
    if spec is None:
        return max(gross_head, 0.0)
    return max(gross_head - head_loss(q, spec), 0.0)
