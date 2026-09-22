"""Fon vazifalar (server ichida, alohida servis kerak emas):
* har monitor_interval_s — barcha loyihalarda 'stale' sensorlar (aloqa uzilgan) tekshiriladi;
* har soat — xom o'lchovlar soatlik agregatga yig'iladi, retention dan eskilari o'chiriladi.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..db import SessionLocal
from ..orm import Project, SystemState
from . import control, health, historian, keys, live, twin

log = logging.getLogger("ges_server.monitoring.bg")


def tick_stale() -> int:
    with SessionLocal() as db:
        n = 0
        for (pid,) in db.query(Project.id).all():
            n += len(live.mark_stale(db, pid))
            n += len(live.settle_pending(db, pid))  # kechikishi o'tgan alarmlar (C1)
            n += len(live.unshelve_expired(db, pid))  # shelving muddati (C2)
        return n


def tick_commands() -> int:
    """Buyruq TTL va watchdog (B1)."""
    with SessionLocal() as db:
        return control.tick(db)


def tick_keys() -> int:
    """Gateway kalitlari muddati yaqinlashganda bildirishnoma (kuniga bir marta, B3)."""
    with SessionLocal() as db:
        return keys.warn_expiring(db)


def send_daily_reports(day_start: datetime) -> int:
    """Kechagi kun hisoboti — loyiha a'zolariga (muhandis/tasdiqlovchi/operator) email."""
    from .. import notify
    from ..orm import ProjectMember, Role

    sent = 0
    with SessionLocal() as db:
        for p in db.query(Project).all():
            emails = sorted(
                {
                    m.user.email
                    for m in db.query(ProjectMember).filter_by(project_id=p.id).all()
                    if m.user.email and m.user.is_active and m.role != Role.viewer
                }
            )
            rep = historian.build_report(db, p, "day", day_start - timedelta(days=1))
            if not emails or not any(r["n"] for r in rep["sensors"]):
                continue
            notify.send_async(emails, f"Kunlik hisobot — {p.name}", historian.report_text(rep), group=f"report:{p.id}")
            sent += 1
    return sent


def tick_hourly() -> tuple[int, int]:
    settings = get_settings()
    with SessionLocal() as db:
        written = historian.rollup(db)
        purged = historian.purge(db, settings.readings_retention_days)
        purged += historian.purge_agg(db, "1m", settings.agg_1m_retention_days)
        purged += historian.purge_agg(db, "10m", settings.agg_10m_retention_days)
        twin.rollup_units(db)  # agregat kunlik statistikasi (tugagan kunlar)
        health.tick_hourly(db)  # sog'liq indekslari (HEALTH.*)
    return written, purged


def state_get(key: str) -> str | None:
    with SessionLocal() as db:
        row = db.get(SystemState, key)
        return row.value if row else None


def state_set(key: str, value: str) -> None:
    with SessionLocal() as db:
        row = db.get(SystemState, key)
        if row is None:
            db.add(SystemState(key=key, value=value))
        else:
            row.value = value
        db.commit()


LAST_HOUR_KEY = "bg.last_hour"


def load_last_hour() -> datetime | None:
    """Oxirgi bajarilgan soat DB dan (restartdan keyin kunlik hisobot/kalit tekshiruvi takrorlanmasin)."""
    v = state_get(LAST_HOUR_KEY)
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


async def loop(stop: asyncio.Event) -> None:
    interval = max(5, get_settings().monitor_interval_s)
    last_hour = await asyncio.to_thread(load_last_hour)
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick_stale)
            await asyncio.to_thread(tick_commands)
            await asyncio.to_thread(twin.tick_all)  # raqamli egizak: kutilgan quvvat/og'ish
            hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            if hour != last_hour:
                written, purged = await asyncio.to_thread(tick_hourly)
                if written or purged:
                    log.info("historian: %d soatlik agregat, %d xom o'chirildi", written, purged)
                if last_hour is None or last_hour.date() != hour.date():
                    n_keys = await asyncio.to_thread(tick_keys)
                    if n_keys:
                        log.info("gateway kalitlari: %d muddat bildirishnomasi", n_keys)
                rh = get_settings().daily_report_hour
                if (
                    rh >= 0
                    and hour.hour == rh
                    and (last_hour is None or last_hour.date() != hour.date())
                ):
                    n = await asyncio.to_thread(send_daily_reports, hour.replace(hour=0))
                    log.info("kunlik hisobot: %d loyiha", n)
                last_hour = hour
                await asyncio.to_thread(state_set, LAST_HOUR_KEY, hour.isoformat())
        except Exception:  # noqa: BLE001 — fon sikl to'xtamasin
            log.exception("monitoring fon vazifasi xatosi")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except (TimeoutError, asyncio.TimeoutError):  # 3.10 da alohida sinf
            pass
