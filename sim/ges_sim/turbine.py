"""Turbina agregatlari: FIK egri chiziqlari, quvvat, agregatlar orasida yuk taqsimoti.

P [W] = η · ρ · g · Q · H_net.  Natijalar MW da qaytariladi.
FIK egri chiziqlari — turbina turi bo'yicha soddalashtirilgan (qism yuklamada FIK pasayishi):
Francis tor, Kaplan (burilma parrakli) keng, Pelton juda keng diapazon.
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


@dataclass(frozen=True)
class TurbineSpec:
    name: str = "Agregat"
    type: TurbineType = "Francis"
    rated_power_mw: float = 25.0
    rated_head_m: float = 45.0
    rated_flow_m3s: float = 62.0
    max_efficiency: float = 0.92
    max_load: float = 1.10  # nominal sarfdan oshiq ruxsat etilgan ulush

    @property
    def min_flow(self) -> float:
        return _CURVES[self.type][0] * self.rated_flow_m3s

    @property
    def max_flow(self) -> float:
        return self.max_load * self.rated_flow_m3s

    def efficiency(self, q: float) -> float:
        """Sarf q dagi FIK (0 — ishlamaydi, min sarfdan past)."""
        if q < self.min_flow - 1e-9:
            return 0.0
        return self.max_efficiency * _interp(_CURVES[self.type][1], q / self.rated_flow_m3s)

    def power_mw(self, q: float, head_net: float) -> float:
        eff = self.efficiency(q)
        if eff == 0.0 or head_net <= 0:
            return 0.0
        return min(eff * RHO * G * q * head_net / 1e6, self.rated_power_mw * 1.05)


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
            UnitResult(u.name, q, u.power_mw(q, h), u.efficiency(q), True)
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
