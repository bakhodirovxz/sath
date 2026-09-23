"""E1/E2: gateway spool (diskda, restartda saqlanadi, backoff, to'lish siyosati), sifat/manba vaqti."""

import importlib.util
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path


class _Resp:
    def __init__(self, status=200, body=None, date=None):
        self.status_code = status
        self._body = body or {"accepted": 0, "unknown": [], "rejected": [], "bad": 0}
        self.headers = {"Date": date} if date else {}
        self.text = "x"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _req.RequestException(f"HTTP {self.status_code}")

    def json(self):
        return self._body


_req = types.ModuleType("requests")


class _RequestException(Exception):
    pass


_req.RequestException = _RequestException
_calls: list[list[dict]] = []
_urls: list[str] = []
_mode = {"fail": False, "status": 200, "date": None}


def _post(url, json=None, headers=None, timeout=None):
    if _mode["fail"]:
        raise _RequestException("tarmoq yo'q")
    _calls.append(list(json))
    _urls.append(url)
    return _Resp(_mode["status"], {"accepted": len(json), "unknown": [], "rejected": [], "bad": 0}, _mode["date"])


_req.post = _post
_req.get = _post


def _load_gateway():
    sys.modules["requests"] = _req
    path = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "ges_gateway.py"
    spec = importlib.util.spec_from_file_location("ges_gateway_spool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cfg(tmp_path, **kw):
    return {"server": "http://s", "project_id": 1, "ingest_key": "k", "spool_path": str(tmp_path / "spool.db"), **kw}


def test_spool_survives_restart_and_sends_after_reconnect(tmp_path):
    gw = _load_gateway()
    _calls.clear()
    _mode.update(fail=True)
    p = gw.Pusher(_cfg(tmp_path))
    p.push([{"key": "A", "value": 1}, {"key": "B", "value": 2}])
    assert p.spool.size() == 2 and p.backoff_s == 2.0 and _calls == []
    p.spool.close()
    # "restart": yangi Pusher o'sha fayl bilan — yozuvlar joyida
    p2 = gw.Pusher(_cfg(tmp_path))
    assert p2.spool.size() == 2 and p2.spool.oldest_age_s() >= 0
    _mode.update(fail=False)
    p2.flush()
    assert p2.spool.size() == 0 and len(_calls) == 1 and [i["key"] for i in _calls[0]] == ["A", "B"]
    assert all("src_ts" in i and "ts" in i for i in _calls[0])
    p2.spool.close()


def test_backoff_grows_and_resets(tmp_path):
    gw = _load_gateway()
    _calls.clear()
    _mode.update(fail=True)
    p = gw.Pusher(_cfg(tmp_path))
    p.push([{"key": "A", "value": 1}])
    assert p.backoff_s == 2.0
    p.next_try = 0  # kutishni o'tkazib yuboramiz
    p.flush()
    assert p.backoff_s == 4.0 and p.next_try > time.time()
    p.flush()  # hali kutish vaqti — urinmaydi
    assert p.backoff_s == 4.0
    _mode.update(fail=False)
    p.next_try = 0
    p.flush()
    assert p.backoff_s == 0.0 and p.spool.size() == 0
    p.spool.close()


def test_overflow_policies(tmp_path):
    gw = _load_gateway()
    _mode.update(fail=True)
    p = gw.Pusher(_cfg(tmp_path, spool_max_rows=3, spool_overflow="drop_oldest"))
    p.push([{"key": f"K{i}", "value": i} for i in range(5)])
    assert p.spool.size() == 3 and p.spool.dropped == 2
    _, batch = p.spool.batch()
    assert [b["key"] for b in batch] == ["K2", "K3", "K4"]
    p.spool.close()
    p2 = gw.Pusher(_cfg(tmp_path, spool_path=str(tmp_path / "s2.db"), spool_max_rows=3, spool_overflow="stop"))
    p2.push([{"key": f"K{i}", "value": i} for i in range(3)])
    added = p2.spool.add([{"key": "X", "value": 9}])
    assert added == 0 and p2.spool.size() == 3
    p2.spool.close()


def test_422_batch_is_dropped_not_retried_forever(tmp_path):
    gw = _load_gateway()
    _calls.clear()
    _mode.update(fail=False, status=422)
    p = gw.Pusher(_cfg(tmp_path))
    p.push([{"key": "A", "value": 1}])
    assert p.spool.size() == 0
    _mode.update(status=200)
    p.spool.close()


def test_diag_tags_and_clock_offset(tmp_path):
    gw = _load_gateway()
    _calls.clear()
    _mode.update(fail=False, status=200, date=(datetime.now(timezone.utc)).strftime("%a, %d %b %Y %H:%M:%S GMT"))
    p = gw.Pusher(_cfg(tmp_path, diag=True))
    p.push([{"key": "A", "value": 1}])
    keys = [i["key"] for i in _calls[-1]]
    assert "GW.spool_rows" in keys and "GW.spool_oldest_age_s" in keys
    assert p.clock_offset_s is not None and abs(p.clock_offset_s) < 5
    p.push([{"key": "A", "value": 2}])
    assert any(i["key"] == "GW.clock_offset_s" for i in _calls[-1])
    _mode.update(date=None)
    p.spool.close()


def test_sanitize_non_finite_and_quality_mapping(tmp_path):
    gw = _load_gateway()
    items = gw.Pusher.sanitize([{"key": "A", "value": float("nan")}, {"key": "B", "value": "x"}, {"key": "C", "value": 1.5}])
    assert items[0]["quality"] == "bad" and items[0]["value"] == 0.0
    assert items[1]["quality"] == "bad" and items[2].get("quality") is None

    class SC:
        def __init__(self, v):
            self.value = v

    assert gw.opcua_quality(SC(0)) == "good"
    assert gw.opcua_quality(SC(0x40000000)) == "uncertain"
    assert gw.opcua_quality(SC(0x80000000)) == "bad"

    class DV:
        def __init__(self, v, sc, ts):
            self.Value = types.SimpleNamespace(Value=v)
            self.StatusCode = SC(sc)
            self.SourceTimestamp = ts
            self.ServerTimestamp = None

    it = gw.opcua_item("T", DV(12.5, 0x40000000, datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert it == {"key": "T", "value": 12.5, "quality": "uncertain", "src_ts": "2026-01-01T00:00:00+00:00"}
    bad = gw.opcua_item("T", DV(12.5, 0x80000000, None))
    assert bad["quality"] == "bad" and bad["value"] == 0.0


def test_comms_loss_emits_single_bad_record_per_tag(tmp_path):
    gw = _load_gateway()

    class Flaky(gw.Source):
        def __init__(self):
            super().__init__()
            self.ok = False

        def tag_keys(self):
            return ["A", "B"]

        def read(self):
            if not self.ok:
                raise ConnectionError("yo'q")
            return [{"key": "A", "value": 1, "quality": "good"}, {"key": "B", "value": 2, "quality": "good"}]

    s = Flaky()
    first = s.read_safe()
    assert [(i["key"], i["quality"]) for i in first] == [("A", "bad"), ("B", "bad")]
    assert s.read_safe() == []  # takrorlanmaydi
    s.ok = True
    assert [i["quality"] for i in s.read_safe()] == ["good", "good"]
    s.ok = False
    assert len(s.read_safe()) == 2  # qayta uzilish → yana bir marta


def test_soe_goes_through_spool_to_soe_endpoint(tmp_path):
    """D3: SOE hodisalari ham spool orqali (uzilishda yo'qolmaydi), alohida /soe manzilga; o'lchovlar /readings ga."""
    gw = _load_gateway()
    _calls.clear()
    _urls.clear()
    _mode.update(fail=True)
    p = gw.Pusher(_cfg(tmp_path))
    p.push([{"key": "A", "value": 1}], soe=[{"point": "AGG1.PROT", "state": "TRIP", "ts": "2026-09-21T10:00:00.012+00:00", "source": "iec104"}])
    assert p.spool.size() == 2 and _calls == []
    _mode.update(fail=False)
    p.next_try = 0
    p.flush()
    assert p.spool.size() == 0 and len(_calls) == 2
    by_url = {u.rsplit("/", 1)[1]: c for u, c in zip(_urls, _calls, strict=True)}
    assert by_url["soe"] == [{"point": "AGG1.PROT", "state": "TRIP", "ts": "2026-09-21T10:00:00.012+00:00", "source": "iec104"}]
    assert [i["key"] for i in by_url["readings"]] == ["A"]
    p.spool.close()


def _scripted(handler):
    """_post o'rniga: handler(url, items) → (status, body)."""
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append((url, list(json)))
        st, body = handler(url, list(json))
        if st == -1:
            raise _RequestException("tarmoq yo'q")
        return _Resp(st, body)

    return post, sent


def test_4xx_splits_or_drops_batch_instead_of_retrying_forever(tmp_path, monkeypatch):
    """SCADA-05: 413 → bo'lib yuboriladi; 422 → yaroqsiz yozuv ajratilib tashlanadi, qolgani yetib boradi;
    400/404 → partiya log bilan tashlanadi; spool tiqilib qolmaydi."""
    gw = _load_gateway()
    _mode.update(fail=False, status=200)

    def handler(url, items):
        if len(items) > 4:
            return 413, {"detail": "katta"}
        if any(i["key"] == "BAD" for i in items):
            return 422, {"detail": "yaroqsiz"}
        return 200, {"accepted": len(items), "unknown": [], "rejected": [], "bad": 0}

    post, sent = _scripted(handler)
    monkeypatch.setattr(gw.requests, "post", post)
    p = gw.Pusher(_cfg(tmp_path, batch_size=10))
    items = [{"key": f"K{i}", "value": i} for i in range(9)]
    items.insert(5, {"key": "BAD", "value": 1})
    p.push(items)
    delivered = [i["key"] for url, b in sent for i in b if handler(url, b)[0] == 200]
    assert sorted(delivered) == sorted(f"K{i}" for i in range(9))  # hammasi yetib bordi
    assert p.spool.size() == 0 and p.dropped_4xx == 1 and p.backoff_s == 0.0
    p.spool.close()
    # 400 (partiya tarkibiga bog'liq emas) — bo'linmaydi, bir marta tashlanadi
    post, sent = _scripted(lambda url, items: (400, {"detail": "x"}))
    monkeypatch.setattr(gw.requests, "post", post)
    p = gw.Pusher(_cfg(tmp_path, spool_path=str(tmp_path / "s400.db")))
    p.push([{"key": f"K{i}", "value": i} for i in range(6)])
    assert len(sent) == 1 and p.spool.size() == 0 and p.dropped_4xx == 6
    p.spool.close()


def test_retryable_statuses_keep_spool(tmp_path, monkeypatch):
    """5xx, 401/403/429, tarmoq xatosi — spool saqlanadi, backoff; keyin hammasi yetib boradi."""
    gw = _load_gateway()
    for st in (500, 503, 401, 403, 429, -1):
        post, sent = _scripted(lambda url, items, st=st: (st, {"detail": "x"}))
        monkeypatch.setattr(gw.requests, "post", post)
        p = gw.Pusher(_cfg(tmp_path, spool_path=str(tmp_path / f"r{st}.db")))
        p.push([{"key": "A", "value": 1}, {"key": "B", "value": 2}])
        assert p.spool.size() == 2 and p.backoff_s == 2.0 and p.dropped_4xx == 0, st
        post, sent = _scripted(lambda url, items: (200, {"accepted": len(items)}))
        monkeypatch.setattr(gw.requests, "post", post)
        p.next_try = 0
        p.flush()
        assert p.spool.size() == 0, st
        p.spool.close()


def test_partial_success_not_resent_after_retryable_error(tmp_path, monkeypatch):
    """Bo'lingan partiyaning yuborilgan yarmi spooldan o'chadi — keyingi urinishda takrorlanmaydi."""
    gw = _load_gateway()
    state = {"n": 0}

    def handler(url, items):
        if len(items) > 2:
            return 413, {}
        state["n"] += 1
        return (200, {"accepted": len(items)}) if state["n"] == 1 else (503, {})

    post, sent = _scripted(handler)
    monkeypatch.setattr(gw.requests, "post", post)
    p = gw.Pusher(_cfg(tmp_path))
    p.push([{"key": f"K{i}", "value": i} for i in range(4)])
    assert p.spool.size() == 2  # birinchi yarmi yetib bordi, ikkinchisi spoolda
    post, sent = _scripted(lambda url, items: (200, {"accepted": len(items)}))
    monkeypatch.setattr(gw.requests, "post", post)
    p.next_try = 0
    p.flush()
    assert [i["key"] for _, b in sent for i in b] == ["K2", "K3"] and p.spool.size() == 0
    p.spool.close()


def test_30000_row_backlog_fully_delivered(tmp_path, monkeypatch):
    """SCADA-05 qabul: 30 000 yozuvli spool — server 10 000 dan kattasini 413 qilsa ham hammasi yetib boradi."""
    gw = _load_gateway()
    got = []

    def handler(url, items):
        if len(items) > 10000:
            return 413, {}
        got.extend(items)
        return 200, {"accepted": len(items)}

    post, _ = _scripted(handler)
    monkeypatch.setattr(gw.requests, "post", post)
    _mode.update(fail=True)
    p = gw.Pusher(_cfg(tmp_path, batch_size=20000, max_batches_per_cycle=5))
    monkeypatch.setattr(gw.requests, "post", lambda *a, **k: (_ for _ in ()).throw(_RequestException("yo'q")))
    p.push([{"key": f"K{i}", "value": i} for i in range(30000)])
    assert p.spool.size() == 30000
    monkeypatch.setattr(gw.requests, "post", post)
    p.next_try = 0
    p.flush()
    assert p.spool.size() == 0 and len(got) == 30000
    p.spool.close()
