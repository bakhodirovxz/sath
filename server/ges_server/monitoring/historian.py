"""Historian: xom o'lchovlarni qatlamlarga (1 daqiqa, 10 daqiqa, 1 soat) SQL `GROUP BY` bilan yig'ish,
eski xomlarni partiyalab o'chirish (alarm atrofi saqlanadi), davr bo'yicha statistika (hisobotlar uchun).

Kech kelgan ma'lumot (SCADA-10): qatlam suv belgisidan `lookback` dan oldingi davrga yozilgan xom
o'lchovlar (tarixiy CSV import, gateway store-and-forward, MQTT backfill) oddiy rollup oynasiga
tushmaydi. Rollup har tickda yangi qatorlarni (`Reading.id` kursori — barcha ingest yo'llari, ilgak
kerak emas) tekshiradi va shunday oraliqlarni `historian_dirty` ga yozadi (`mark_dirty` — ochiq API);
keyin ularni sensor bo'yicha qayta yig'adi. Purge yig'ilmagan (dirty yoki hali skanerlanmagan) xom
qatorlarni o'chirmaydi — ma'lumot yo'qolmaydi.
Postgres: parallel tranzaksiyalar id ni tartibsiz commit qilsa (kichik id kechroq ko'rinadi), skaner
uni o'tkazib yuborishi mumkin — `mark_dirty` ni import yo'lidan to'g'ridan-to'g'ri ham chaqirish mumkin."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, cast, func, insert
from sqlalchemy.orm import Session

from ..orm import (
    AlarmEvent,
    AlarmState,
    HistorianDirty,
    Reading,
    ReadingAgg,
    ReadingHourly,
    Sensor,
    SystemState,
)
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
SCAN_KEY = "historian.scan_id"  # oxirgi skanerlangan Reading.id (kech kelgan ma'lumotni aniqlash)
MAX_DIRTY_CHUNKS_PER_TICK = 16  # bir tickda qayta yig'iladigan dirty oynalar soni (katta import bosqichma-bosqich)
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


def _aggregate(
    db: Session, sec: int, start: datetime, end: datetime, sensor_id: int | None = None
) -> list[tuple]:
    """Barcha sensorlar (yoki bitta `sensor_id`) uchun [start, end) oralig'ini `sec` bo'laklarga SQL
    `GROUP BY` bilan yig'adi. Xotira — bo'laklar soniga proporsional (xom qatorlar soniga emas).
    Bad qiymatlar agregatga kirmaydi."""
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
    if sensor_id is not None:
        q = q.filter(Reading.sensor_id == sensor_id)
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
    scan_late(db)
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
            rows = _rewrite(db, tier, sec, start, end)
            if tier == "1h":
                written_1h += sum(1 for r in rows if r[1] >= wm)
            wm = end
            _state_set(db, WM_KEY + tier, wm)
            db.commit()
            steps += 1
    process_dirty(db)
    return written_1h


def _rewrite(
    db: Session, tier: str, sec: int, start: datetime, end: datetime, sensor_id: int | None = None
) -> list[tuple]:
    """[start, end) qatlam bo'laklarini o'chirib qayta yozadi (hamma sensor yoki bitta)."""
    rows = _aggregate(db, sec, start, end, sensor_id)
    if tier == "1h":
        q = db.query(ReadingHourly).filter(ReadingHourly.hour >= start, ReadingHourly.hour < end)
        if sensor_id is not None:
            q = q.filter(ReadingHourly.sensor_id == sensor_id)
        q.delete(synchronize_session=False)
        if rows:
            db.execute(
                insert(ReadingHourly),
                [
                    {"sensor_id": sid, "hour": bk, "n": n, "avg": avg, "min": mn, "max": mx, "pct_good": g / (n + nb), "n_bad": nb}
                    for sid, bk, n, avg, mn, mx, g, nb in rows
                ],
            )
    else:
        q = db.query(ReadingAgg).filter(ReadingAgg.tier == tier, ReadingAgg.bucket >= start, ReadingAgg.bucket < end)
        if sensor_id is not None:
            q = q.filter(ReadingAgg.sensor_id == sensor_id)
        q.delete(synchronize_session=False)
        if rows:
            db.execute(
                insert(ReadingAgg),
                [
                    {"sensor_id": sid, "tier": tier, "bucket": bk, "n": n, "avg": avg, "min": mn, "max": mx, "pct_good": g / (n + nb), "n_bad": nb}
                    for sid, bk, n, avg, mn, mx, g, nb in rows
                ],
            )
    return rows


def mark_dirty(db: Session, sensor_id: int, ts_min: datetime, ts_max: datetime) -> int:
    """Sensorning [ts_min, ts_max] oralig'ini qayta yig'ishga belgilaydi — faqat suv belgisi va
    `lookback` dan oldingi qismi bo'lgan qatlamlar uchun (qolgani oddiy rollup oynasida). Purge
    kursorini ham orqaga suradi (eski import ham keyin retention bo'yicha tozalanadi). Commit qilmaydi.
    Qaytaradi: yozilgan dirty qatorlar soni."""
    ts_min, ts_max = _aware(ts_min), _aware(ts_max)
    if ts_max < ts_min:
        ts_min, ts_max = ts_max, ts_min
    n = 0
    for tier, (sec, _window, lookback) in TIERS.items():
        wm = _state_get(db, WM_KEY + tier)
        if wm is None or ts_min >= wm - lookback:
            continue
        db.add(
            HistorianDirty(
                tier=tier, sensor_id=sensor_id, ts_min=floor_to(ts_min, sec), ts_max=min(ts_max, wm)
            )
        )
        n += 1
    if n:
        cur = _state_get(db, PURGE_CURSOR_KEY)
        if cur is not None and ts_min < _aware(cur):
            _state_set(db, PURGE_CURSOR_KEY, ts_min)
    return n


def scan_late(db: Session) -> int:
    """Oxirgi skanerdan keyin yozilgan xom qatorlar ichidan qatlam oynasidan eski (ts < wm − lookback)
    bo'lganlarini sensor bo'yicha topib `mark_dirty` qiladi. Birinchi chaqiruvda faqat kursor
    o'rnatiladi (avvalgi tarix skanerlanmaydi). Qaytaradi: belgilangan sensorlar soni."""
    max_id = db.query(func.max(Reading.id)).scalar()
    row = db.get(SystemState, SCAN_KEY)
    cur = int(row.value) if row is not None and (row.value or "").isdigit() else None
    if max_id is None or (cur is not None and max_id <= cur):
        return 0
    marked = 0
    if cur is not None:
        thresholds = [
            _aware(wm) - lookback
            for tier, (_s, _w, lookback) in TIERS.items()
            if (wm := _state_get(db, WM_KEY + tier)) is not None
        ]
        if thresholds:
            late = (
                db.query(Reading.sensor_id, func.min(Reading.ts), func.max(Reading.ts))
                .filter(Reading.id > cur, Reading.id <= max_id, Reading.ts < max(thresholds))
                .group_by(Reading.sensor_id)
                .all()
            )
            for sid, t0, t1 in late:
                if mark_dirty(db, sid, t0, t1):
                    marked += 1
    if row is None:
        db.add(SystemState(key=SCAN_KEY, value=str(max_id)))
    else:
        row.value = str(max_id)
    db.commit()
    if marked:
        log.info("historian: %d sensorda kech kelgan ma'lumot — qayta yig'iladi", marked)
    return marked


def process_dirty(db: Session, max_chunks: int = MAX_DIRTY_CHUNKS_PER_TICK) -> int:
    """Dirty oraliqlarni qatlam oynasi bo'laklarida qayta yig'adi; tugaganini o'chiradi, qolganining
    ts_min ni suradi. Qaytaradi: qayta yig'ilgan oynalar soni."""
    chunks = 0
    for d in db.query(HistorianDirty).order_by(HistorianDirty.id).all():
        sec, window, _lookback = TIERS[d.tier]
        wm = _state_get(db, WM_KEY + d.tier)
        start = floor_to(d.ts_min, sec)
        end_lim = floor_to(d.ts_max, sec) + timedelta(seconds=sec)
        if wm is not None:
            end_lim = min(end_lim, _aware(wm))
        while start < end_lim and chunks < max_chunks:
            end = min(end_lim, start + window)
            _rewrite(db, d.tier, sec, start, end, d.sensor_id)
            start = end
            chunks += 1
        if start >= end_lim:
            db.delete(d)
        else:
            d.ts_min = start
        db.commit()
        if chunks >= max_chunks:
            break
    return chunks


def _dirty_windows(db: Session) -> dict[int, list[tuple[datetime, datetime]]]:
    """1h qatlami hali qayta yig'ilmagan oraliqlar, sensor bo'yicha (purge ularni o'chirmaydi)."""
    out: dict[int, list[tuple[datetime, datetime]]] = {}
    for sid, a, b in db.query(HistorianDirty.sensor_id, HistorianDirty.ts_min, HistorianDirty.ts_max).filter(
        HistorianDirty.tier == "1h"
    ):
        out.setdefault(sid, []).append((_aware(a), _aware(b) + timedelta(hours=1)))
    return out


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
    Kursor (SystemState) himoyalangan qatorlarni qayta-qayta ko'rib chiqmaslik uchun.
    SCADA-10: hali skanerlanmagan (id > scan kursori) va 1h qatlamida qayta yig'ilmagan (dirty) xom
    qatorlar o'chirilmaydi; dirty qator uchun kursor shu qator vaqtidan oldinga o'tmaydi."""
    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    wm = watermark(db, "1h")
    if wm is None:
        return 0
    limit = min(floor_hour(now - timedelta(days=retention_days)), wm)
    cursor = _state_get(db, PURGE_CURSOR_KEY)
    scan_row = db.get(SystemState, SCAN_KEY)
    scanned = int(scan_row.value) if scan_row is not None and (scan_row.value or "").isdigit() else None
    dirty = _dirty_windows(db)
    keep_from: datetime | None = None  # eng erta saqlangan dirty qator — persist kursor undan oshmaydi
    total = 0
    for _ in range(max_batches):
        q = db.query(Reading.id, Reading.sensor_id, Reading.ts).filter(Reading.ts < limit)
        if scanned is not None:
            q = q.filter(Reading.id <= scanned)
        if cursor is not None:
            q = q.filter(Reading.ts >= cursor)
        rows = q.order_by(Reading.ts).limit(batch).all()
        if not rows:
            break
        lo, hi = _aware(rows[0][2]), _aware(rows[-1][2])
        prot = _protected_windows(db, lo, hi)
        ids = []
        for rid, sid, ts in rows:
            t = _aware(ts)
            if any(a <= t < b for a, b in dirty.get(sid, ())):
                keep_from = t if keep_from is None else min(keep_from, t)
                continue
            if not any(a <= t <= b for a, b in prot.get(sid, ())):
                ids.append(rid)
        for i in range(0, len(ids), 900):  # SQLite o'zgaruvchilar chegarasi
            db.query(Reading).filter(Reading.id.in_(ids[i : i + 900])).delete(synchronize_session=False)
        total += len(ids)
        cursor = hi
        _state_set(db, PURGE_CURSOR_KEY, min(cursor, keep_from) if keep_from is not None else cursor)
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


def bucketed(db: Session, sensor_id: int, since: datetime, until: datetime, sec: int) -> list[dict]:
    """Xom o'lchovlarni `sec` soniyalik bo'laklarga SQL da yig'adi (avg/min/max) — grafik siyraklashtirish."""
    b = _bucket_expr(db, sec)
    rows = (
        db.query(b.label("b"), func.avg(Reading.value), func.min(Reading.value), func.max(Reading.value))
        .filter(Reading.sensor_id == sensor_id, Reading.ts >= since, Reading.ts < until, Reading.quality != "bad")
        .group_by(b)
        .order_by(b)
        .all()
    )
    return [
        {"ts": datetime.fromtimestamp(int(bk) * sec, tz=timezone.utc).isoformat(), "v": round(avg, 4), "min": round(mn, 4), "max": round(mx, 4)}
        for bk, avg, mn, mx in rows
    ]


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
    # Yig'ilmagan dum — SQL agregat (D4): qatorlar RAM ga yuklanmaydi
    raw_n, raw_sum, raw_min, raw_max = (
        db.query(func.count(Reading.id), func.sum(Reading.value), func.min(Reading.value), func.max(Reading.value))
        .filter(
            Reading.sensor_id == sensor.id,
            Reading.ts >= raw_since,
            Reading.ts < until,
            Reading.quality != "bad",
        )
        .one()
    )
    raw_n = int(raw_n or 0)
    n = sum(h.n for h in hourly) + raw_n
    if n == 0:
        return {"n": 0, "avg": None, "min": None, "max": None, "energy_mwh": None}
    total = sum(h.avg * h.n for h in hourly) + float(raw_sum or 0.0)
    mn = min([h.min for h in hourly] + ([float(raw_min)] if raw_n else []))
    mx = max([h.max for h in hourly] + ([float(raw_max)] if raw_n else []))
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
        if raw_n:
            span_h = (until - raw_since).total_seconds() / 3600
            e += float(raw_sum) / raw_n * min(span_h, 1e9) * scale
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
