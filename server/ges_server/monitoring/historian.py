"""Historian: xom o'lchovlarni soatlik agregatga yig'ish, eski xomlarni o'chirish, davr bo'yicha
statistika (hisobotlar uchun)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..orm import AlarmEvent, AlarmState, Reading, ReadingHourly, Sensor
from .live import _aware

log = logging.getLogger("ges_server.historian")


def floor_hour(dt: datetime) -> datetime:
    return _aware(dt).replace(minute=0, second=0, microsecond=0)


def rollup(db: Session, now: datetime | None = None) -> int:
    """Tugagan soatlar uchun (joriy soat emas) agregat yozadi. Qaytaradi: yangi qatorlar soni.

    Har sensor uchun oxirgi agregatdan keyingi soatlar; hech qachon qilinmagan bo'lsa — xom
    o'lchovlarning eng eski soatidan boshlab."""
    now = now or datetime.now(timezone.utc)
    current_hour = floor_hour(now)
    written = 0
    for (sensor_id,) in db.query(Sensor.id).all():
        last = db.query(func.max(ReadingHourly.hour)).filter_by(sensor_id=sensor_id).scalar()
        if last is not None:
            start = _aware(last) + timedelta(hours=1)
        else:
            first = db.query(func.min(Reading.ts)).filter_by(sensor_id=sensor_id).scalar()
            if first is None:
                continue
            start = floor_hour(first)
        if start >= current_hour:
            continue
        rows = (
            db.query(Reading.ts, Reading.value)
            .filter(Reading.sensor_id == sensor_id, Reading.ts >= start, Reading.ts < current_hour)
            .all()
        )
        buckets: dict[datetime, list[float]] = {}
        for ts, v in rows:
            buckets.setdefault(floor_hour(ts), []).append(v)
        for hour, vals in buckets.items():
            db.add(
                ReadingHourly(
                    sensor_id=sensor_id,
                    hour=hour,
                    n=len(vals),
                    avg=sum(vals) / len(vals),
                    min=min(vals),
                    max=max(vals),
                )
            )
            written += 1
    if written:
        db.commit()
    return written


def purge(db: Session, retention_days: int, now: datetime | None = None) -> int:
    """retention_days dan eski xom o'lchovlarni o'chiradi (faqat agregati yozilgan soatlar)."""
    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = floor_hour(now - timedelta(days=retention_days))
    total = 0
    for (sensor_id,) in db.query(Sensor.id).all():
        last = db.query(func.max(ReadingHourly.hour)).filter_by(sensor_id=sensor_id).scalar()
        if last is None:
            continue
        limit = min(cutoff, _aware(last) + timedelta(hours=1))
        total += (
            db.query(Reading)
            .filter(Reading.sensor_id == sensor_id, Reading.ts < limit)
            .delete(synchronize_session=False)
        )
    if total:
        db.commit()
    return total


def hourly_points(db: Session, sensor_id: int, since: datetime, until: datetime) -> list[dict]:
    rows = (
        db.query(ReadingHourly)
        .filter(
            ReadingHourly.sensor_id == sensor_id,
            ReadingHourly.hour >= since,
            ReadingHourly.hour < until,
        )
        .order_by(ReadingHourly.hour)
        .all()
    )
    return [
        {
            "ts": _aware(r.hour).isoformat(),
            "v": round(r.avg, 4),
            "min": round(r.min, 4),
            "max": round(r.max, 4),
        }
        for r in rows
    ]


def sensor_stats(db: Session, sensor: Sensor, since: datetime, until: datetime) -> dict:
    """Davr statistikasi: soatlik agregat + hali yig'ilmagan xom o'lchovlar birga."""
    hourly = (
        db.query(ReadingHourly)
        .filter(
            ReadingHourly.sensor_id == sensor.id,
            ReadingHourly.hour >= floor_hour(since),
            ReadingHourly.hour < until,
        )
        .all()
    )
    last_hour = max((_aware(h.hour) for h in hourly), default=None)
    raw_since = max(since, last_hour + timedelta(hours=1)) if last_hour else since
    raw = (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == sensor.id, Reading.ts >= raw_since, Reading.ts < until)
        .all()
    )
    n = sum(h.n for h in hourly) + len(raw)
    if n == 0:
        return {"n": 0, "avg": None, "min": None, "max": None, "energy_mwh": None}
    total = sum(h.avg * h.n for h in hourly) + sum(v for _, v in raw)
    mn = min([h.min for h in hourly] + [v for _, v in raw])
    mx = max([h.max for h in hourly] + [v for _, v in raw])
    out = {
        "n": n,
        "avg": round(total / n, 4),
        "min": round(mn, 4),
        "max": round(mx, 4),
        "energy_mwh": None,
    }
    if sensor.kind == "power":
        # Quvvat (MW yoki kW) → energiya: soatlik o'rtacha × 1 soat; xom qism — o'rtacha × davr ulushi
        scale = 0.001 if sensor.unit.lower().startswith("kw") else 1.0
        e = sum(h.avg for h in hourly) * scale
        if raw:
            span_h = (until - raw_since).total_seconds() / 3600
            e += sum(v for _, v in raw) / len(raw) * min(span_h, 1e9) * scale
        out["energy_mwh"] = round(e, 3)
    return out


def alarm_stats(db: Session, project_id: int, since: datetime, until: datetime) -> dict:
    events = (
        db.query(AlarmEvent)
        .filter(
            AlarmEvent.project_id == project_id,
            AlarmEvent.started_at >= since,
            AlarmEvent.started_at < until,
        )
        .all()
    )
    by_state = {s.value: 0 for s in AlarmState if s != AlarmState.ok}
    for e in events:
        by_state[e.state.value] += 1
    unacked = sum(1 for e in events if e.acked_at is None)
    return {"count": len(events), "by_state": by_state, "unacked": unacked}


def period_bounds(period: str, start: datetime | None, now: datetime) -> tuple[datetime, datetime]:
    if start is None:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "month":
            start = start.replace(day=1)
        elif period == "week":
            start -= timedelta(days=start.weekday())
    if period == "day":
        end = start + timedelta(days=1)
    elif period == "week":
        end = start + timedelta(days=7)
    else:
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, min(end, now)


def build_report(
    db: Session, project, period: str, start: datetime | None, now: datetime | None = None
) -> dict:
    """Davr hisoboti (JSON): sensorlar statistikasi, energiya, alarmlar. Web/CSV/email uchun."""
    now = now or datetime.now(timezone.utc)
    start, end = period_bounds(period, start, now)
    sensors = db.query(Sensor).filter_by(project_id=project.id).order_by(Sensor.name).all()
    rows, energy = [], 0.0
    for s in sensors:
        st = sensor_stats(db, s, start, end)
        if st["energy_mwh"] is not None and s.protocol != "twin":
            energy += st["energy_mwh"]
        rows.append(
            {"sensor_id": s.id, "key": s.key, "name": s.name, "kind": s.kind, "unit": s.unit, **st}
        )
    return {
        "project": project.name,
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "energy_mwh": round(energy, 3),
        "alarms": alarm_stats(db, project.id, start, end),
        "sensors": rows,
    }


def report_text(rep: dict) -> str:
    """Email uchun oddiy matn."""
    lines = [
        f"Sath kunlik hisobot — {rep['project']}",
        f"Davr: {rep['start'][:16]} — {rep['end'][:16]} (UTC)",
        f"Energiya: {rep['energy_mwh']:.1f} MWh",
        f"Alarmlar: {rep['alarms']['count']} (yuqori {rep['alarms']['by_state'].get('high', 0)}, "
        f"past {rep['alarms']['by_state'].get('low', 0)}, aloqa {rep['alarms']['by_state'].get('stale', 0)}), "
        f"kvitlanmagan {rep['alarms']['unacked']}",
        "",
        "Sensor | o'rtacha | min | max",
    ]
    for r in rep["sensors"]:
        if r["n"]:
            lines.append(f"{r['name']} ({r['unit']}) | {r['avg']} | {r['min']} | {r['max']}")
    return chr(10).join(lines)
