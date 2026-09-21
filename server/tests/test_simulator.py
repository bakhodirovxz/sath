"""E4: GES simulyatori — stsenariylar kutilgan ketma-ketlikni beradi; Modbus/OPC UA orqali gateway
o'qiydi va buyruq yozadi."""

import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    sys.modules.setdefault("requests", types.ModuleType("requests"))
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass (from __future__ import annotations) modulni topishi uchun
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sim():
    return _load("ges_simulator_t", "deploy/simulator/ges_simulator.py")


@pytest.fixture(scope="module")
def gw():
    return _load("ges_gateway_sim", "deploy/gateway/ges_gateway.py")


def _run(sim, scenario, ticks, dt=None):
    p = sim.Plant(sim.default_plant())
    r = sim.Runner(p, scenario, dt=dt or sim.SCENARIOS[scenario].get("dt", 1.0))
    rows = [dict(r.step()) for _ in range(ticks)]
    return p, rows


def test_normal_steady(sim):
    p, rows = _run(sim, "normal", 120)
    last = rows[-1]
    assert abs(last["AGG1.P"] - 35) < 0.5 and abs(last["AGG2.P"] - 35) < 0.5 and last["AGG3.P"] == 0
    assert last["AGG1.RUN"] == 1 and last["AGG3.RUN"] == 0 and 902 < last["RES.H"] < 904
    assert 49.9 < last["GRID.F"] < 50.1 and last["AGG1.Q"] > 50 and p.soe == []


def test_unit_trip_sequence(sim):
    p, rows = _run(sim, "unit_trip", 320)
    # trip 40 s da: 45 s gacha quvvat 0 ga tushadi, RUN=0; 300 s da qayta ishga tushadi
    assert rows[38]["AGG1.P"] > 30 and rows[45]["AGG1.P"] < 1.0 and rows[45]["AGG1.RUN"] == 0
    assert rows[319]["AGG1.RUN"] == 1 and rows[319]["AGG1.P"] > 20
    pts = [(e["point"], e["state"]) for e in p.soe]
    assert pts[:2] == [("AGG1.PROT", "TRIP"), ("AGG1.CB", "OPEN")] and ("AGG1", "START") in pts
    assert all("ts" in e and len(e["ts"]) >= 24 for e in p.soe)  # ms tamg'a


def test_load_rejection_overspeed(sim):
    _, rows = _run(sim, "load_rejection", 130)
    f = [r["GRID.F"] for r in rows]
    assert max(f[60:120]) > 50.5  # yuk tashlash → ortiqcha tezlik
    assert max(f) < 65.0  # regulyator statizmi (5 %) quvvatni kamaytiradi — cheksiz o'smaydi (ilgari 79 Hz)
    assert abs(f[25] - 50.0) < 0.05


def test_gate_fault_stuck(sim):
    p, rows = _run(sim, "gate_fault", 120)
    assert rows[24]["GATE1.POS"] > 60.5
    assert abs(rows[119]["GATE1.POS"] - rows[30]["GATE1.POS"]) < 1e-6
    assert ("GATE1", "STUCK") in [(e["point"], e["state"]) for e in p.soe]
    p.write("GATE1.SP", 20.0)  # buyruq bajarilmaydi
    assert p.gate_sp == 80.0


def test_flood_spills(sim):
    _, rows = _run(sim, "flood", 720)  # dt = 60 s → 12 soat
    assert rows[-1]["RES.H"] > 905.0 and rows[-1]["RES.QSPILL"] > 0 and rows[0]["RES.QSPILL"] == 0


def test_sensor_faults(sim):
    p, rows = _run(sim, "sensor_stuck", 200)
    assert rows[199]["RES.H"] == rows[21]["RES.H"] and p.res.elev_m > rows[21]["RES.H"]
    _, rows = _run(sim, "sensor_noisy", 100)
    v = [r["AGG1.VIB"] for r in rows[30:]]
    assert max(v) - min(v) > 3.0
    _, rows = _run(sim, "chatter", 120)
    p2 = [r["AGG2.P"] for r in rows]
    assert min(p2[40:]) < 30.6 and max(p2[40:]) > 30.4  # 30 ↔ 31 tebranadi


def test_record_and_replay(sim, tmp_path):
    rec = tmp_path / "run.jsonl"
    p = sim.Plant(sim.default_plant())
    sim.Runner(p, "normal", dt=1.0, speed=1000, record=str(rec)).run([], duration_s=5)
    rows = [json.loads(x) for x in rec.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5 and "RES.H" in rows[0]["tags"]
    got = []

    class Sink:
        def update(self, tags, plant):
            got.append(tags["RES.H"])

    sim.Replayer(str(rec), dt=1.0, speed=1000).run([Sink()])
    assert got == [r["tags"]["RES.H"] for r in rows]


def test_gateway_config_matches_registers(sim):
    cfg = sim.gateway_config(modbus="127.0.0.1:5021")
    tags = cfg["sources"][0]["tags"]
    assert tags[0]["key"] == "RES.H" and tags[0]["address"] == sim.REGISTER_BASE
    assert cfg["commands"] is True and all(t["type"] == "float32" for t in tags)


def test_modbus_server_with_gateway_source_and_command(sim, gw):
    pytest.importorskip("pymodbus")
    ms = sim.ModbusServer("127.0.0.1:5021")
    ms.start()
    p = sim.Plant(sim.default_plant())
    r = sim.Runner(p, "normal", dt=1.0)
    src = None
    try:
        tags = r.step()
        ms.update(tags, p)
        src = gw.ModbusSource(
            {
                "host": "127.0.0.1",
                "port": 5021,
                "tags": [
                    {"key": "RES.H", "address": sim.register_of("RES.H"), "type": "float32"},
                    {"key": "AGG1.P", "address": sim.register_of("AGG1.P"), "type": "float32"},
                    {"key": "GATE1.SP", "address": sim.register_of("GATE1.SP"), "type": "float32"},
                ],
            }
        )
        items = {i["key"]: i for i in src.read_safe()}
        assert abs(items["RES.H"]["value"] - tags["RES.H"]) < 0.01
        assert items["RES.H"]["quality"] == "good"
        # buyruq: gateway registrga yozadi → simulyator plant.write → zatvor harakatlanadi
        src.write({"address": sim.register_of("GATE1.SP"), "type": "float32"}, 90.0)
        for _ in range(5):
            ms.update(r.step(), p)
        assert p.gate_sp == 90.0 and p.gate_pos > 60.5
        assert ("GATE1.SP", "90") in [(e["point"], e["state"]) for e in p.soe]
        # aloqa uzilishi: server to'xtaydi → gateway bad yozuv
        p.comms = False
        ms.update(r.step(), p)
        time.sleep(0.5)
        bad = src.read_safe()
        assert bad and all(i["quality"] == "bad" for i in bad)
    finally:
        if src:
            src.close()
        ms.stop()


def test_opcua_server_with_gateway_subscribe(sim, gw):
    pytest.importorskip("asyncua")
    srv = sim.OpcUaServer("opc.tcp://127.0.0.1:48521/sath-sim/")
    srv.start()
    p = sim.Plant(sim.default_plant())
    r = sim.Runner(p, "normal", dt=1.0)
    src = None
    try:
        srv.update(r.step(), p)
        src = gw.OpcUaSource(
            {
                "url": "opc.tcp://127.0.0.1:48521/sath-sim/",
                "mode": "subscribe",
                "publishing_interval_ms": 100,
                "tags": [
                    {"key": "RES.H", "node_id": "ns=2;s=RES.H"},
                    {"key": "AGG1.P", "node_id": "ns=2;s=AGG1.P"},
                ],
            }
        )
        time.sleep(0.6)
        items = {i["key"]: i for i in src.read_safe()}
        assert "RES.H" in items and items["RES.H"]["quality"] == "good" and items["RES.H"]["src_ts"]
        # comms yo'q → Bad status → gateway bad sifat
        p.comms = False
        srv.update(r.step(), p)
        time.sleep(0.5)
        items = {i["key"]: i for i in src.read_safe()}
        assert items and all(i["quality"] == "bad" for i in items.values())
        p.comms = True
        srv.update(r.step(), p)
        time.sleep(0.5)
        items = {i["key"]: i for i in src.read_safe()}
        assert items and all(i["quality"] == "good" for i in items.values())
    finally:
        if src:
            src.close()
        srv.stop()
