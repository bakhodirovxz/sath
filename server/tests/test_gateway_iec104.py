"""E5: IEC 60870-5-104 klienti — c104 server in-process: interrogation, spontan, sifat bitlari, SOE, setpoint."""

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

c104 = pytest.importorskip("c104")


def _load_gateway():
    sys.modules.setdefault("requests", types.ModuleType("requests"))
    path = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "ges_gateway.py"
    spec = importlib.util.spec_from_file_location("ges_gateway_104", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def rtu():
    srv = c104.Server(ip="127.0.0.1", port=24042)
    st = srv.add_station(common_address=7)
    pts = {
        "level": st.add_point(io_address=11, type=c104.Type.M_ME_NC_1),
        "power": st.add_point(io_address=12, type=c104.Type.M_ME_NB_1),
        "run": st.add_point(io_address=13, type=c104.Type.M_SP_TB_1),
        "sp": st.add_point(io_address=41, type=c104.Type.C_SE_NC_1),
    }
    pts["level"].value = 903.5
    pts["power"].value = c104.Int16(350)
    pts["run"].value = True
    received = []

    def on_cmd(point: c104.Point, previous_info: c104.Information, message: c104.IncomingMessage) -> c104.ResponseState:
        received.append(float(point.value))
        return c104.ResponseState.SUCCESS

    pts["sp"].on_receive(on_cmd)
    srv.start()
    try:
        yield srv, pts, received
    finally:
        srv.stop()


def _source(gw, commands=True):
    cfg = {
        "host": "127.0.0.1",
        "port": 24042,
        "common_address": 7,
        "interrogation_s": 1,
        "tags": [
            {"key": "RES.H", "ioa": 11, "type": "M_ME_NC_1"},
            {"key": "AGG1.P", "ioa": 12, "type": "M_ME_NB_1", "scale": 0.1},
            {"key": "AGG1.RUN", "ioa": 13, "type": "M_SP_TB_1"},
        ],
    }
    if commands:
        cfg["commands"] = [{"key": "GATE1.SP", "ioa": 41, "type": "C_SE_NC_1"}]
    return gw.Iec104Source(cfg)


def test_interrogation_spontaneous_quality_and_soe(rtu):
    gw = _load_gateway()
    srv, pts, _ = rtu
    src = _source(gw)
    try:
        time.sleep(1.5)
        items = {i["key"]: i for i in src.read_safe()}  # umumiy so'rov (interrogation) natijasi
        assert items["RES.H"]["value"] == 903.5 and items["RES.H"]["quality"] == "good"
        assert items["AGG1.P"]["value"] == 35.0  # skalyar × 0.1
        assert items["AGG1.RUN"]["value"] == 1.0 and items["AGG1.RUN"]["src_ts"].startswith("20")
        assert src.read_safe() == []  # o'zgarish yo'q
        # spontan o'zgarish
        pts["level"].value = 904.0
        pts["level"].transmit(cause=c104.Cot.SPONTANEOUS)
        time.sleep(0.5)
        items = {i["key"]: i for i in src.read_safe()}
        assert items["RES.H"]["value"] == 904.0
        # sifat bitlari: IV → bad, NT → uncertain, SB → substituted
        pts["level"].quality = c104.Quality.Invalid
        pts["level"].transmit(cause=c104.Cot.SPONTANEOUS)
        pts["power"].quality = c104.Quality.NonTopical
        pts["power"].transmit(cause=c104.Cot.SPONTANEOUS)
        time.sleep(0.5)
        items = {i["key"]: i for i in src.read_safe()}
        assert items["RES.H"]["quality"] == "bad" and items["AGG1.P"]["quality"] == "uncertain"
        pts["level"].quality = c104.Quality.Substituted
        pts["level"].transmit(cause=c104.Cot.SPONTANEOUS)
        time.sleep(0.5)
        assert {i["key"]: i for i in src.read_safe()}["RES.H"]["quality"] == "substituted"
        # SOE: vaqt tamg'ali bitta bit — ms tamg'a bilan hodisa
        pts["run"].value = False
        pts["run"].transmit(cause=c104.Cot.SPONTANEOUS)
        time.sleep(0.5)
        src.read_safe()
        assert src.soe and src.soe[-1]["point"] == "AGG1.RUN" and src.soe[-1]["state"] is False
        assert len(src.soe[-1]["ts"]) >= 23
    finally:
        src.close()


def test_setpoint_command_and_comms_loss(rtu):
    gw = _load_gateway()
    srv, pts, received = rtu
    src = _source(gw)
    try:
        time.sleep(1.2)
        src.write({"key": "GATE1.SP"}, 42.5)
        time.sleep(0.5)
        assert received and abs(received[-1] - 42.5) < 1e-3
        with pytest.raises(RuntimeError):
            src.write({"key": "YOQ"}, 1.0)
        # aloqa yo'q → read ConnectionError → read_safe har teg uchun bitta bad
        srv.stop()
        time.sleep(1.5)
        bad = src.read_safe()
        assert bad and {i["key"] for i in bad} == {"RES.H", "AGG1.P", "AGG1.RUN"}
        assert all(i["quality"] == "bad" for i in bad)
        assert src.read_safe() == []
    finally:
        src.close()


def test_commands_disabled_by_default(rtu):
    gw = _load_gateway()
    src = _source(gw, commands=False)
    try:
        with pytest.raises(RuntimeError, match="commands"):
            src.write({"key": "GATE1.SP"}, 1.0)
    finally:
        src.close()
