"""Yuqori darajali ssenariy: kiruvchi gidrograf → suv ombori → quvur → turbinalar → quvvat/energiya.

Kirish — oddiy JSON (server API va web forma bilan bir xil), chiqish — vaqt qatorlari + xulosa.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .climate import ClimateSpec
from .penstock import PenstockSpec
from .reservoir import ReservoirSpec, ReservoirState, SpillwaySpec, StorageCurve, step
from .turbine import TurbineSpec, dispatch, flow_for_power

MODES = ("max_power", "run_of_river", "constant_flow", "target_level", "target_power")


def _inflow_series(spec: Any) -> list[float]:
    if isinstance(spec, list):
        return [float(x) for x in spec]
    if isinstance(spec, dict):
        if "constant" in spec:
            return [float(spec["constant"])] * int(spec.get("steps", 365))
        if "values" in spec:
            return [float(x) for x in spec["values"]]
    raise ValueError("inflow_m3s: ro'yxat yoki {constant, steps} bo'lishi kerak")


def _only(d: dict, cls) -> dict:
    return {k: v for k, v in d.items() if k in cls.__dataclass_fields__}


def parse(params: dict) -> dict:
    """JSON parametrlarni spec obyektlariga aylantiradi (validatsiya bilan)."""
    r = params["reservoir"]
    curve = StorageCurve(tuple(r["curve"]["elevations_m"]), tuple(r["curve"]["volumes_mcm"]))
    spill = SpillwaySpec(**r["spillway"]) if r.get("spillway") else None
    reservoir = ReservoirSpec(
        curve=curve,
        dead_level_m=float(r["dead_level_m"]),
        normal_level_m=float(r["normal_level_m"]),
        max_level_m=float(r["max_level_m"]) if r.get("max_level_m") is not None else None,
        spillway=spill,
        tailwater_m=float(r.get("tailwater_m", 0.0)),
        other_outflow_m3s=float(r.get("other_outflow_m3s", 0.0)),
        evaporation_mm_day=float(r.get("evaporation_mm_day", 0.0)),
        seepage_m3s=float(r.get("seepage_m3s", 0.0)),
        climate=ClimateSpec(**_only(r["climate"], ClimateSpec)) if r.get("climate") else None,
    )
    if not (reservoir.dead_level_m < reservoir.normal_level_m):
        raise ValueError("O'lik sath NPU dan past bo'lishi kerak")
    # Qo'shimcha maydonlar (guid, izoh) e'tiborsiz qoldiriladi
    units = [TurbineSpec(**_only(u, TurbineSpec)) for u in params.get("units", [])]
    if not units:
        raise ValueError("Kamida bitta agregat kerak")
    penstock = (
        PenstockSpec(**_only(params["penstock"], PenstockSpec)) if params.get("penstock") else None
    )
    per_unit = bool((params.get("penstock") or {}).get("per_unit", True))
    op = params.get("operation") or {"mode": "max_power"}
    if op.get("mode", "max_power") not in MODES:
        raise ValueError(f"operation.mode: {MODES}")
    return {
        "dt_s": float(params.get("dt_hours", 24)) * 3600,
        "inflow": _inflow_series(params["inflow_m3s"]),
        "reservoir": reservoir,
        "initial_level": float(r.get("initial_level_m", reservoir.normal_level_m)),
        "units": units,
        "penstock": penstock,
        "per_unit": per_unit,
        "operation": op,
        "start_date": params.get("start_date"),
    }


def run(params: dict) -> dict:
    p = parse(params)
    res: ReservoirSpec = p["reservoir"]
    units: list[TurbineSpec] = p["units"]
    dt = p["dt_s"]
    op = p["operation"]
    mode = op.get("mode", "max_power")
    max_flow = sum(u.max_flow for u in units)

    state = ReservoirState(p["initial_level"], res.curve.volume(p["initial_level"]))
    n = len(p["inflow"])
    series: dict[str, list] = {
        k: []
        for k in (
            "t",
            "inflow",
            "level",
            "volume_mcm",
            "turbine_flow",
            "spill",
            "power_mw",
            "head_gross",
            "head_net",
            "units_on",
            "curtailed",
            "evap_mm_day",
            "ice",
        )
    }
    unit_power: list[list[float]] = [[] for _ in units]
    start = date.fromisoformat(p["start_date"]) if p.get("start_date") else None

    for i, q_in in enumerate(p["inflow"]):
        gross = state.elev_m - res.tailwater_m
        if mode == "max_power":
            demand = max_flow
        elif mode == "run_of_river":
            demand = min(q_in - res.other_outflow_m3s, max_flow)
        elif mode == "constant_flow":
            demand = min(float(op.get("flow_m3s", 0.0)), max_flow)
        elif mode == "target_level":
            target_v = res.curve.volume(float(op.get("target_level_m", res.normal_level_m)))
            demand = min(
                max(q_in + (state.volume_m3 - target_v) / dt - res.other_outflow_m3s, 0.0), max_flow
            )
        else:  # target_power
            demand = (
                flow_for_power(float(op.get("power_mw", 0.0)), gross, units, p["penstock"])
                if gross > 0
                else 0.0
            )
        demand = max(demand, 0.0)

        doy = (start + timedelta(seconds=dt * i)).timetuple().tm_yday if start else None
        state_next, flows = step(state, res, q_in, demand, dt, day_of_year=doy)
        d = dispatch(flows["turbine"], gross, units, p["penstock"], p["per_unit"])

        series["t"].append((start + timedelta(seconds=dt * i)).isoformat() if start else i)
        series["inflow"].append(q_in)
        series["level"].append(round(state.elev_m, 3))
        series["volume_mcm"].append(round(state.volume_m3 / 1e6, 4))
        series["turbine_flow"].append(round(d.flow_m3s, 3))
        series["spill"].append(round(flows["spill"], 3))
        series["power_mw"].append(round(d.power_mw, 3))
        series["head_gross"].append(round(gross, 3))
        series["head_net"].append(round(d.head_net_m, 3))
        series["units_on"].append(sum(1 for u in d.units if u.on))
        series["curtailed"].append(round(max(flows["curtailed"], 0.0), 3))
        series["evap_mm_day"].append(round(flows["evap_mm_day"], 2))
        series["ice"].append(bool(flows["ice"]))
        for k, u in enumerate(d.units):
            unit_power[k].append(round(u.power_mw, 3))
        state = state_next

    hours = dt / 3600
    energy = sum(series["power_mw"]) * hours
    installed = sum(u.rated_power_mw for u in units)
    summary = {
        "steps": n,
        "hours": n * hours,
        "energy_mwh": round(energy, 1),
        "mean_power_mw": round(energy / (n * hours), 3) if n else 0.0,
        "max_power_mw": round(max(series["power_mw"], default=0.0), 3),
        "installed_mw": installed,
        "capacity_factor": round(energy / (installed * n * hours), 4) if n and installed else 0.0,
        "min_level_m": round(min(series["level"], default=0.0), 3),
        "max_level_m": round(max(series["level"], default=0.0), 3),
        "final_level_m": round(state.elev_m, 3),
        "spill_volume_mcm": round(sum(series["spill"]) * dt / 1e6, 3),
        "inflow_volume_mcm": round(sum(series["inflow"]) * dt / 1e6, 3),
        "turbined_volume_mcm": round(sum(series["turbine_flow"]) * dt / 1e6, 3),
        "curtailed_steps": sum(1 for c in series["curtailed"] if c > 1e-6),
    }
    return {
        "series": series,
        "units": [
            {"name": u.name, "type": u.type, "power_mw": unit_power[k]} for k, u in enumerate(units)
        ],
        "summary": summary,
    }


def example_params() -> dict:
    """Web forma uchun boshlang'ich namuna (o'rta GES)."""
    return {
        "dt_hours": 24,
        "start_date": "2026-01-01",
        "inflow_m3s": {"constant": 120, "steps": 365},
        "reservoir": {
            "curve": {
                "elevations_m": [850, 870, 890, 905, 915],
                "volumes_mcm": [0, 60, 220, 480, 700],
            },
            "dead_level_m": 870,
            "normal_level_m": 905,
            "max_level_m": 912,
            "initial_level_m": 900,
            "tailwater_m": 840,
            "other_outflow_m3s": 5,
            "evaporation_mm_day": 3,
            "spillway": {"crest_m": 905, "width_m": 24, "coefficient": 0.49, "gate_opening": 1.0},
        },
        "penstock": {
            "length_m": 180,
            "diameter_m": 4.0,
            "roughness_mm": 0.1,
            "minor_loss_k": 0.6,
            "per_unit": True,
        },
        "units": [
            {
                "name": "Agregat 1",
                "type": "Francis",
                "rated_power_mw": 40,
                "rated_head_m": 60,
                "rated_flow_m3s": 75,
                "max_efficiency": 0.92,
            },
            {
                "name": "Agregat 2",
                "type": "Francis",
                "rated_power_mw": 40,
                "rated_head_m": 60,
                "rated_flow_m3s": 75,
                "max_efficiency": 0.92,
            },
        ],
        "operation": {"mode": "target_level", "target_level_m": 903},
    }
