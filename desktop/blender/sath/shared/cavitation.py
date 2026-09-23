"""Reaktiv turbina kavitatsiyasi: kritik Toma soni σ_c solishtirma tezlik n_s ga bog'liq.

YAGONA MANBA — server (`monitoring/cm/ha.py`) va Blender addoni (`desktop/blender/sath/shared/`,
`desktop/build/sync_blender.py` nusxalaydi) shu faylni ishlatadi. Faqat `math` — boshqa import yo'q.

Solishtirma tezlik (metrik, "m-kVt" birliklarida):
    n_s = n · √P / H^(5/4)
    n — aylanish tezligi [ayl/min], P — BIR ish g'ildiragining val quvvati [kVt], H — sof napor [m].
    (ft-hp birligidagi n_s dan: n_s(m-kVt) ≈ 3.81 · n_s(ft-hp).)

Kritik Toma soni (empirik, IEC 60193 ta'rifidagi σ = NPSE/(gH) bilan bir xil ma'noda):
    Francis:          σ_c = 0.625 · (n_s / 380.78)²            (≡ 0.0431 · (n_s/100)²)
    Kaplan/propeller: σ_c = 0.28 + (1/7.5) · (n_s / 380.78)³
    Pelton:           erkin oqim — σ bilan baholanmaydi (0).
Manba: Moody tipidagi empirik korrelyatsiyaning metrik ko'rinishi — R.K. Bansal, "A Textbook of Fluid
Mechanics and Hydraulic Machines" (Laxmi), turbinalar bobi, "Thoma's cavitation factor"; P.S. Nigam,
"Handbook of Hydroelectric Engineering" (1985). 380.78 — korrelyatsiya konstantasi (m-kVt birliklarida).

Tekshirish (tarqoqlik ±30 % — bu ko'rsatkich loyiha bosqichi uchun, model sinovi o'rnini bosmaydi):
    de Siervo & de Leva (1976), Water Power & Dam Constr. 28(12) — Francis σ = 7.54·10⁻⁵·n_s^1.41
    de Siervo & de Leva (1977), Water Power & Dam Constr. 29(1)  — Kaplan  σ = 6.40·10⁻⁵·n_s^1.46
    USBR Engineering Monograph No. 20 (1976) — Francis σ = n_s^1.64 / 50327 (n_s m-kVt)
    n_s = 200 (Francis): Bansal 0.172, de Siervo 0.132, USBR 0.118 → Bansal konservativ (yuqori σ_c).
    n_s = 600 (Kaplan):  Bansal 0.80,  de Siervo 0.73.
"""

from __future__ import annotations

import math

NS_REF = 380.78  # m-kVt (Bansal)


def specific_speed(n_rpm: float, p_kw: float, head_m: float) -> float:
    """n_s = n·√P/H^1.25 [m-kVt]; noto'g'ri kirishda 0."""
    if n_rpm <= 0 or p_kw <= 0 or head_m <= 0:
        return 0.0
    return n_rpm * math.sqrt(p_kw) / head_m**1.25


def turbine_family(turbine_type: str | None) -> str:
    """Turbina oilasi: francis | kaplan | pelton (bulb/propeller/tubular/deriaz → kaplan)."""
    t = (turbine_type or "Francis").lower()
    if any(k in t for k in ("kaplan", "propeller", "bulb", "tubular", "deriaz")):
        return "kaplan"
    if "pelton" in t or "turgo" in t:
        return "pelton"
    return "francis"


def sigma_critical(turbine_type: str | None, n_s: float) -> float:
    """Kritik Toma soni σ_c (modul docstringidagi formulalar). σ_plant < σ_c → kavitatsiya xavfi."""
    fam = turbine_family(turbine_type)
    if fam == "pelton" or n_s <= 0:
        return 0.0
    x = n_s / NS_REF
    if fam == "kaplan":
        return 0.28 + x**3 / 7.5
    return 0.625 * x * x


def plant_sigma(h_atm_m: float, h_vapor_m: float, suction_head_m: float, head_net_m: float) -> float:
    """σ_plant = (H_atm − H_v − H_s)/H_net (Thoma; H_s = ish g'ildiragi − quyi byef, + yuqorida)."""
    if head_net_m <= 0:
        return 0.0
    return (h_atm_m - h_vapor_m - suction_head_m) / head_net_m
