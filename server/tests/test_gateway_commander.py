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


def _signed(cmds, key="ck", pid=1, exp_in=60):
    """Serverning o'z imzolash funksiyasi bilan (SCADA-04 kross-moslik)."""
    import time
    import types

    from ges_server.monitoring import keys

    proj = types.SimpleNamespace(command_sign_key=keys.derive_sign_key(key))
    out = []
    for i, c in enumerate(cmds):
        base = {"project_id": pid, "protocol": "modbus", "address": {"register": 10}, "nonce": f"n{c['id']}-{i}",
                "expires_at": int(time.time()) + exp_in}
        out.append(keys.sign_command(proj, {**base, **c}))
    return out


def test_run_once_rejects_read_only_and_writes_valid(gw, monkeypatch):
    src = _Writer()
    cmd = _commander(gw, src)
    acks = {}

    class _Resp:
        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    claimed = _signed([
        {"id": 1, "key": "RES.H", "value": 5.0},
        {"id": 2, "key": "GATE1.SP", "value": 55.0},
        {"id": 3, "key": "GATE1.SP", "value": 500.0},
    ])

    def post(url, json=None, headers=None, timeout=None):
        if url.endswith("/claim"):
            return _Resp(claimed)
        if "/ack" in url:
            acks[int(url.split("/")[-2])] = json
        return _Resp({})

    monkeypatch.setattr(gw.requests, "post", post, raising=False)
    monkeypatch.setattr(cmd, "_readback", lambda c, st: None)
    cmd.run_once()
    assert src.writes == [("GATE1.SP", 55.0)]
    assert acks[1]["status"] == "failed" and "writable" in acks[1]["result"]
    assert acks[2]["status"] == "acked"
    assert acks[3]["status"] == "failed" and "diapazon" in acks[3]["result"]


def test_signature_verification(gw):
    """SCADA-04: imzosiz/soxta/eskirgan/takroriy/boshqa loyiha buyrug'i rad etiladi."""
    import time

    v = gw.CommandVerifier("ck", 1, clock_skew_s=5)
    good = _signed([{"id": 7, "key": "GATE1.SP", "value": 40.0}])[0]
    v.verify(good)  # to'g'ri imzo
    with pytest.raises(RuntimeError, match="takror"):
        v.verify(good)  # replay
    fresh = lambda **kw: _signed([{"id": 8, "key": "GATE1.SP", "value": 40.0, **kw}])[0]  # noqa: E731
    tampered = {**fresh(nonce="t1"), "value": 90.0}
    with pytest.raises(RuntimeError, match="imzosi noto'g'ri"):
        v.verify(tampered)
    moved = {**fresh(nonce="t2"), "address": {"register": 11}}
    with pytest.raises(RuntimeError, match="imzosi noto'g'ri"):
        v.verify(moved)
    unsigned = {k: x for k, x in fresh(nonce="t3").items() if k not in ("sig", "alg")}
    with pytest.raises(RuntimeError, match="imzosiz"):
        v.verify(unsigned)
    with pytest.raises(RuntimeError, match="imzosi noto'g'ri"):
        v.verify(_signed([{"id": 9, "key": "GATE1.SP", "value": 1.0}], key="boshqa-kalit")[0])
    with pytest.raises(RuntimeError, match="muddati"):
        v.verify(_signed([{"id": 10, "key": "GATE1.SP", "value": 1.0}], exp_in=-60)[0])
    with pytest.raises(RuntimeError, match="loyiha"):
        v.verify(_signed([{"id": 11, "key": "GATE1.SP", "value": 1.0}], pid=2)[0])
    # replay keshi eskirgan nonce larni tozalaydi
    v.verify(fresh(nonce="t4"), now=time.time())
    assert "t4" in v.seen
    v.verify(fresh(nonce="t5"), now=time.time() + 3600 - 3590)
    assert v.cache_max > 0


def test_unsigned_command_not_written(gw, monkeypatch):
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
            return _Resp([{"id": 5, "project_id": 1, "key": "GATE1.SP", "value": 50.0}])
        if "/ack" in url:
            acks[5] = json
        return _Resp({})

    monkeypatch.setattr(gw.requests, "post", post, raising=False)
    cmd.run_once()
    assert src.writes == [] and acks[5]["status"] == "failed" and "imzosiz" in acks[5]["result"]


def test_server_claim_returns_verifiable_signature(client, users, admin, gw):
    """Server claim javobi gateway tekshiruvidan o'tadi (uchidan-uchiga)."""
    from conftest import add_member, send_command

    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "GATE1.SP", "name": "Z", "writable": True, "min_setpoint": 0, "max_setpoint": 100,
              "protocol": "modbus", "address": {"register": 10}},
        headers=users["engineer"],
    )
    op = add_member(client, admin, pid, "opr", "operator")
    ck = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()["key"]
    assert send_command(client, op, pid, r.json()["id"], 42).status_code == 201
    got = client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ck}).json()
    assert len(got) == 1 and got[0]["alg"] == "hmac-sha256-v1" and len(got[0]["nonce"]) == 32
    v = gw.CommandVerifier(ck, pid)
    v.verify(got[0])
    with pytest.raises(RuntimeError):
        gw.CommandVerifier("noto'g'ri", pid).verify(got[0])
