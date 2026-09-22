"""Historian: xom o'lchovlarni qatlamlarga (1 daqiqa, 10 daqiqa, 1 soat) SQL `GROUP BY` bilan yig'ish,
eski xomlarni partiyalab o'chirish (alarm atrofi saqlanadi), davr bo'yicha statistika (hisobotlar uchun)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, cast, func, insert
from sqlalchemy.orm import Session

from ..orm import AlarmEvent, AlarmState, Reading, ReadingAgg, ReadingHourly, Sensor, SystemState
from .live import _aware

log = logging.getLogger("ges_server.historian")


def floor_hour(dt: datetime) -> datetime:
    return _aware(dt).replace(minute=0, second=0, microsecond=0)


def floor_to(dt: datetime, sec: int) -> datetime:
    e = int(_aware(dt).timestamp()) // sec * sec
    return datetime.fromtimestamp(e, tz=timezone.utc)


# Qatlamlar (D2): nom → (soniya, bir tickda ko'pi bilan qancha vaqt yig'iladi, kech kelgan ma'lumot uchun
# qayta hisoblash oynasi). 1h — readings_hourly (abadiy), 1m/10m — readings_agg (config muddati).
TIERS: dict[str, tuple[int, timedelta, timedelta]] = {
    "1m": (60, timedelta(days=1), timedelta(hours=3)),
    "10m": (600, timedelta(days=7), timedelta(hours=6)),
    "1h": (3600, timedelta(days=30), timedelta(hours=24)),
}
MAX_STEPS_PER_TICK = 4  # bitta tickda har qatlam uchun ko'pi bilan shuncha oyna (katta orqada qolishni bosqichma-bosqich)
WM_KEY = "historian.wm."  # SystemState: qatlam suv belgisi (yig'ilgan oxirgi bo'lak tugashi)
PURGE_CURSOR_KEY = "historian.purge_cursor"
PROTECT_AROUND_ALARM = timedelta(hours=1)


def _state_get(db: Session, key: str) -> datetime | None:
    row = db.get(SystemState, key)
    if row is None or not row.value:
        return None
    try:
        return datetime.fromisoformat(row.value)
    except ValueError:
        return None


def _state_set(db: Session, key: str, value: datetime) -> None:
    row = db.get(SystemState, key)
    if row is None:
        db.add(SystemState(key=key, value=value.isoformat()))
    else:
        row.value = value.isoformat()


def _bucket_expr(db: Session, sec: int):
    """Vaqt bo'lagi (epoch // sec) — dialektga qarab SQL ifodasi (agregat SQL da, Python da emas)."""
    if db.bind.dialect.name == "postgresql":
        return func.floor(func.extract("epoch", Reading.ts) / sec)
    # `.op("/")` — SQLAlchemy 2.0 `/` ni NUMERIC ga keltiradi; SQLite butun bo'lish kerak
    return cast(func.strftime("%s", Reading.ts), Integer).op("/")(sec)


def _aggregate(db: Session, sec: int, start: datetime, end: datetime) -> list[tuple]:
    """Barcha sensorlar uchun [start, end) oralig'ini `sec` bo'laklarga SQL `GROUP BY` bilan yig'adi.
    Xotira — bo'laklar soniga proporsional (xom qatorlar soniga emas). Bad qiymatlar agregatga kirmaydi."""
    b = _bucket_expr(db, sec)
    good_val = case((Reading.quality != "bad", Reading.value), else_=None)
    q = (
        db.query(
            Reading.sensor_id,
            b.label("b"),
            func.count(good_val),
            func.avg(good_val),
            func.min(good_val),
            func.max(good_val),
            func.sum(case((Reading.quality == "good", 1), else_=0)),
            func.sum(case((Reading.quality == "bad", 1), else_=0)),
        )
        .filter(Reading.ts >= start, Reading.ts < end)
        .group_by(Reading.sensor_id, b)
        .order_by(Reading.sensor_id, b)
    )
    out = []
    for sid, bk, n, avg, mn, mx, n_good, n_bad in q.all():
        if not n:  # faqat bad bo'lgan bo'lak: avg/min/max yo'q — qator yozilmaydi (bo'shliq = ma'lumot yo'q)
            continue
        out.append((sid, datetime.fromtimestamp(int(bk) * sec, tz=timezone.utc), int(n), float(avg), float(mn), float(mx), int(n_good or 0), int(n_bad or 0)))
    return out


def rollup(db: Session, now: datetime | None = None) -> int:
    """Tugagan bo'laklar uchun qatlamlarni (1m, 10m, 1h) yangilaydi. Qaytaradi: yangi soatlik qatorlar soni.

    Har qatlam o'z suv belgisidan (SystemState) davom etadi; kech kelgan ma'lumot uchun oxirgi
    `lookback` oynasi qayta hisoblanadi (o'chirib qayta yoziladi). Bir tickda ko'pi bilan
    MAX_STEPS_PER_TICK × oyna — katta orqada qolish bosqichma-bosqich yopiladi."""
    now = now or datetime.now(timezone.utc)
    first_ts = db.query(func.min(Reading.ts)).scalar()
    written_1h = 0
    for tier, (sec, window, lookback) in TIERS.items():
        wm = _state_get(db, WM_KEY + tier)
        if wm is None:
            if first_ts is None:
                continue
            wm = floor_to(first_ts, sec)
        end_all = floor_to(now, sec)
        if wm >= end_all:
            continue
        steps = 0
        while wm < end_all and steps < MAX_STEPS_PER_TICK:
            start = wm - lookback
            end = min(end_all, wm + window)
            rows = _aggregate(db, sec, start, end)
            if tier == "1h":
                db.query(ReadingHourly).filter(ReadingHourly.hour >= start, ReadingHourly.hour < end).delete(synchronize_session=False)
                if rows:
                    db.execute(
                        insert(ReadingHourly),
                        [
                            {"sensor_id": sid, "hour": bk, "n": n, "avg": avg, "min": mn, "max": mx, "pct_good": g / (n + nb), "n_bad": nb}
                            for sid, bk, n, avg, mn, mx, g, nb in rows
                        ],
                    )
                written_1h += sum(1 for r in rows if r[1] >= wm)
            else:
                db.query(ReadingAgg).filter(ReadingAgg.tier == tier, ReadingAgg.bucket >= start, ReadingAgg.bucket < end).delete(synchronize_session=False)
                if rows:
                    db.execute(
                        insert(ReadingAgg),
                        [
                            {"sensor_id": sid, "tier": tier, "bucket": bk, "n": n, "avg": avg, "min": mn, "max": mx, "pct_good": g / (n + nb), "n_bad": nb}
                            for sid, bk, n, avg, mn, mx, g, nb in rows
                        ],
                    )
            wm = end
            _state_set(db, WM_KEY + tier, wm)
            db.commit()
            steps += 1
    return written_1h


def watermark(db: Session, tier: str = "1h") -> datetime | None:
    return _state_get(db, WM_KEY + tier)


def _protected_windows(db: Session, lo: datetime, hi: datetime) -> dict[int, list[tuple[datetime, datetime]]]:
    """Alarm hodisalari atrofidagi (±1 soat) himoyalangan oraliqlar, sensor bo'yicha."""
    evs = (
        db.query(AlarmEvent.sensor_id, AlarmEvent.started_at, AlarmEvent.ended_at)
        .filter(AlarmEvent.started_at <= hi + PROTECT_AROUND_ALARM)
        .filter(func.coalesce(AlarmEvent.ended_at, AlarmEvent.started_at) >= lo - PROTECT_AROUND_ALARM)
        .all()
    )
    out: dict[int, list[tuple[datetime, datetime]]] = {}
    for sid, st, en in evs:
        out.setdefault(sid, []).append((_aware(st) - PROTECT_AROUND_ALARM, _aware(en or st) + PROTECT_AROUND_ALARM))
    return out


def purge(db: Session, retention_days: int, now: datetime | None = None, batch: int = 5000, max_batches: int = 20) -> int:
    """retention_days dan eski xom o'lchovlarni partiyalab o'chiradi — faqat soatlik agregati yozilgan
    (suv belgisidan oldingi) qismi; alarm hodisasi atrofidagi ±1 soat saqlanadi (avariya tahlili).
    Kursor (SystemState) himoyalangan qatorlarni qayta-qayta ko'rib chiqmaslik uchun."""
    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    wm = watermark(db, "1h")
    if wm is None:
        return 0
    limit = min(floor_hour(now - timedelta(days=retention_days)), wm)
    cursor = _state_get(db, PURGE_CURSOR_KEY)
    total = 0
    for _ in range(max_batches):
        q = db.query(Reading.id, Reading.sensor_id, Reading.ts).filter(Reading.ts < limit)
        if cursor is not None:
            q = q.filter(Reading.ts >= cursor)
        rows = q.order_by(Reading.ts).limit(batch).all()
        if not rows:
            break
        lo, hi = _aware(rows[0][2]), _aware(rows[-1][2])
        prot = _protected_windows(db, lo, hi)
        ids = [
            rid
            for rid, sid, ts in rows
            if not any(a <= _aware(ts) <= b for a, b in prot.get(sid, ()))
        ]
        for i in range(0, len(ids), 900):  # SQLite o'zgaruvchilar chegarasi
            db.query(Reading).filter(Reading.id.in_(ids[i : i + 900])).delete(synchronize_session=False)
        total += len(ids)
        cursor = hi
        _state_set(db, PURGE_CURSOR_KEY, cursor)
        db.commit()
        if len(rows) < batch:
            break
    return total


def purge_agg(db: Session, tier: str, retention_days: int, now: datetime | None = None, batch: int = 20000) -> int:
    """1m/10m qatlamining eski bo'laklarini partiyalab o'chiradi."""
    if retention_days <= 0 or tier not in ("1m", "10m"):
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    total = 0
    while True:
        ids = [i for (i,) in db.query(ReadingAgg.id).filter(ReadingAgg.tier == tier, ReadingAgg.bucket < cutoff).limit(batch).all()]
        if not ids:
            break
        for i in range(0, len(ids), 900):
            db.query(ReadingAgg).filter(ReadingAgg.id.in_(ids[i : i + 900])).delete(synchronize_session=False)
        db.commit()
        total += len(ids)
        if len(ids) < batch:
            break
    return total


def tier_for_span(hours: float) -> str:
    """Grafik uchun qatlam: ≤ 6 soat xom, ≤ 48 soat 1 daqiqa, ≤ 96 soat 10 daqiqa, undan uzoq — soatlik."""
    if hours <= 6:
        return "raw"
    if hours <= 48:
        return "1m"
    if hours <= 96:
        return "10m"
    return "1h"


def tier_points(db: Session, sensor_id: int, tier: str, since: datetime, until: datetime) -> list[dict]:
    """Qatlam nuqtalari + hali yig'ilmagan dum (suv belgisidan keyingi xom, shu bo'lak o'lchamida)."""
    sec = TIERS[tier][0]
    if tier == "1h":
        pts = hourly_points(db, sensor_id, since, until)
    else:
        rows = (
            db.query(ReadingAgg)
            .filter(ReadingAgg.sensor_id == sensor_id, ReadingAgg.tier == tier, ReadingAgg.bucket >= since, ReadingAgg.bucket < until)
            .order_by(ReadingAgg.bucket)
            .all()
        )
        pts = [
            {"ts": _aware(r.bucket).isoformat(), "v": round(r.avg, 4), "min": round(r.min, 4), "max": round(r.max, 4), "pct_good": round(r.pct_good, 3)}
            for r in rows
        ]
    wm = watermark(db, tier)
    tail_since = max(since, wm) if wm else since
    if pts:
        tail_since = max(tail_since, datetime.fromisoformat(pts[-1]["ts"]) + timedelta(seconds=sec))
    raw = (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == sensor_id, Reading.ts >= tail_since, Reading.ts < until, Reading.quality != "bad")
        .order_by(Reading.ts)
        .all()
    )
    buckets: dict[datetime, list[float]] = {}
    for t, v in raw:
        buckets.setdefault(floor_to(t, sec), []).append(v)
    for bk, vals in sorted(buckets.items()):
        pts.append({"ts": bk.isoformat(), "v": round(sum(vals) / len(vals), 4), "min": round(min(vals), 4), "max": round(max(vals), 4)})
    return pts


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
            "pct_good": round(r.pct_good if r.pct_good is not None else 1.0, 3),
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
        .filter(
            Reading.sensor_id == sensor.id,
            Reading.ts >= raw_since,
            Reading.ts < until,
            Reading.quality != "bad",
        )
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
