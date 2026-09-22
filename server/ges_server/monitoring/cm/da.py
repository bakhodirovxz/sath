"""DA — Data Acquisition (ISO 13374-1 §5.2): xom kanallarni yig'ish.

Bu blok faqat *oladi*: aktivning sensor kanallari (tebranish, podshipnik harorati, quvvat), ularning
oxirgi qiymati va soatlik qatori, oxirgi spektr yozuvlari va egizak holati. Hech qanday baho bermaydi —
chegara va zona SD blokida, tashxis HA blokida.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...orm import Asset, Project, ReadingHourly, Sensor, Spectrum
from .. import live, twin

CHANNELS = {  # kanal → aktiv konfiguratsiyasidagi kalit
    "vibration": "vibration_sensor_id",
    "bearing_temp": "bearing_temp_sensor_id",
    "shaft_vibration": "shaft_vibration_sensor_id",  # val nisbiy tebranishi (ISO 20816-5 B ilova)
    "air_gap": "air_gap_sensor_id",  # generator havo oralig'i
    "partial_discharge": "pd_sensor_id",  # qisman razryad (IEC 60270)
    "oil_water": "oil_water_sensor_id",  # moy tahlili: suv miqdori
}


def hourly(db: Session, sensor_id: int, days: int = 30) -> list[tuple[datetime, float]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(ReadingHourly.hour, ReadingHourly.avg)
        .filter(ReadingHourly.sensor_id == sensor_id, ReadingHourly.hour >= since)
        .order_by(ReadingHourly.hour)
        .all()
    )
    return [(live._aware(h), float(v)) for h, v in rows]


def channel(db: Session, s: Sensor | None, days: int = 30) -> dict | None:
    """Bitta kanal: sensor, oxirgi qiymat, aloqa holati va soatlik qator (DM bloki uchun)."""
    if s is None:
        return None
    return {
        "sensor_id": s.id,
        "key": s.key,
        "name": s.name,
        "unit": s.unit,
        "value": twin._live(s),
        "stale": bool(s.stale),
        "quality": s.last_quality,
        "series": hourly(db, s.id, days),
    }


def latest_spectra(db: Session, asset_id: int, limit: int = 4) -> list[Spectrum]:
    return (
        db.query(Spectrum)
        .filter(Spectrum.asset_id == asset_id)
        .order_by(Spectrum.ts.desc())
        .limit(limit)
        .all()
    )


def machine_group(db: Session, a: Asset) -> int:
    """ISO 20816-5 mashina guruhi: aktiv konfiguratsiyasi → ota aktivlar (H1 ierarxiyasi) → KKS tizimi
    kaliti bo'yicha taxmin → 4 (vertikal, yuqori podshipnik statorga — GES uchun keng tarqalgan).

    Guruhlar (ISO 20816-5 A ilova): 1 — gorizontal val, >300 ayl/min; 2 — gorizontal (kapsula/bulb),
    ≤300; 3 — vertikal, barcha podshipnik poydevorga; 4 — vertikal, yuqori podshipnik statorga."""
    node: Asset | None = a
    seen: set[int] = set()
    while node is not None and node.id not in seen:
        seen.add(node.id)
        g = (node.config or {}).get("machine_group")
        if g:
            return int(g)
        node = db.get(Asset, node.parent_id) if node.parent_id else None
    code = (a.kks_code or "").replace("=", "").strip()
    sys_key = code[1:4] if code[:1].isdigit() else code[:3]
    if sys_key in ("MAA", "MAB", "MAV"):  # gidroturbina tizimi
        rpm = float((a.config or {}).get("rated_speed_rpm") or 0)
        return 2 if 0 < rpm <= 300 else 4
    if sys_key in ("MKA", "MKC", "MKF"):  # generator — vertikal mashina
        return 4
    return 4


def acquire(
    db: Session, project: Project, a: Asset, twin_state: dict | None, slots: dict[str, Sensor]
) -> dict:
    """DA natijasi: kanallar, spektrlar, egizak agregat holati va aktiv konfiguratsiyasi."""
    cfg = a.config or {}
    channels: dict[str, dict | None] = {}
    for name, key in CHANNELS.items():
        sid = cfg.get(key)
        channels[name] = channel(db, db.get(Sensor, sid) if sid else None)
    unit = None
    if twin_state and a.power_sensor_id:
        unit = next(
            (u for u in twin_state.get("units", []) if u["sensor_id"] == a.power_sensor_id), None
        )
    eff_sensor = (
        db.query(Sensor)
        .filter_by(project_id=project.id, key=f"TWIN.{a.power_sensor_id}.EFF")
        .first()
        if a.power_sensor_id
        else None
    )
    return {
        "asset_id": a.id,
        "config": cfg,
        "machine_group": machine_group(db, a),
        "channels": channels,
        "spectra": latest_spectra(db, a.id),
        "unit": unit,
        "efficiency_series": hourly(db, eff_sensor.id) if eff_sensor else [],
        "power": twin._live(db.get(Sensor, a.power_sensor_id)) if a.power_sensor_id else None,
        "downstream_level": twin._live(slots.get("downstream_level")),
    }
