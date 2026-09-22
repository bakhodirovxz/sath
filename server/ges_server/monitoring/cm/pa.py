"""PA — Prognostics Assessment (ISO 13374-1 §5.6): kelajakdagi holatni baholash.

Trendni chiziqli ekstrapolyatsiya qilib chegaraga yetish muddati hisoblanadi (ISO 13381-1 sodda
usuli): tebranish C va D zonalariga, podshipnik harorati alarm chegarasiga, val tebranishi chegaraga.
Qolgan foydali resurs (RUL) — shu muddatlarning eng kichigi; tashqi tizim (PA bloki) o'z RUL ini bersa,
undan kichigi olinadi. Trend ishonchsiz bo'lsa (nuqta kam, qiyalik manfiy) — `None`.
"""

from __future__ import annotations

from ...orm import Asset
from .sd import VIB_ZONES


def days_to(value: float | None, slope: float | None, limit: float) -> float | None:
    """Chiziqli trend bo'yicha chegaraga yetish muddati, kun (o'sish sekin/manfiy bo'lsa — None)."""
    if value is None or slope is None or slope <= 1e-9 or value >= limit:
        return None
    return round((limit - value) / slope, 0)


def prognose(a: Asset, acq: dict, feats: dict, state: dict, health: dict) -> dict:
    group = acq["machine_group"]
    limits = VIB_ZONES.get(group, VIB_ZONES[4])
    days: dict[str, float | None] = {}

    vib = feats["scalars"].get("vibration")
    if vib and vib["value"] is not None:
        days["vibration_c"] = days_to(vib["value"], vib["slope_per_day"], limits[1])
        days["vibration_d"] = days_to(vib["value"], vib["slope_per_day"], limits[2])

    temp = feats["scalars"].get("bearing_temp")
    item = state["items"].get("bearing_temp")
    if temp and temp["value"] is not None and item:
        days["bearing_temp_alarm"] = days_to(temp["value"], temp["slope_per_day"], item["alarm"])

    shaft = feats["scalars"].get("shaft_vibration")
    sitem = state["items"].get("shaft_vibration")
    if shaft and shaft["value"] is not None and sitem:
        days["shaft_limit"] = days_to(shaft["value"], shaft["slope_per_day"], sitem["limits"][1])

    ext_rul = [e["rul_days"] for e in state["external"] if e["rul_days"] is not None]
    named: list[tuple[str, float]] = [(k, v) for k, v in days.items() if v is not None]
    named += [("external", min(ext_rul))] if ext_rul else []
    basis, rul = min(named, key=lambda kv: kv[1]) if named else (None, None)
    eff_trend = feats["efficiency_trend_pct_per_month"]
    return {
        "days": days,
        "rul_days": rul,
        "rul_basis": basis,
        "external_rul_days": min(ext_rul) if ext_rul else None,
        "efficiency_pct_per_year": round(eff_trend * 12, 2) if eff_trend is not None else None,
    }
