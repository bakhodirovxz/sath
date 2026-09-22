"""L4: WebSocket ko'p jarayonga tayyorlik — har klientga chegaralangan navbat (sekin klient boshqalarni
to'xtatmaydi), diagnostika, foydalanuvchi bo'yicha ulanish chegarasi, bo'sh turish, backplane (ikki replika)."""

import asyncio
import os

import pytest
from conftest import ws_ticket
from ges_server.config import get_settings
from ges_server.monitoring import backplane, live


class FakeWS:
    """Soxta WebSocket: `slow=True` — send hech qachon tugamaydi (qotgan HMI)."""

    def __init__(self, slow: bool = False):
        self.sent: list[dict] = []
        self.slow = slow
        self.closed_code: int | None = None

    async def accept(self):
        pass

    async def send_json(self, m):
        if self.slow:
            await asyncio.sleep(3600)
        self.sent.append(m)

    async def close(self, code=1000):
        self.closed_code = code


def test_slow_client_does_not_block_others_and_is_diagnosed():
    async def run():
        hub = live.Hub()
        fast, slow = FakeWS(), FakeWS(slow=True)
        cf = await hub.connect(1, fast, user_id=1)
        cs = await hub.connect(1, slow, user_id=2)
        # 100 ta xabar, yuboruvchiga navbat beriladi, keyin yana 150 (jami 250 > navbat 200)
        for i in range(100):
            hub.deliver(1, {"type": "reading", "i": i})
        await asyncio.sleep(0.05)
        for i in range(100, 250):
            hub.deliver(1, {"type": "reading", "i": i})
        await asyncio.sleep(0.05)
        assert len(fast.sent) == 250  # tez klient hammasini oldi
        # sekin klient: 1-xabar send da qotgan, 99 + 150 = 249 → 49 ta eng eskisi tashlandi, navbat to'la
        assert cs.dropped == 49 and cs.queue.qsize() == live.WS_QUEUE_MAX
        assert cs.queue._queue[0]["i"] == 50  # noqa: SLF001 — eng eskilari (1..49) tashlangan
        d = {x["user_id"]: x for x in hub.diagnostics(1)}
        assert d[2]["slow"] is True and d[2]["dropped"] == 49 and d[1]["slow"] is False and d[1]["sent"] == 250
        # sync publish loop threadidan tashqari chaqiriladi
        hub.loop = asyncio.get_running_loop()
        await asyncio.to_thread(hub.publish, 1, {"type": "reading", "i": -1})
        await asyncio.sleep(0.05)
        assert fast.sent[-1]["i"] == -1
        hub.disconnect(1, cf)
        hub.disconnect(1, cs)
        await asyncio.sleep(0)
        assert hub.count(1) == 0 and hub.user_connections(1) == 0

    asyncio.run(run())


def test_send_timeout_closes_client(monkeypatch):
    monkeypatch.setattr(live, "WS_SEND_TIMEOUT_S", 0.05)

    async def run():
        hub = live.Hub()
        slow = FakeWS(slow=True)
        c = await hub.connect(1, slow, user_id=3)
        hub.deliver(1, {"type": "ping"})
        await asyncio.sleep(0.2)
        assert c.closed and slow.closed_code == 1011

    asyncio.run(run())


def test_memory_backplane_two_replicas():
    """Ikki replika (ikki Hub) bitta backplane bilan: A dagi publish B ning klientiga yetadi, o'ziga takrorlanmaydi."""

    async def run():
        a, b = live.Hub(), live.Hub()
        a.loop = b.loop = asyncio.get_running_loop()
        a.backplane, b.backplane = backplane.MemoryBackplane("t", node_id="A"), backplane.MemoryBackplane("t", node_id="B")
        await a.backplane.start(a.deliver)
        await b.backplane.start(b.deliver)
        wa, wb = FakeWS(), FakeWS()
        await a.connect(7, wa, 1)
        await b.connect(7, wb, 2)
        a.publish(7, {"type": "reading", "v": 1})
        await asyncio.sleep(0.05)
        assert wa.sent == [{"type": "reading", "v": 1}] and wb.sent == [{"type": "reading", "v": 1}]
        # boshqa loyiha — yetmaydi
        b.publish(8, {"type": "reading", "v": 2})
        await asyncio.sleep(0.05)
        assert len(wa.sent) == 1 and len(wb.sent) == 1
        await a.backplane.stop()
        await b.backplane.stop()

    asyncio.run(run())


def test_backplane_from_settings_sqlite_off_pg_on(monkeypatch):
    s = get_settings()
    old = s.database_url, s.live_backplane
    try:
        s.database_url, s.live_backplane = "sqlite:///x.db", "auto"
        assert backplane.from_settings() is None
        s.database_url = "postgresql+psycopg://u:p@h:5433/d"
        bp = backplane.from_settings()
        assert isinstance(bp, backplane.PgBackplane) and "dbname=d" in bp.conninfo and "port=5433" in bp.conninfo
        s.live_backplane = "off"
        assert backplane.from_settings() is None
    finally:
        s.database_url, s.live_backplane = old


def test_pg_backplane_payload_limit():
    bp = backplane.PgBackplane("host=x")
    bp.publish(1, {"type": "workorder", "text": "x" * 9000})
    assert bp.dropped_large == 1 and bp._out == []
    bp.publish(1, {"type": "reading"})
    assert len(bp._out) == 1


@pytest.mark.skipif(not os.environ.get("GES_TEST_DATABASE_URL", "").startswith("postgresql"), reason="Postgres kerak (D1 CI ishi)")
def test_pg_backplane_roundtrip():
    """Haqiqiy Postgres LISTEN/NOTIFY: A tugunidan B tuguniga."""

    async def run():
        a, b = backplane.from_settings(), backplane.from_settings()
        assert a is not None and b is not None
        a.node_id, b.node_id = "A", "B"
        got: list[tuple[int, dict]] = []
        await b.start(lambda pid, m: got.append((pid, m)))
        await a.start(lambda pid, m: None)
        assert await asyncio.to_thread(b.listening.wait, 10)  # LISTEN o'rnatilsin
        a.publish(5, {"type": "reading", "v": 42})
        for _ in range(50):
            await asyncio.sleep(0.1)
            if got:
                break
        assert got == [(5, {"type": "reading", "v": 42})]
        await a.stop()
        await b.stop()

    asyncio.run(run())


def test_ws_per_user_limit_and_idle_close(client, users, monkeypatch):
    pid = users["project_id"]
    s = get_settings()
    monkeypatch.setattr(s, "ws_max_per_user", 1)
    t1 = ws_ticket(client, users["viewer"])
    t2 = ws_ticket(client, users["viewer"])
    with client.websocket_connect(f"/api/projects/{pid}/live?ticket={t1}") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        with pytest.raises(Exception):  # noqa: B017 — 4429 bilan yopiladi
            with client.websocket_connect(f"/api/projects/{pid}/live?ticket={t2}") as ws2:
                ws2.receive_json()
        # diagnostika
        r = client.get(f"/api/projects/{pid}/live/clients", headers=users["engineer"])
        assert r.status_code == 200 and len(r.json()["clients"]) == 1 and r.json()["clients"][0]["user_id"] == users["ids"]["viewer"]
    # bo'sh turish: ws_idle_s=0 → birinchi ping muddatida yopiladi (4408)
    monkeypatch.setattr(s, "ws_idle_s", 0)
    from ges_server.monitoring import router as mon_router

    monkeypatch.setattr(mon_router, "WS_PING_S", 0.05)
    t3 = ws_ticket(client, users["viewer"])
    with pytest.raises(Exception):  # noqa: B017
        with client.websocket_connect(f"/api/projects/{pid}/live?ticket={t3}") as ws:
            ws.receive_json()
            for _ in range(5):
                ws.receive_json()
