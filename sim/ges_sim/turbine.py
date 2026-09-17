"""Turbina agregatlari: hill-chart FIK (sarf va naporga bog'liq), generator/mexanik yo'qotishlar, quvvat,
agregatlar orasida yuk taqsimoti.

Gidravlik quvvat  P_h [W] = ρ·g·Q·H_net;  turbina vali  P_t = η_t·P_h;  generator klemmalari  P_e = η_g·(1−k_mech)·P_t.
Turbina FIK — soddalashtirilgan hill-chart (IEC 60193 normalizatsiyasi ruhida, tur bo'yicha prototip egri chiziqlari):
  η_t(Q, H) = η_max · f_q(Q / Q_bep(H)) · f_H(H / H_r),
  Q_bep(H) = Q_r · √(H/H_r)      — o'zgarmas aylanishda BEP sarfi napor bilan siljiydi (Q₁₁ = Q/(D²√H) = const),
  f_H(x)   = 1 − c_H·(x − 1)²    — nominal napordan chetlanish jarimasi (|x−1| ≤ 0.4 da): Francis c_H = 0.5
                                   (±30 % → −4.5 %), Kaplan/Bulb 0.15 (ikki tomonlama rostlash), Pelton 0.10.
  f_q      — qism yuklamada FIK pasayishi (nuqtalar): Francis tor, Kaplan/Bulb keng, Pelton juda keng.
  Francis «qo'pol zona»: 40–60 % yuklama — so'rish quvurida vortex (Rheingans), tebranish ortadi (belgilanadi).
Generator (sinxron): yo'qotish = temir (doimiy) + mis (∝ P²):  P_loss = P_r(1/η_gmax − 1)·[k_fe + (1−k_fe)·(P/P_r)²],
  k_fe = 0.4;  η_g(P) = P_t/(P_t + P_loss).  Mexanik (podshipnik, ventilyatsiya) ≈ 0.5 % nominaldan (ishlaganda doimiy).
Natijalar MW da qaytariladi. Manbalar: IEC 60193; Krivchenko, «Hydraulic Machines» (1994); IEEE Std 115.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .penstock import RHO, G, PenstockSpec, net_head

TurbineType = str  # "Francis" | "Kaplan" | "Pelton" | "Bulb"

# (min_load, curve) — curve: q/q_rated → η/η_max (nuqtalar, chiziqli interpolyatsiya)
_CURVES: dict[str, tuple[float, list[tuple[float, float]]]] = {
    "Francis": (
        0.40,
        [(0.40, 0.78), (0.55, 0.90), (0.70, 0.96), (0.85, 0.99), (1.00, 1.00), (1.10, 0.97)],
    ),
    "Kaplan": (
        0.25,
        [(0.25, 0.85), (0.40, 0.93), (0.60, 0.97), (0.80, 0.99), (1.00, 1.00), (1.10, 0.98)],
    ),
    "Bulb": (
        0.25,
        [(0.25, 0.84), (0.40, 0.92), (0.60, 0.97), (0.80, 0.99), (1.00, 1.00), (1.10, 0.98)],
    ),
    "Pelton": (
        0.10,
        [(0.10, 0.80), (0.25, 0.92), (0.50, 0.97), (0.75, 0.99), (1.00, 1.00), (1.15, 0.98)],
    ),
}


def _interp(points: list[tuple[float, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


# Nominal napordan chetlanish jarimasi koeffitsienti c_H (tur bo'yicha)
_HEAD_SENS: dict[str, float] = {"Francis": 0.5, "Kaplan": 0.15, "Bulb": 0.15, "Pelton": 0.10}
# Francis qo'pol zonasi (yuklama ulushi): so'rish quvuri vortex — tebranish
ROUGH_ZONE = (0.40, 0.60)
HEAD_RANGE = 0.40  # hill-chart jarimasi hisoblanadigan napor og'ishi chegarasi


@dataclass(frozen=True)
class UnitPower:
    """Bitta agregat ishlash nuqtasi."""

    hydraulic_mw: float  # ρgQH_net
    turbine_mw: float  # val quvvati
    electrical_mw: float  # generator klemmalari
    eta_turbine: float
    eta_generator: float
    eta_total: float  # P_e / P_h
    rough_zone: bool


@dataclass(frozen=True)
class TurbineSpec:
    name: str = "Agregat"
    type: TurbineType = "Francis"
    rated_power_mw: float = 25.0
    rated_head_m: float = 45.0
    rated_flow_m3s: float = 62.0
    max_efficiency: float = 0.92  # turbina (gidravlik) maksimal FIK
    max_load: float = 1.10  # nominal sarfdan oshiq ruxsat etilgan ulush
    generator_eta_max: float = 0.985  # sinxron generator nominal FIK
    generator_iron_frac: float = 0.4  # temir (doimiy) yo'qotish ulushi nominal yo'qotishda
    mech_loss_frac: float = 0.005  # podshipnik/ventilyatsiya — nominal quvvatdan ulush
    head_sensitivity: float | None = None  # c_H (None — tur bo'yicha)

    @property
    def min_flow(self) -> float:
        return _CURVES[self.type][0] * self.rated_flow_m3s

    @property
    def max_flow(self) -> float:
        return self.max_load * self.rated_flow_m3s

    def bep_flow(self, head_net: float | None = None) -> float:
        """Eng yaxshi FIK sarfi — napor bilan siljiydi (o'zgarmas aylanish tezligi, Q₁₁ = const)."""
        if head_net is None or head_net <= 0 or self.rated_head_m <= 0:
            return self.rated_flow_m3s
        return self.rated_flow_m3s * (head_net / self.rated_head_m) ** 0.5

    def head_factor(self, head_net: float | None) -> float:
        """f_H — nominal napordan chetlanish jarimasi (0.5 dan kam emas)."""
        if head_net is None or head_net <= 0 or self.rated_head_m <= 0:
            return 1.0
        c = self.head_sensitivity if self.head_sensitivity is not None else _HEAD_SENS[self.type]
        # ±40 % dan tashqarida jarima o'smaydi (ish diapazonidan tashqari — quvvat naporga proporsional qoladi)
        d = max(-HEAD_RANGE, min(HEAD_RANGE, head_net / self.rated_head_m - 1.0))
        return 1.0 - c * d * d

    def efficiency(self, q: float, head_net: float | None = None) -> float:
        """Turbina FIK ishlash nuqtasida (0 — ishlamaydi, min sarfdan past). head_net berilsa hill-chart."""
        if q < self.min_flow - 1e-9:
            return 0.0
        return (
            self.max_efficiency
            * _interp(_CURVES[self.type][1], q / self.bep_flow(head_net))
            * self.head_factor(head_net)
        )

    def rough_zone(self, q: float) -> bool:
        """Francis qism yuklama qo'pol zonasi (so'rish quvuri vortex, tebranish)."""
        if self.type != "Francis" or self.rated_flow_m3s <= 0:
            return False
        r = q / self.rated_flow_m3s
        return ROUGH_ZONE[0] <= r < ROUGH_ZONE[1]

    def generator_efficiency(self, turbine_mw: float) -> float:
        """η_g(P): temir (doimiy) + mis (∝P²) yo'qotishlar; nominalda generator_eta_max."""
        if turbine_mw <= 0 or self.rated_power_mw <= 0:
            return 0.0
        loss_rated = self.rated_power_mw * (1.0 / self.generator_eta_max - 1.0)
        k = self.generator_iron_frac
        ratio = turbine_mw / self.rated_power_mw
        loss = loss_rated * (k + (1.0 - k) * ratio * ratio)
        return turbine_mw / (turbine_mw + loss)

    def output(self, q: float, head_net: float) -> UnitPower:
        """To'liq zanjir: gidravlik → turbina vali → generator klemmalari (MW)."""
        eta_t = self.efficiency(q, head_net)
        if eta_t == 0.0 or head_net <= 0:
            return UnitPower(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)
        p_h = RHO * G * q * head_net / 1e6
        p_t = eta_t * p_h - self.mech_loss_frac * self.rated_power_mw
        p_t = max(p_t, 0.0)
        eta_g = self.generator_efficiency(p_t)
        p_e = min(p_t * eta_g, self.rated_power_mw * 1.05)
        return UnitPower(p_h, p_t, p_e, eta_t, eta_g, p_e / p_h if p_h > 0 else 0.0, self.rough_zone(q))

    def power_mw(self, q: float, head_net: float) -> float:
        """Generator klemmalaridagi quvvat, MW (turbina + generator + mexanik yo'qotishlar bilan)."""
        return self.output(q, head_net).electrical_mw


@dataclass
class UnitResult:
    name: str
    flow_m3s: float
    power_mw: float
    efficiency: float
    on: bool


@dataclass
class DispatchResult:
    head_net_m: float
    flow_m3s: float
    power_mw: float
    units: list[UnitResult] = field(default_factory=list)


def dispatch(
    q_available: float,
    gross_head: float,
    units: list[TurbineSpec],
    penstock: PenstockSpec | None = None,
    penstocks_per_unit: bool = True,
) -> DispatchResult:
    """Sarfni agregatlar orasida taqsimlaydi: n ta bir xil ishlaydigan agregat varianti ichidan
    eng katta quvvat beradiganini tanlaydi (tenglashtirilgan yuk — amaliyotda odatiy).

    penstocks_per_unit=True — har agregatning o'z quvuri (yo'qotish agregat sarfi bo'yicha);
    False — umumiy quvur (yo'qotish jami sarf bo'yicha).
    """
    if not units or q_available <= 0 or gross_head <= 0:
        return DispatchResult(
            net_head(gross_head, 0, None),
            0.0,
            0.0,
            [UnitResult(u.name, 0, 0, 0, False) for u in units],
        )

    best: DispatchResult | None = None
    for n in range(1, len(units) + 1):
        active = units[:n]
        # Har biriga ulush: sarfni teng bo'lib, chegaralarga kesamiz
        total_cap = sum(u.max_flow for u in active)
        share = min(q_available, total_cap)
        flows = [share * u.max_flow / total_cap for u in active]
        if any(q < u.min_flow for q, u in zip(flows, active, strict=True)):
            continue
        if penstocks_per_unit:
            heads = [net_head(gross_head, q, penstock) for q in flows]
        else:
            h = net_head(gross_head, sum(flows), penstock)
            heads = [h] * n
        results = [
            UnitResult(u.name, q, u.power_mw(q, h), u.efficiency(q, h), True)
            for u, q, h in zip(active, flows, heads, strict=True)
        ]
        total = sum(r.power_mw for r in results)
        if best is None or total > best.power_mw:
            off = [UnitResult(u.name, 0, 0, 0, False) for u in units[n:]]
            best = DispatchResult(sum(heads) / n, sum(flows), total, results + off)
    if best is None:  # sarf eng kichik agregat uchun ham yetmaydi
        return DispatchResult(
            net_head(gross_head, 0, None),
            0.0,
            0.0,
            [UnitResult(u.name, 0, 0, 0, False) for u in units],
        )
    return best


def flow_for_power(
    target_mw: float,
    gross_head: float,
    units: list[TurbineSpec],
    penstock: PenstockSpec | None = None,
) -> float:
    """Berilgan quvvat uchun kerakli sarf (ikkilik qidiruv). Mumkin bo'lgan maksimumdan oshsa — maksimal sarf."""
    lo, hi = 0.0, sum(u.max_flow for u in units)
    if dispatch(hi, gross_head, units, penstock).power_mw <= target_mw:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if dispatch(mid, gross_head, units, penstock).power_mw < target_mw:
            lo = mid
        else:
            hi = mid
    return hi
