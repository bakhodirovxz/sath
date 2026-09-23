"""SCADA-02: gateway Commander — faqat writable teglar, cmd_min/cmd_max va chekli qiymat."""

import importlib.util
import sys
from pathlib import Path

import pytest

_GW = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "ges_gateway.py"


@pytest.fixture(scope="module")
def gw():
    spec = importlib.util.spec_from_file_location("ges_gateway_cmd", _GW)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ges_gateway_cmd"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Writer:
    def __init__(self):
        self.writes = []

    def write(self, tag, value):
        self.writes.append((tag["key"], value))


def _commander(gw, src):
    scfg = {
        "tags": [
            {"key": "RES.H"},  # faqat o'qish
            {"key": "GATE1.SP", "writable": True, "cmd_min": 0, "cmd_max": 100},
            {"key": "GATE2.SP", "writable": True},  # chegarasiz — yozilmaydi
            {"key": "GATE3.SP", "writable": "true", "cmd_min": 0, "cmd_max": 1},  # faqat haqiqiy true
        ],
        "commands": [{"key": "AGG1.SP", "ioa": 41, "cmd_min": 0, "cmd_max": 40}],
    }
    cfg = {"server": "http://s", "project_id": 1, "command_key": "ck"}
    return gw.Commander(cfg, [src], [scfg])


def test_only_writable_tags_mapped(gw):
    cmd = _commander(gw, _Writer())
    assert set(cmd.tags) == {"GATE1.SP", "GATE2.SP", "AGG1.SP"}


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("RES.H", 1.0, "writable"),
        ("GATE3.SP", 0.5, "writable"),
        ("NOPE", 1.0, "writable"),
        ("GATE1.SP", 150.0, "diapazon"),
        ("GATE1.SP", -1.0, "diapazon"),
        ("GATE1.SP", float("nan"), "chekli"),
        ("GATE1.SP", float("inf"), "chekli"),
        ("GATE1.SP", "abc", "son emas"),
        ("GATE2.SP", 10.0, "cmd_min"),
        ("AGG1.SP", 41.0, "diapazon"),
    ],
)
def test_write_rejected(gw, key, value, reason):
    cmd = _commander(gw, _Writer())
    with pytest.raises(RuntimeError, match=reason):
        cmd.check_write(key, value)


def test_run_once_rejects_read_only_and_writes_valid(gw, monkeypatch):
    src = _Writer()
    cmd = _commander(gw, src)
    acks = {}

    class _Resp:
        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    def post(url, json=None, headers=None, timeout=None):
        if url.endswith("/claim"):
            return _Resp([
                {"id": 1, "key": "RES.H", "value": 5.0},
                {"id": 2, "key": "GATE1.SP", "value": 55.0},
                {"id": 3, "key": "GATE1.SP", "value": 500.0},
            ])
        if "/ack" in url:
            acks[int(url.split("/")[-2])] = json
        return _Resp({})

    monkeypatch.setattr(gw.requests, "post", post)
    monkeypatch.setattr(cmd, "_readback", lambda c, st: None)
    cmd.run_once()
    assert src.writes == [("GATE1.SP", 55.0)]
    assert acks[1]["status"] == "failed" and "writable" in acks[1]["result"]
    assert acks[2]["status"] == "acked"
    assert acks[3]["status"] == "failed" and "diapazon" in acks[3]["result"]
