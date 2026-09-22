"""SOE — hodisalar ketma-ketligi (Sequence of Events, D3): millisekundli diskret hodisalar (himoya trip,
uzgich holati, zatvor STUCK …) alohida jadvalda; hech qachon agregat qilinmaydi, o'z saqlash muddati.

Manba: gateway (IEC 104 vaqt tamg'ali M_SP_TB_1/M_DP_TB_1, OPC UA SourceTimestamp) yoki simulyator.
Takroriy yuborish (spool qayta urinishi) `(project, source, point, ts_ms, state)` unikal kaliti bilan
tashlab yuboriladi. Tartib `ts_ms` (epoch millisekund) bo'yicha — 1 ms aniqlik saqlanadi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from ..orm import AlarmEvent, Sensor, SequenceEvent
from .live import STATE_LABEL, _aware, _parse_ts


def _to_ms(v) -> int | None:
    """ISO/epoch → epoch millisekund (float epoch dagi kasr ham). Yaroqsiz → None."""
    if isinstance(v, int | float) and not isinstance(v, bool):
        try:
            dt = _parse_ts(v)
        except (OverflowError, ValueError):
            return None
        return int(round(v * 1000)) if dt is not None else None
    dt = _parse_ts(v)
    if dt is None:
        return None
    return int(round(dt.timestamp() * 1000))


def ingest(db: Session, project_id: int, items: list[dict], source: str = "gateway", max_age: timedelta | None = None) -> dict:
    """Hodisalarni partiyalab yozadi. items: [{point, state, ts, source?, quality?, raw?}].
    Qaytaradi: {accepted, duplicates, rejected: [{point, reason}]}."""
    now = datetime.now(timezone.utc)
    rows, rejected = [], []
    seen: set[tuple] = set()
    dup_in_batch = 0
    for it in items:
        point = str(it.get("point") or "").strip()
        if not point:
            rejected.append({"point": None, "reason": "point_missing"})
            continue
        ms = _to_ms(it.get("ts"))
        if ms is None:
            rejected.append({"point": point, "reason": "ts_invalid"})
            continue
        ts = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        if ts > now + timedelta(minutes=5):
            rejected.append({"point": point, "reason": "ts_future"})
            continue
        if max_age is not None and ts < now - max_age:
            rejected.append({"point": point, "reason": "ts_too_old"})
            continue
        state = it.get("state")
        state = ("1" if state else "0") if isinstance(state, bool) else str(state if state is not None else "")
        src = str(it.get("source") or source)[:32]
        key = (src, point[:64], ms, state[:32])
        if key in seen:
            dup_in_batch += 1
            continue
        seen.add(key)
        raw = it.get("raw")
        rows.append(
            {
                "project_id": project_id,
                "source": src,
                "point": point[:64],
                "state": state[:32],
                "ts": ts,
                "ts_ms": ms,
                "quality": str(it.get("quality") or "good")[:16],
                "raw": raw if isinstance(raw, dict | list) else ({"raw": raw} if raw is not None else None),
                "received_at": now,
            }
        )
    inserted = 0
    if rows:
        if db.bind.dialect.name == "postgresql":
            stmt = postgresql.insert(SequenceEvent).values(rows).on_conflict_do_nothing()
        else:
            stmt = sqlite.insert(SequenceEvent).values(rows).on_conflict_do_nothing()
        # rowcount ON CONFLICT bilan ishonchsiz (PG da -1) — RETURNING bo'yicha sanaymiz
        inserted = len(db.execute(stmt.returning(SequenceEvent.id)).all())
        db.commit()
    return {"accepted": inserted, "duplicates": len(rows) - inserted + dup_in_batch, "rejected": rejected}


def event_out(e: SequenceEvent) -> dict:
    return {
        "id": e.id,
        "source": e.source,
        "point": e.point,
        "state": e.state,
        "ts": _aware(e.ts).isoformat(timespec="milliseconds"),
        "ts_ms": e.ts_ms,
        "quality": e.quality,
        "raw": e.raw,
    }


def query(
    db: Session,
    project_id: int,
    since: datetime,
    until: datetime,
    point: str | None = None,
    source: str | None = None,
    limit: int = 500,
    before_id: int | None = None,
) -> list[SequenceEvent]:
    q = db.query(SequenceEvent).filter(
        SequenceEvent.project_id == project_id,
        SequenceEvent.ts_ms >= int(since.timestamp() * 1000),
        SequenceEvent.ts_ms < int(until.timestamp() * 1000),
    )
    if point:
        q = q.filter(SequenceEvent.point.like(point.replace("*", "%")))
    if source:
        q = q.filter(SequenceEvent.source == source)
    if before_id is not None:
        q = q.filter(SequenceEvent.id < before_id)
    return q.order_by(SequenceEvent.ts_ms.desc(), SequenceEvent.id.desc()).limit(limit).all()


def timeline(db: Session, project_id: int, since: datetime, until: datetime, limit: int = 500) -> list[dict]:
    """SOE + alarm jurnali birlashtirilgan ko'rinish (vaqt bo'yicha, eng yangisi birinchi) — F5 uchun."""
    out = [{"type": "soe", **event_out(e)} for e in query(db, project_id, since, until, limit=limit)]
    evs = (
        db.query(AlarmEvent, Sensor)
        .join(Sensor, Sensor.id == AlarmEvent.sensor_id)
        .filter(AlarmEvent.project_id == project_id, AlarmEvent.started_at >= since, AlarmEvent.started_at < until)
        .order_by(AlarmEvent.started_at.desc())
        .limit(limit)
        .all()
    )
    for ev, s in evs:
        st = _aware(ev.started_at)
        out.append(
            {
                "type": "alarm",
                "id": ev.id,
                "source": "alarm",
                "point": s.key,
                "state": STATE_LABEL.get(ev.state.value, ev.state.value),
                "ts": st.isoformat(timespec="milliseconds"),
                "ts_ms": int(st.timestamp() * 1000),
                "quality": ev.suppressed or "good",
                "raw": {"value": ev.value, "priority": s.priority, "ended_at": _aware(ev.ended_at).isoformat() if ev.ended_at else None},
            }
        )
    out.sort(key=lambda r: (r["ts_ms"], r["id"]), reverse=True)
    return out[:limit]


def purge(db: Session, retention_days: int, now: datetime | None = None, batch: int = 20000) -> int:
    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff_ms = int((now - timedelta(days=retention_days)).timestamp() * 1000)
    total = 0
    while True:
        ids = [i for (i,) in db.query(SequenceEvent.id).filter(SequenceEvent.ts_ms < cutoff_ms).limit(batch).all()]
        if not ids:
            break
        for i in range(0, len(ids), 900):
            db.query(SequenceEvent).filter(SequenceEvent.id.in_(ids[i : i + 900])).delete(synchronize_session=False)
        db.commit()
        total += len(ids)
        if len(ids) < batch:
            break
    return total
