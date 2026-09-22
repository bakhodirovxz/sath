"""Jonli oqim backplane (L4): ko'p jarayon/replikada `hub.publish` xabarlari boshqa replikalarga ham
yetib borsin. Postgres `LISTEN/NOTIFY` (`sath_live` kanali; Redis siz — D1 dagi DB ning o'zi), SQLite da
o'chiq (bitta jarayon). Testlar uchun `MemoryBackplane` (bir jarayondagi bir necha Hub).

Chiqish: `publish()` sync koddan chaqiriladi, xabarlar chiqish navbatiga yig'ilib yuboruvchi threadda ~100 ms
da bitta `pg_notify` partiyasi bilan yuboriladi. Kirish: alohida ulanish (thread) `LISTEN` qiladi, o'z
tuguni (`NODE_ID`) xabarlarini tashlaydi, qolganini loop orqali mahalliy Hub ga beradi. NOTIFY payload chegarasi
8000 bayt — katta xabar (kamdan-kam: ish buyrug'i matni) faqat mahalliy yetkaziladi (ogohlantirish).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
from collections.abc import Callable

log = logging.getLogger("ges_server.backplane")

NODE_ID = f"{socket.gethostname()}:{os.getpid()}"
CHANNEL = "sath_live"
MAX_PAYLOAD = 7900
FLUSH_MS = 100

Deliver = Callable[[int, dict], None]  # (project_id, message) → mahalliy hub ga


class Backplane:
    """Umumiy interfeys: `publish` (sync, bloklamaydi), `start/stop` (async)."""

    node_id = NODE_ID

    def publish(self, project_id: int, message: dict) -> None:  # pragma: no cover - interfeys
        raise NotImplementedError

    async def start(self, deliver: Deliver) -> None:  # pragma: no cover
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover
        raise NotImplementedError


class MemoryBackplane(Backplane):
    """Bir jarayonda bir necha Hub (testlar, ikki replika simulyatsiyasi): bus ro'yxatidagi hamma
    obunachiga o'z tugunidan tashqari yetkazadi."""

    _buses: dict[str, list[MemoryBackplane]] = {}

    def __init__(self, bus: str = "default", node_id: str | None = None):
        self.bus = bus
        self.node_id = node_id or NODE_ID
        self._deliver: Deliver | None = None
        self.sent = 0

    def publish(self, project_id: int, message: dict) -> None:
        self.sent += 1
        for peer in self._buses.get(self.bus, []):
            if peer is not self and peer._deliver is not None:
                peer._deliver(project_id, message)

    async def start(self, deliver: Deliver) -> None:
        self._deliver = deliver
        self._buses.setdefault(self.bus, []).append(self)

    async def stop(self) -> None:
        self._deliver = None
        if self in self._buses.get(self.bus, []):
            self._buses[self.bus].remove(self)


class PgBackplane(Backplane):
    """Postgres LISTEN/NOTIFY. `conninfo` — psycopg (libpq) ulanish satri. Sinxron psycopg ulanishlari
    alohida threadlarda (Windows Proactor loop va psycopg async mos emas; Linux da ham loopdan mustaqil):
    yuboruvchi thread partiyalab `pg_notify`, tinglovchi thread `notifies()` → loop ga `call_soon_threadsafe`."""

    def __init__(self, conninfo: str):
        self.conninfo = conninfo
        self._out: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self.dropped_large = 0
        self.sent = 0
        self.received = 0
        self.listening = threading.Event()

    def publish(self, project_id: int, message: dict) -> None:
        payload = json.dumps({"n": self.node_id, "p": project_id, "m": message}, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > MAX_PAYLOAD:
            self.dropped_large += 1
            log.warning("backplane: xabar juda katta (%d bayt, %s) — faqat mahalliy yetkazildi", len(payload), message.get("type"))
            return
        with self._lock:
            self._out.append(payload)

    async def start(self, deliver: Deliver) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = threading.Event()
        self._threads = [
            threading.Thread(target=self._sender, name="backplane-tx", daemon=True),
            threading.Thread(target=self._listener, args=(deliver,), name="backplane-rx", daemon=True),
        ]
        for t in self._threads:
            t.start()

    async def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            await asyncio.to_thread(t.join, 3.0)
        self._threads = []

    def _connect(self):
        import psycopg

        return psycopg.connect(self.conninfo, autocommit=True)

    def _sender(self) -> None:
        conn = None
        while not self._stop.wait(FLUSH_MS / 1000):
            with self._lock:
                batch, self._out = self._out, []
            if not batch:
                continue
            try:
                if conn is None or conn.closed:
                    conn = self._connect()
                conn.execute("SELECT pg_notify(%s, unnest(%s::text[]))", (CHANNEL, batch))
                self.sent += len(batch)
            except Exception:  # noqa: BLE001 — ulanish uzilsa keyingi partiyada qayta ulanadi; xabarlar yo'qoladi (jonli oqim, tarix DB da)
                log.exception("backplane: %d xabar yuborilmadi", len(batch))
                conn = None
        if conn is not None:
            conn.close()

    def _listener(self, deliver: Deliver) -> None:
        while not self._stop.is_set():
            conn = None
            try:
                conn = self._connect()
                conn.execute(f"LISTEN {CHANNEL}")
                self.listening.set()
                log.info("backplane: LISTEN %s (%s)", CHANNEL, self.node_id)
                gen = conn.notifies(timeout=1.0)
                while not self._stop.is_set():
                    for n in gen:  # timeout da generator tugaydi — to'xtash bayrog'i tekshiriladi
                        try:
                            d = json.loads(n.payload)
                        except ValueError:
                            continue
                        if d.get("n") == self.node_id:
                            continue
                        self.received += 1
                        if self._loop is not None:
                            self._loop.call_soon_threadsafe(deliver, int(d["p"]), d["m"])
                    gen = conn.notifies(timeout=1.0)
            except Exception:  # noqa: BLE001 — ulanish uzildi: qayta ulanamiz
                self.listening.clear()
                if self._stop.is_set():
                    break
                log.exception("backplane: LISTEN uzildi, 2 s dan keyin qayta")
                self._stop.wait(2)
            finally:
                if conn is not None:
                    conn.close()


def from_settings() -> Backplane | None:
    """Sozlamadan: `live_backplane` = auto (Postgres bo'lsa pg) | pg | off."""
    from ..config import get_settings

    s = get_settings()
    mode = s.live_backplane
    if mode == "off":
        return None
    if mode == "auto" and not s.database_url.startswith("postgresql"):
        return None
    if mode in ("auto", "pg"):
        from sqlalchemy.engine import make_url

        u = make_url(s.database_url)
        conninfo = " ".join(
            f"{k}={v}"
            for k, v in (
                ("host", u.host),
                ("port", u.port),
                ("dbname", u.database),
                ("user", u.username),
                ("password", u.password),
            )
            if v
        )
        return PgBackplane(conninfo)
    raise ValueError(f"live_backplane: {mode}")
