"""E3: OPC UA obuna rejimi — asyncua sync server in-process; o'zgarish poll davridan tez keladi."""

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

asyncua = pytest.importorskip("asyncua")


def _load_gateway():
    sys.modules.setdefault("requests", types.ModuleType("requests"))
    path = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "ges_gateway.py"
    spec = importlib.util.spec_from_file_location("ges_gateway_opc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def opc_server():
    from asyncua.sync import Server

    srv = Server()
    srv.set_endpoint("opc.tcp://127.0.0.1:48511/sath/")
    idx = srv.register_namespace("sath-test")
    obj = srv.nodes.objects.add_object(idx, "Plant")
    var = obj.add_variable(idx, "Level", 900.0)
    var.set_writable()
    var2 = obj.add_variable(idx, "Power", 10.0)
    var2.set_writable()
    srv.start()
    try:
        yield srv, var, var2
    finally:
        srv.stop()


def test_subscribe_mode_delivers_changes_faster_than_poll(opc_server):
    gw = _load_gateway()
    srv, var, var2 = opc_server
    cfg = {
        "url": "opc.tcp://127.0.0.1:48511/sath/",
        "mode": "subscribe",
        "publishing_interval_ms": 100,
        "tags": [
            {"key": "RES.H", "node_id": var.nodeid.to_string()},
            {"key": "AGG1.P", "node_id": var2.nodeid.to_string(), "deadband": 0.5},
        ],
    }
    src = gw.OpcUaSource(cfg)
    try:
        time.sleep(0.6)
        first = src.read_safe()  # boshlang'ich qiymatlar (obuna birinchi bildirishnomasi)
        keys = {i["key"] for i in first}
        assert {"RES.H", "AGG1.P"} <= keys
        assert all(i["quality"] == "good" and i["src_ts"] for i in first)
        var.write_value(905.5)
        t0 = time.time()
        got = None
        while time.time() - t0 < 3.0:
            items = src.read_safe()
            got = next((i for i in items if i["key"] == "RES.H"), None)
            if got:
                break
            time.sleep(0.05)
        assert got is not None and got["value"] == 905.5
        assert time.time() - t0 < 1.5  # 10 s poll davridan ancha tez
        # deadband 0.5: 10 → 10.2 o'zgarish bildirilmaydi, 10 → 11 bildiriladi
        var2.write_value(10.2)
        time.sleep(0.5)
        assert not any(i["key"] == "AGG1.P" for i in src.read_safe())
        var2.write_value(11.0)
        time.sleep(0.5)
        assert any(i["key"] == "AGG1.P" and i["value"] == 11.0 for i in src.read_safe())
        # o'zgarish yo'q → bo'sh (poll dan farqli — tarmoq yuki yo'q)
        assert src.read_safe() == []
    finally:
        src.close()


def test_poll_mode_reads_status_and_timestamp(opc_server):
    gw = _load_gateway()
    srv, var, _ = opc_server
    src = gw.OpcUaSource({"url": "opc.tcp://127.0.0.1:48511/sath/", "tags": [{"key": "RES.H", "node_id": var.nodeid.to_string()}]})
    try:
        items = src.read_safe()
        assert items[0]["key"] == "RES.H" and items[0]["value"] == 900.0 and items[0]["quality"] == "good"
        assert items[0]["src_ts"].startswith("20")
    finally:
        src.close()


def test_subscribe_reconnects_after_session_loss(opc_server):
    gw = _load_gateway()
    srv, var, _ = opc_server
    cfg = {"url": "opc.tcp://127.0.0.1:48511/sath/", "mode": "subscribe", "publishing_interval_ms": 100,
           "tags": [{"key": "RES.H", "node_id": var.nodeid.to_string()}]}
    src = gw.OpcUaSource(cfg)
    try:
        time.sleep(0.5)
        src.read_safe()
        # sessiya uzildi (tarmoq/server qayta ishga tushdi) — klient tomonda ulanish yopiladi
        src.client.disconnect()
        bad = src.read_safe()  # aloqa yo'q → bitta bad yozuv, qayta ulanish urinishi
        assert bad and bad[0]["quality"] == "bad" and bad[0]["key"] == "RES.H"
        var.write_value(910.0)
        ok = None
        for _ in range(30):
            items = src.read_safe()
            ok = next((i for i in items if i["key"] == "RES.H" and i["quality"] == "good"), None)
            if ok:
                break
            time.sleep(0.2)
        assert ok is not None and ok["value"] == 910.0
    finally:
        src.close()
