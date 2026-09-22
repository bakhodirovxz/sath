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
