"""Optimal yuk taqsimoti (economic dispatch) gidroagregatlar orasida: berilgan umumiy quvvatni minimal
suv sarfi bilan ishlab chiqarish (FIK egri chiziqlari bo'yicha), agregatlarni yoqish/o'chirish.

Usul: dinamik dasturlash quvvat qadamlari bo'yicha (ΔP = 0.25 MW): har agregat uchun P → Q(P) jadval
(η(Q) egri chizig'i, minimal yuk 30–40 %), so'ng DP: F_k(P) = min_{P_k} [Q_k(P_k) + F_{k−1}(P − P_k)].
Taqqoslash: teng taqsimot va "birma-bir to'liq" strategiyalari bilan suv tejash %.
Kunlik jadval (ixtiyoriy): 24 soatlik talab → har soat dispatch → suv hajmi, sath o'zgarishi (ombor yuzasi).
"""

from __future__ import annotations

from .penstock import PenstockSpec, net_head
from .schema import Field, Meta
from .turbine import TurbineSpec, flow_for_power

META = Meta(
    id="dispatch",
    title="Optimal yuk taqsimoti (agregatlar)",
    description="Berilgan umumiy quvvat uchun qaysi agregatlar va qanday yuk bilan ishlasin — minimal suv sarfi "
    "(FIK egri chiziqlari). Kunlik talab jadvali bo'yicha suv hajmi va sath. Jonli holatdan «bugungi optimal rejim».",
    group="ekspluatatsiya",
    icon="sliders",
    formulas=["min Σ Q_k(P_k), Σ P_k = P", "Q(P) = P/(η(Q)·ρ·g·H_net)", "DP qadam 0.25 MW"],
    outputs=[
        {"key": "total_flow_m3s", "label": "Jami sarf (optimal)", "unit": "m³/s"},
        {"key": "saving_pct", "label": "Suv tejash (teng taqsimotga nisbatan)", "unit": "%"},
        {"key": "units_on", "label": "Ishlaydigan agregatlar", "unit": ""},
    ],
)

FIELDS = [
    Field(
        "target_mw", "Kerakli umumiy quvvat", "MW", default=60, min=0, group="Rejim", live="power"
    ),
    Field("head_m", "Brutto napor", "m", default=65, min=1, group="Rejim", live="gross_head"),
    Field(
        "n_units", "Agregatlar soni", "", type="int", default=3, min=1, max=8, group="Agregatlar"
    ),
    Field(
        "unit_type",
        "Turbina turi",
        type="select",
        default="Francis",
        options=(
            ("Francis", "Francis"),
            ("Kaplan", "Kaplan"),
            ("Pelton", "Pelton"),
            ("Bulb", "Bulb"),
        ),
        group="Agregatlar",
    ),
    Field("rated_mw", "Nominal quvvat (har biri)", "MW", default=40, min=0.1, group="Agregatlar"),
    Field("rated_head_m", "Nominal napor", "m", default=60, min=1, group="Agregatlar"),
    Field("rated_flow_m3s", "Nominal sarf", "m³/s", default=75, min=0.1, group="Agregatlar"),
    Field(
        "max_eff",
        "Maksimal FIK",
        "",
        default=0.92,
        min=0.5,
        max=0.98,
        step=0.005,
        group="Agregatlar",
    ),
    Field(
        "unit_ratings",
        "yoki agregatlar quvvatlari alohida (MW, bo'shliq bilan)",
        type="series",
        default=[],
        group="Agregatlar",
        advanced=True,
    ),
    Field(
        "penstock_length_m",
        "Quvur uzunligi (0 — yo'qotishsiz)",
        "m",
        default=0,
        min=0,
        group="Quvur",
        advanced=True,
    ),
    Field(
        "penstock_diameter_m",
        "Quvur diametri",
        "m",
        default=4.0,
        min=0.1,
        group="Quvur",
        advanced=True,
    ),
    Field(
        "daily_profile",
        "Kunlik talab (24 qiymat, MW; bo'sh — faqat bitta nuqta)",
        type="series",
        default=[],
        group="Kunlik jadval",
    ),
    Field(
        "reservoir_area_km2",
        "Ombor yuzasi (sath o'zgarishi uchun)",
        "km²",
        default=0,
        min=0,
        group="Kunlik jadval",
    ),
    Field(
        "inflow_m3s",
        "Kiruvchi sarf (kunlik jadval uchun)",
        "m³/s",
        default=100,
        min=0,
        group="Kunlik jadval",
        live="inflow",
    ),
]

STEP = 0.25  # MW


def _units(p: dict) -> list[TurbineSpec]:
    ratings = p["unit_ratings"] or [p["rated_mw"]] * int(p["n_units"])
    return [
        TurbineSpec(
            name=f"Agregat {i + 1}",
            type=p["unit_type"],
            rated_power_mw=float(r),
            rated_head_m=p["rated_head_m"],
            rated_flow_m3s=p["rated_flow_m3s"] * float(r) / p["rated_mw"],
            max_efficiency=p["max_eff"],
        )
        for i, r in enumerate(ratings)
    ]


def _q_table(
    u: TurbineSpec, head: float, pen: PenstockSpec | None, pmax: float
) -> list[float | None]:
    """P (qadam indeksi) → sarf; yaroqsiz (min yukdan kam / imkonsiz) → None; 0 → 0."""
    n = int(pmax / STEP) + 1
    out: list[float | None] = [0.0] + [None] * (n - 1)
    pmin = u.power_mw(u.min_flow, net_head(head, u.min_flow, pen))
    pcap = u.power_mw(u.max_flow, net_head(head, u.max_flow, pen))
    for i in range(1, n):
        pw = i * STEP
        if pw < pmin or pw > pcap:
            continue
        q = flow_for_power(pw, head, [u], pen)
        out[i] = q if q > 0 else None
    return out


def optimize(
    units: list[TurbineSpec],
    target: float,
    head: float,
    pen: PenstockSpec | None,
    tables: list[list[float | None]] | None = None,
) -> dict:
    n = int(round(target / STEP))
    pmax = sum(u.rated_power_mw for u in units) * 1.05
    tables = tables or [_q_table(u, head, pen, pmax) for u in units]
    INF = float("inf")
    # DP
    best = [0.0] + [INF] * n
    choice: list[list[int]] = []
    for tab in tables:
        nb = [INF] * (n + 1)
        ch = [0] * (n + 1)
        for tot in range(n + 1):
            for pk in range(0, min(tot, len(tab) - 1) + 1):
                q = tab[pk]
                if q is None or best[tot - pk] == INF:
                    continue
                v = best[tot - pk] + q
                if v < nb[tot]:
                    nb[tot], ch[tot] = v, pk
        best = nb
        choice.append(ch)
    if best[n] == INF:
        raise ValueError("Berilgan quvvatga erishib bo'lmaydi (agregatlar sig'imi/min yuk)")
    alloc = []
    rem = n
    for k in range(len(units) - 1, -1, -1):
        pk = choice[k][rem]
        alloc.append(pk * STEP)
        rem -= pk
    alloc.reverse()
    rows = []
    for u, pw in zip(units, alloc, strict=False):
        q = flow_for_power(pw, head, [u], pen) if pw > 0 else 0.0
        hn = net_head(head, q, pen)
        rows.append(
            {
                "name": u.name,
                "power_mw": round(pw, 2),
                "flow_m3s": round(q, 3),
                "efficiency": round(u.efficiency(q), 4) if q > 0 else None,
                "head_net_m": round(hn, 2),
                "load_pct": round(pw / u.rated_power_mw * 100, 1),
            }
        )
    return {
        "units": rows,
        "total_flow": round(best[n], 3),
        "units_on": sum(1 for r in rows if r["power_mw"] > 0),
    }


def _equal_share(
    units: list[TurbineSpec], target: float, head: float, pen: PenstockSpec | None
) -> float | None:
    """Teng taqsimot: minimal yukdan kam bo'lmaydigan eng kam sonli agregatlar bir xil yuk bilan — taqqoslash."""
    if target <= 0:
        return 0.0
    for n in range(1, len(units) + 1):
        share = target / n
        sub = units[:n]
        ok = all(
            u.power_mw(u.min_flow, net_head(head, u.min_flow, pen))
            <= share
            <= u.power_mw(u.max_flow, net_head(head, u.max_flow, pen))
            for u in sub
        )
        if ok:
            return round(sum(flow_for_power(share, head, [u], pen) for u in sub), 3)
    return None


def run(p: dict) -> dict:
    units = _units(p)
    pen = (
        PenstockSpec(p["penstock_length_m"], p["penstock_diameter_m"], 0.1, 0.5)
        if p["penstock_length_m"] > 0
        else None
    )
    head = p["head_m"]
    res = optimize(units, p["target_mw"], head, pen)
    eq = _equal_share(units, p["target_mw"], head, pen)
    saving = round((1 - res["total_flow"] / eq) * 100, 2) if eq and eq > 0 else None
    out = {
        "series": {},
        "units": res["units"],
        "summary": {
            "total_flow_m3s": res["total_flow"],
            "equal_share_flow_m3s": eq,
            "saving_pct": saving,
            "units_on": res["units_on"],
            "water_per_mwh_m3": round(res["total_flow"] * 3600 / p["target_mw"], 1)
            if p["target_mw"] > 0
            else None,
            "verdict": f"{res['units_on']} agregat: "
            + ", ".join(
                f"{r['name']} {r['power_mw']} MW ({r['load_pct']} %)"
                for r in res["units"]
                if r["power_mw"] > 0
            )
            + (f"; teng taqsimotga nisbatan {saving} % suv tejaladi" if saving is not None else ""),
            "ok": True,
        },
    }
    prof = p["daily_profile"]
    if prof:
        hours, flows, level, on = [], [], [], []
        lvl = 0.0
        area = p["reservoir_area_km2"] * 1e6
        pmax = sum(u.rated_power_mw for u in units) * 1.05
        tables = [_q_table(u, head, pen, pmax) for u in units]
        for h, pw in enumerate(prof[:24]):
            try:
                r = (
                    optimize(units, float(pw), head, pen, tables)
                    if pw > 0
                    else {"total_flow": 0.0, "units_on": 0}
                )
            except ValueError:
                r = {"total_flow": None, "units_on": None}
            hours.append(h)
            flows.append(r["total_flow"])
            on.append(r["units_on"])
            if area > 0 and r["total_flow"] is not None:
                lvl += (p["inflow_m3s"] - r["total_flow"]) * 3600 / area
            level.append(round(lvl, 4))
        out["series"] = {"t": hours, "flow_m3s": flows, "units_on": on, "level_change_m": level}
        vol = sum(f for f in flows if f is not None) * 3600 / 1e6
        out["summary"]["daily_water_mcm"] = round(vol, 3)
        out["summary"]["daily_energy_mwh"] = round(sum(prof[:24]), 1)
        out["summary"]["level_change_m"] = level[-1] if level else None
    return out
