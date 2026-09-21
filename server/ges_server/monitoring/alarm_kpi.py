"""Alarm tizimi KPI (EEMUA-191 3-nashr, ISA-18.2 §16) va toshqin (flood) aniqlash — C4.

Ko'rsatkichlar (faqat bostirilmagan hodisalar; shelved/OOS/shart bo'yicha bostirilganlar alohida sanaladi):
- o'rtacha yuk: soatiga va 10 daqiqaga alarm soni;
- cho'qqi: istalgan 10 daqiqalik oynadagi maksimal soni; toshqin — 10 daqiqada > 10 (EEMUA-191 §6.3);
- toshqin vaqti ulushi: 10 daqiqalik bo'laklarning necha foizi toshqin;
- turg'un (standing) alarmlar: 24 soatdan ortiq faol;
- chattering: bir soat ichida 3+ marta takrorlangan manbalar;
- ustuvorlik taqsimoti (EEMUA maqsadi ~80 / 15 / 5 % past/o'rta/yuqori);
- eng yomon 10 manba va ularning ulushi (maqsad: 10 talik < 20 %, hech biri > 5 % emas);
- kvitlashgacha o'rtacha/mediana vaqt.

EEMUA-191 o'rtacha yuk bahosi (10 daqiqaga): < 1 — maqbul (acceptable), 1–2 — boshqarsa bo'ladi
(manageable), 2–5 — haddan tashqari (over-demanding), 5–10 — juda yuqori, > 10 (daqiqasiga 1 dan ko'p) —
qabul qilib bo'lmaydi (unacceptable).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy.orm import Session

from ..orm import AlarmEvent, Sensor
from .live import _aware

FLOOD_PER_10MIN = 10  # EEMUA-191: 10 daqiqada 10 dan ko'p — toshqin
STANDING_H = 24.0
CHATTER_PER_HOUR = 3
PRIORITY_TARGET_PCT = {"low": 80.0, "medium": 15.0, "high": 5.0, "critical": 0.0}  # EEMUA-191 §6.5


def rate_rating(per_10min: float) -> tuple[str, str]:
    """(baho kodi, izoh) EEMUA-191 o'rtacha yuk jadvali bo'yicha."""
    if per_10min < 1:
        return "acceptable", "maqbul (< 1 alarm / 10 daq)"
    if per_10min < 2:
        return "manageable", "boshqarsa bo'ladi (1–2 / 10 daq)"
    if per_10min < 5:
        return "over_demanding", "haddan tashqari (2–5 / 10 daq)"
    if per_10min <= 10:
        return "very_high", "juda yuqori (5–10 / 10 daq)"
    return "unacceptable", "qabul qilib bo'lmaydi (> 1 alarm / daqiqa)"


def _peak_window(times: list[datetime], window: timedelta) -> int:
    """Saralangan vaqtlar ichida istalgan `window` uzunlikdagi oynadagi maksimal soni (ikki ko'rsatkich)."""
    best, j = 0, 0
    for i, t in enumerate(times):
        while times[j] < t - window + timedelta(microseconds=1):
            j += 1
        best = max(best, i - j + 1)
    return best


def flood_now(db: Session, project_id: int, now: datetime | None = None) -> tuple[bool, int]:
    """Hozir toshqin rejimi: oxirgi 10 daqiqada ochilgan (bostirilmagan) alarmlar soni > 10."""
    now = now or datetime.now(timezone.utc)
    n = (
        db.query(AlarmEvent)
        .filter(
            AlarmEvent.project_id == project_id,
            AlarmEvent.suppressed.is_(None),
            AlarmEvent.started_at >= now - timedelta(minutes=10),
        )
        .count()
    )
    return n > FLOOD_PER_10MIN, n


def kpi(db: Session, project_id: int, since: datetime, until: datetime, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(AlarmEvent)
        .filter(AlarmEvent.project_id == project_id, AlarmEvent.started_at >= since, AlarmEvent.started_at < until)
        .order_by(AlarmEvent.started_at)
        .all()
    )
    sensors = {s.id: s for s in db.query(Sensor).filter_by(project_id=project_id).all()}
    active = [e for e in rows if not e.suppressed]
    suppressed = Counter(e.suppressed for e in rows if e.suppressed)
    hours = max((until - since).total_seconds() / 3600.0, 1e-9)
    total = len(active)
    per_hour = total / hours
    per_10min = per_hour / 6.0
    times = [_aware(e.started_at) for e in active]
    peak10 = _peak_window(times, timedelta(minutes=10))
    # toshqin vaqti ulushi — 10 daqiqalik bo'laklar
    buckets = Counter(int((t - since).total_seconds() // 600) for t in times)
    n_buckets = max(int((until - since).total_seconds() // 600), 1)
    flood_buckets = sum(1 for c in buckets.values() if c > FLOOD_PER_10MIN)
    # turg'un alarmlar (oynadan mustaqil: hozir faol va 24 soatdan eski)
    open_events = (
        db.query(AlarmEvent)
        .filter(AlarmEvent.project_id == project_id, AlarmEvent.ended_at.is_(None), AlarmEvent.suppressed.is_(None))
        .all()
    )
    standing = [e for e in open_events if (now - _aware(e.started_at)).total_seconds() > STANDING_H * 3600]
    # chattering: sensor bo'yicha bir soatlik oynada 3+
    by_sensor: dict[int, list[datetime]] = defaultdict(list)
    for e in active:
        by_sensor[e.sensor_id].append(_aware(e.started_at))
    chattering = []
    for sid, ts in by_sensor.items():
        peak_h = _peak_window(ts, timedelta(hours=1))
        if peak_h >= CHATTER_PER_HOUR:
            s = sensors.get(sid)
            chattering.append({"sensor_id": sid, "key": s.key if s else str(sid), "name": s.name if s else "", "peak_per_hour": peak_h, "count": len(ts)})
    chattering.sort(key=lambda r: -r["peak_per_hour"])
    # ustuvorlik taqsimoti
    prio = Counter((sensors[e.sensor_id].priority or "medium") if e.sensor_id in sensors else "medium" for e in active)
    priority_pct = {p: round(100.0 * prio.get(p, 0) / total, 1) if total else 0.0 for p in ("low", "medium", "high", "critical")}
    # eng yomon 10 manba
    cnt = Counter(e.sensor_id for e in active)
    top = []
    for sid, n in cnt.most_common(10):
        s = sensors.get(sid)
        top.append({"sensor_id": sid, "key": s.key if s else str(sid), "name": s.name if s else "", "count": n, "share_pct": round(100.0 * n / total, 1)})
    top10_share = round(100.0 * sum(t["count"] for t in top) / total, 1) if total else 0.0
    # kvitlash vaqti
    ack_s = [(_aware(e.acked_at) - _aware(e.started_at)).total_seconds() for e in active if e.acked_at is not None]
    unacked = sum(1 for e in open_events if e.acked_at is None)  # hozir faol, kvitlanmagan (oynadan mustaqil)
    rating, rating_note = rate_rating(per_10min)
    is_flood, last10 = flood_now(db, project_id, now)
    verdicts = []
    if rating in ("over_demanding", "very_high", "unacceptable"):
        verdicts.append(f"O'rtacha yuk {per_10min:.1f} / 10 daq — {rating_note}; ratsionalizatsiya va o'lik zona/kechikish kerak (C1, C3)")
    if peak10 > FLOOD_PER_10MIN:
        verdicts.append(f"Toshqin: 10 daqiqada {peak10} alarm (chegara {FLOOD_PER_10MIN}) — suppression-by-design va guruhlashni ko'rib chiqing")
    if standing:
        verdicts.append(f"{len(standing)} ta turg'un alarm (> {STANDING_H:g} soat) — shelving/OOS yoki ta'rifni qayta ko'rish")
    if chattering:
        verdicts.append(f"{len(chattering)} ta chattering manba — deadband/on_delay sozlang")
    if top10_share > 20:
        verdicts.append(f"Eng yomon 10 manba alarmlarning {top10_share:g} % ini beradi (maqsad < 20 %)")
    if total and priority_pct["high"] + priority_pct["critical"] > 20:
        verdicts.append("Yuqori/kritik ustuvorlik ulushi > 20 % — ustuvorlik asosini qayta ko'ring (EEMUA maqsadi ~5 %)")
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "hours": round(hours, 2),
        "total": total,
        "suppressed": dict(suppressed),
        "per_hour": round(per_hour, 2),
        "per_10min": round(per_10min, 2),
        "peak_10min": peak10,
        "flood_threshold_10min": FLOOD_PER_10MIN,
        "flood_time_pct": round(100.0 * flood_buckets / n_buckets, 1),
        "flood_now": is_flood,
        "last_10min": last10,
        "standing": [
            {"event_id": e.id, "sensor_id": e.sensor_id, "key": sensors[e.sensor_id].key if e.sensor_id in sensors else "", "hours": round((now - _aware(e.started_at)).total_seconds() / 3600, 1)}
            for e in standing
        ],
        "chattering": chattering,
        "priority_pct": priority_pct,
        "priority_target_pct": PRIORITY_TARGET_PCT,
        "top10": top,
        "top10_share_pct": top10_share,
        "ack_mean_s": round(sum(ack_s) / len(ack_s), 1) if ack_s else None,
        "ack_median_s": round(median(ack_s), 1) if ack_s else None,
        "unacked_active": unacked,
        "rating": rating,
        "rating_note": rating_note,
        "verdicts": verdicts,
        "reference": "EEMUA-191 (3-nashr) §6; ISA-18.2-2016 §16",
    }
