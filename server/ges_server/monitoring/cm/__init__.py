"""Holat monitoringi (H3) — ISO 13374-1/-2 (OSA-CBM) funksional bloklari:

    DA  (data acquisition)      — `da.py`  : xom kanallar, sensor bloklari, spektr yozuvlari
    DM  (data manipulation)     — `dm.py`  : trend, z-score, spektr xususiyatlari (podshipnik chastotalari)
    SD  (state detection)       — `sd.py`  : ISO 20816-5 zonalari, chegaralar, anomaliya, tashqi holat
    HA  (health assessment)     — `ha.py`  : sog'liq indeksi va tashxis (kavitatsiya, FIK, transformator)
    PA  (prognostics assessment)— `pa.py`  : C/D zonasigacha kun, RUL, FIK degradatsiyasi
    AG  (advisory generation)   — `ag.py`  : muammo/tavsiya matni, avtomatik ish buyrug'i

Bloklar orasidagi interfeys — oddiy dict: har blok oldingisining natijasini oladi va o'zinikini
qaytaradi (`blocks` kalitida yig'iladi), shuning uchun uchinchi tomon tizimi istalgan darajadan
(`SD`, `HA`, `PA`) natija berib qo'shila oladi (`cm_results` jadvali, `sd.external_states`).

Umumiy natija tuzilmasi eski `health.compute` bilan mos (web interfeysi uchun): `score`, `level`,
`vibration`, `bearing_temp`, `efficiency`, `cavitation`, `electrical`, `problems`, `tips`,
`machine_group` — ustiga `blocks`, `external`, `spectrum`, `prognosis` qo'shildi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...orm import Asset, Project, Sensor
from .. import twin
from . import ag, da, dm, ha, pa, sd

__all__ = [
    "ag",
    "asset_health",
    "auto_work_orders",
    "compute",
    "da",
    "dm",
    "ha",
    "pa",
    "publish",
    "sd",
    "tick_hourly",
]


def asset_health(
    db: Session, project: Project, a: Asset, twin_state: dict | None, slots: dict[str, Sensor]
) -> dict:
    """Bitta aktiv uchun ISO 13374 zanjiri: DA → DM → SD → HA → PA → AG."""
    acq = da.acquire(db, project, a, twin_state, slots)
    feats = dm.features(db, a, acq)
    state = sd.detect(db, a, acq, feats)
    health = ha.assess(db, project, a, acq, feats, state)
    prog = pa.prognose(a, acq, feats, state, health)
    advice = ag.advise(a, acq, feats, state, health, prog)
    return ha.render(a, acq, feats, state, health, prog, advice)


def compute(db: Session, project: Project) -> dict:
    """Loyiha bo'yicha sog'liq hisoboti (barcha aktivlar + stansiya ballari)."""
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    ts = twin.compute(db, project)
    assets = db.query(Asset).filter_by(project_id=project.id).order_by(Asset.name).all()
    items = [asset_health(db, project, a, ts, slots) for a in assets]
    maint = {x["id"]: x for x in twin.asset_status(db, project)}
    for it in items:
        ha.apply_maintenance(it, maint.get(it["asset_id"]))
    plant = round(sum(i["score"] for i in items) / len(items)) if items else None
    return {"plant_score": plant, "assets": items, "twin_status": ts.get("status")}


def publish(db: Session, project: Project) -> dict:
    """Sog'liq indekslarini HEALTH.<asset> virtual sensorlariga yozish (trend, alarm < 60)."""
    return ag.publish(db, project, compute(db, project))


def auto_work_orders(db: Session, project: Project, report: dict) -> int:
    return ag.auto_work_orders(db, project, report)


def tick_hourly(db: Session) -> int:
    """Fon (soatlik): aktivlari bor barcha loyihalar uchun sog'liq indeksi."""
    n = 0
    for pid in {a.project_id for a in db.query(Asset.project_id).all()}:
        project = db.get(Project, pid)
        if project is not None:
            auto_work_orders(db, project, publish(db, project))
            n += 1
    return n
