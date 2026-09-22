"""Sog'liq indeksi — `monitoring/cm/` (ISO 13374 / OSA-CBM bloklari) ustidagi yupqa moslik qatlami.

H3 dan oldin butun holat monitoringi shu faylda edi (190 qatorli `asset_health`); endi u DA → DM → SD →
HA → PA → AG bloklariga ajratilgan (`cm/da.py`, `cm/dm.py`, `cm/sd.py`, `cm/ha.py`, `cm/pa.py`,
`cm/ag.py`). Bu modul eski nomlarni (mavjud chaqiruvlar va testlar uchun) saqlab qoladi.
"""

from __future__ import annotations

from . import cm
from .cm.dm import trend
from .cm.ha import H_VAP, level_for, specific_speed, thoma_critical
from .cm.pa import days_to as _days_to
from .cm.sd import VIB_ZONES, ZONE_NOTE, vib_zone

asset_health = cm.asset_health
compute = cm.compute
publish = cm.publish
auto_work_orders = cm.auto_work_orders
tick_hourly = cm.tick_hourly

__all__ = [
    "H_VAP",
    "VIB_ZONES",
    "ZONE_NOTE",
    "_days_to",
    "asset_health",
    "auto_work_orders",
    "cm",
    "compute",
    "level_for",
    "publish",
    "specific_speed",
    "thoma_critical",
    "tick_hourly",
    "trend",
    "vib_zone",
]
