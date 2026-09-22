"""Yuqori ishonchlilik (L8): rol (api | worker | all), fon vazifalari uchun yetakchi qulfi, tayyorlik holati.

- `GES_ROLE=api` — faqat HTTP/WS (ko'p replika, load balancer ortida); `worker` — faqat fon sikli + ish navbati
  + MQTT ko'prigi (bitta nusxa); `all` (default) — ikkalasi bitta jarayonda (kichik deploy).
- Yetakchi qulfi: `all`/`worker` rejimida bir necha nusxa ishga tushsa ham davriy fon siklini faqat qulfni
  olgan nusxa bajaradi — Postgres `pg_try_advisory_lock` (sessiya davomida ushlab turiladi), SQLite da fayl
  qulfi (`data_dir/leader.lock`, bitta host). Qulf yo'qolsa sikl to'xtaydi va qayta olishga urinadi.
- Tayyorlik (`/api/ready`): DB so'rovi, sxema `head` da, backplane (sozlangan bo'lsa) tinglayapti, ish
  navbati ishchisi (worker rolida) tirik → 200; aks holda 503 — load balancer bu replikaga trafik bermaydi.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from .config import get_settings
from .db import engine

log = logging.getLogger("ges_server.ha")

LEADER_KEY = 0x53415448  # 'SATH'


def role() -> str:
    r = get_settings().role
    if r not in ("api", "worker", "all"):
        raise ValueError(f"GES_ROLE: {r} (api | worker | all)")
    return r


def serves_http() -> bool:
    return role() in ("api", "all")


def runs_background() -> bool:
    return role() in ("worker", "all")


class Leader:
    """Fon vazifalari yetakchisi. `acquire()` — qulf olindi (True) yoki boshqa nusxada (False); `held()` —
    hali bizda (Postgres ulanishi tirikligini tekshiradi); `release()`."""

    def __init__(self) -> None:
        self._conn = None  # Postgres: qulfni ushlab turuvchi ulanish
        self._fh = None  # SQLite: fayl qulfi
        self._lock = threading.Lock()
        self.acquired_at: datetime | None = None

    @property
    def is_pg(self) -> bool:
        return engine.dialect.name == "postgresql"

    def acquire(self) -> bool:
        with self._lock:
            if self.acquired_at is not None:
                return True
            try:
                if self.is_pg:
                    conn = engine.raw_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT pg_try_advisory_lock(%s)", (LEADER_KEY,))
                    ok = bool(cur.fetchone()[0])
                    cur.close()
                    if not ok:
                        conn.close()
                        return False
                    self._conn = conn
                else:
                    ok = self._acquire_file()
                    if not ok:
                        return False
            except Exception:  # noqa: BLE001 — DB/fayl xatosi: yetakchi emas (keyingi urinishda qayta)
                log.exception("yetakchi qulfini olishda xato")
                return False
            self.acquired_at = datetime.now(timezone.utc)
            return True

    def _acquire_file(self) -> bool:
        path = Path(get_settings().data_dir) / "leader.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+")  # noqa: SIM115 — qulf davomida ochiq qoladi
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
        fh.flush()
        self._fh = fh
        return True

    def held(self) -> bool:
        with self._lock:
            if self.acquired_at is None:
                return False
            if self._conn is not None:
                try:
                    cur = self._conn.cursor()
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    cur.close()
                    return True
                except Exception:  # noqa: BLE001 — ulanish uzildi: qulf ham ketdi
                    log.warning("yetakchi ulanishi uzildi — qulf yo'qoldi")
                    self._drop()
                    return False
            return self._fh is not None

    def _drop(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None
        if self._fh is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self._fh.close()
            self._fh = None
        self.acquired_at = None

    def release(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    cur = self._conn.cursor()
                    cur.execute("SELECT pg_advisory_unlock(%s)", (LEADER_KEY,))
                    cur.fetchone()
                    cur.close()
                except Exception:  # noqa: BLE001
                    pass
            self._drop()


leader = Leader()


def readiness() -> tuple[bool, dict]:
    """Tayyorlik tekshiruvi: (ok, tafsilot). Yengil — har necha soniyada chaqirilishi mumkin."""
    from . import jobs
    from .db import assert_at_head
    from .monitoring import live

    checks: dict[str, str] = {}
    ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:  # noqa: BLE001 — holat sifatida qaytariladi
        checks["db"] = f"xato: {type(e).__name__}"
        ok = False
    if checks["db"] == "ok":
        try:
            assert_at_head()
            checks["schema"] = "head"
        except Exception as e:  # noqa: BLE001
            checks["schema"] = str(e)[:120]
            ok = False
    bp = live.hub.backplane
    if bp is not None:
        listening = getattr(bp, "listening", None)
        if listening is not None and not listening.is_set():
            checks["backplane"] = "ulanmagan"
            ok = False
        else:
            checks["backplane"] = "ok"
    else:
        checks["backplane"] = "yo'q"
    if runs_background():
        checks["jobs"] = "ok" if jobs.runner is not None else "ishchi yo'q"
        ok = ok and jobs.runner is not None
        checks["leader"] = "ha" if leader.acquired_at is not None else "yo'q (boshqa nusxa)"
    checks["role"] = role()
    return ok, checks
