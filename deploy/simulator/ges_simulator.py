"""GES simulyatori — sinov stendi (E4): haqiqiy stansiyaga o'xshash dinamik model, Modbus TCP va OPC UA
server sifatida ishlaydi (gateway haqiqiy protokol bilan ulanadi), stsenariylar, SOE, yozib olish/qayta ijro.

Fizika `ges_sim` dan (ikkinchi dvigatel yo'q): ombor balansi (`reservoir.step`, `spillway`), quvur
yo'qotishi (`penstock.net_head`), turbina/generator (`turbine.dispatch`). Agregat dinamikasi (yuk
qabul/tashlash, trip) va zatvor harakati — birinchi tartibli kechikishlar (T_g, T_agg), chastota —
2H·dΔω/dt = P_m − P_L − D·Δω (izolyatsiyalangan rejimda; tarmoqda Δω = 0).

Teglar (kalitlar Sath sensor kalitlari bilan bir xil):
  RES.H (m), RES.QIN (m³/s), RES.QSPILL (m³/s), TW.H (m), GATE1.SP (%, yoziladigan), GATE1.POS (%),
  AGGn.P (MW), AGGn.Q (m³/s), AGGn.RUN (0/1), AGGn.SP (MW, yoziladigan), AGGn.VIB (mm/s),
  AGGn.TEMP (°C), GRID.F (Hz), TR1.OIL (°C), GW.* — gateway o'zi qo'shadi.
Stsenariylar: normal, load_rejection, unit_trip, gate_fault, flood, comms_loss, sensor_stuck,
  sensor_noisy, chatter — vaqt jadvali bilan (`SCENARIOS`), har biri kutilgan hodisalar ketma-ketligini
  beradi (tests). SOE: ms tamg'ali diskret hodisalar (trip, zatvor, rele) → `soe.jsonl` (D3 da serverga).
Ishga tushirish:
  python ges_simulator.py --scenario normal --modbus 0.0.0.0:5020 --opcua opc.tcp://0.0.0.0:4840
  python ges_simulator.py --scenario unit_trip --record run.jsonl
  python ges_simulator.py --replay run.jsonl --modbus :5020          (operator mashqi, F8/P8)
  python ges_simulator.py --print-gateway-config > gateway_config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ges_sim.penstock import PenstockSpec, net_head
from ges_sim.reservoir import ReservoirSpec, ReservoirState, StorageCurve, step
from ges_sim.spillway import Spillway
from ges_sim.turbine import TurbineSpec, dispatch

log = logging.getLogger("ges_simulator")

# ---------- Stansiya ----------


def default_plant() -> dict:
    """O'rta GES (scenario.example_params bilan mos): 3 agregat × 40 MW, ombor 850–915 m."""
    return {
        "reservoir": {
            "curve": {"elevations_m": [850, 870, 890, 905, 915], "volumes_mcm": [0, 60, 220, 480, 700]},
            "dead_level_m": 870,
            "normal_level_m": 905,
            "max_level_m": 912,
            "initial_level_m": 903,
            "tailwater_m": 840,
            "other_outflow_m3s": 5,
            "spillway": {"crest_m": 905, "width_m": 24, "coefficient": 0.49, "bays": 2},
        },
        "penstock": {"length_m": 180, "diameter_m": 4.0, "roughness_mm": 0.1, "minor_loss_k": 0.6},
        "units": [
            {"name": f"Agregat {i}", "type": "Francis", "rated_power_mw": 40, "rated_head_m": 60, "rated_flow_m3s": 75}
            for i in (1, 2, 3)
        ],
        "inflow_m3s": 150.0,
        "grid": {"h_inertia": 3.5, "d_load": 1.0, "isolated": False},
        "gate": {"t_s": 20.0, "sp0": 60.0},  # zatvor servo vaqti, boshlang'ich ochilish %
        "unit_t_s": 8.0,  # yuk qabul/tashlash kechikishi
        "setpoints_mw": [35.0, 35.0, 0.0],
    }


@dataclass
class UnitState:
    name: str
    sp_mw: float
    p_mw: float = 0.0
    q_m3s: float = 0.0
    run: bool = False
    tripped: bool = False
    vib: float = 1.2
    temp: float = 55.0


@dataclass
class Plant:
    cfg: dict
    t: float = 0.0
    res: ReservoirState | None = None
    spec: ReservoirSpec | None = None
    units: list[UnitState] = field(default_factory=list)
    turbines: list[TurbineSpec] = field(default_factory=list)
    penstock: PenstockSpec | None = None
    inflow: float = 150.0
    gate_sp: float = 60.0
    gate_pos: float = 60.0
    gate_stuck: bool = False
    dw: float = 0.0  # Δω p.u.
    comms: bool = True  # False → serverlar "bad"/javobsiz
    stuck: set[str] = field(default_factory=set)  # qotgan sensorlar
    noisy: dict[str, float] = field(default_factory=dict)  # kalit → shovqin sigma
    bad: set[str] = field(default_factory=set)  # OPC UA Bad status
    soe: list[dict] = field(default_factory=list)
    last: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        r = self.cfg["reservoir"]
        curve = StorageCurve(tuple(r["curve"]["elevations_m"]), tuple(r["curve"]["volumes_mcm"]))
        sp = r.get("spillway")
        self.spec = ReservoirSpec(
            curve,
            dead_level_m=r["dead_level_m"],
            normal_level_m=r["normal_level_m"],
            max_level_m=r.get("max_level_m"),
            spillway=Spillway(sp["crest_m"], sp["width_m"], m=sp.get("coefficient", 0.49), bays=sp.get("bays", 1)) if sp else None,
            tailwater_m=r.get("tailwater_m", 0.0),
            other_outflow_m3s=r.get("other_outflow_m3s", 0.0),
        )
        self.res = ReservoirState(r["initial_level_m"], curve.volume(r["initial_level_m"]))
        p = self.cfg["penstock"]
        self.penstock = PenstockSpec(p["length_m"], p["diameter_m"], p.get("roughness_mm", 0.1), p.get("minor_loss_k", 0.0))
        self.turbines = [TurbineSpec(**u) for u in self.cfg["units"]]
        self.units = [
            UnitState(u.name, sp, run=sp > 0) for u, sp in zip(self.turbines, self.cfg["setpoints_mw"], strict=False)
        ]
        self.inflow = float(self.cfg["inflow_m3s"])
        self.gate_sp = self.gate_pos = float(self.cfg["gate"]["sp0"])

    # ---- hodisalar (SOE) ----
    def event(self, point: str, state: str, note: str = "") -> None:
        ev = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "t": round(self.t, 3), "point": point, "state": state, "note": note}
        self.soe.append(ev)
        log.info("SOE %s %s %s", point, state, note)

    # ---- boshqaruv (gateway yozuvlari) ----
    def write(self, key: str, value: float) -> None:
        if key == "GATE1.SP":
            if self.gate_stuck:
                self.event("GATE1", "STUCK", f"buyruq {value:g} % bajarilmadi")
                return
            self.gate_sp = max(0.0, min(100.0, float(value)))
            self.event("GATE1.SP", f"{self.gate_sp:g}", "operator buyrug'i")
        for i, u in enumerate(self.units, 1):
            if key == f"AGG{i}.SP":
                u.sp_mw = max(0.0, float(value))
                if u.sp_mw > 0 and not u.run and not u.tripped:
                    u.run = True
                    self.event(f"AGG{i}", "START", "setpoint > 0")
                if u.sp_mw <= 0 and u.run:
                    u.run = False
                    self.event(f"AGG{i}", "STOP", "setpoint 0")

    # ---- dinamika ----
    def tick(self, dt: float) -> dict[str, float]:
        self.t += dt
        g = self.cfg["gate"]
        if not self.gate_stuck:
            self.gate_pos += (self.gate_sp - self.gate_pos) * min(dt / g["t_s"], 1.0)
        gross = self.res.elev_m - self.spec.tailwater_m
        # Agregatlar: setpoint ga birinchi tartibli yaqinlashish; trip → 0
        tu = self.cfg["unit_t_s"]
        grid = self.cfg["grid"]
        # Regulyator statizmi (5 %): izolyatsiyalangan rejimda chastota oshsa quvvat kamayadi
        droop = max(1.0 - self.dw / grid.get("droop", 0.05), 0.0) if grid.get("isolated") else 1.0
        for u, ts in zip(self.units, self.turbines, strict=False):
            target = 0.0 if (u.tripped or not u.run) else min(u.sp_mw * droop, ts.rated_power_mw * ts.max_load)
            u.p_mw += (target - u.p_mw) * min(dt / (tu if not u.tripped else 1.0), 1.0)
            if u.p_mw < 0.05:
                u.p_mw = 0.0
        # Sarf: quvvatdan (dispatch teskari) — soddalashtirib turbina FIK bilan
        total_p = sum(u.p_mw for u in self.units)
        q_total = 0.0
        for u, ts in zip(self.units, self.turbines, strict=False):
            if u.p_mw > 0 and gross > 0:
                h = net_head(gross, u.q_m3s, self.penstock)
                eta = max(ts.efficiency(max(u.q_m3s, ts.min_flow), h), 0.5)
                u.q_m3s = u.p_mw * 1e6 / (998.2 * 9.80665 * max(h, 1.0) * eta)
            else:
                u.q_m3s = 0.0
            q_total += u.q_m3s
            # vibratsiya/harorat: yuklanish bilan, qo'pol zonada (30–50 %) yuqori
            load = u.p_mw / ts.rated_power_mw
            rough = 1.0 + (2.5 if 0.25 < load < 0.5 else 0.0)
            u.vib += ((1.0 + 2.0 * load) * rough - u.vib) * min(dt / 30.0, 1.0)
            u.temp += ((45.0 + 30.0 * load) - u.temp) * min(dt / 600.0, 1.0)
        # Zatvor orqali tashlama (qo'shimcha suv o'tkazish inshooti sifatida): ochilish % → m³/s
        q_gate = 400.0 * (self.gate_pos / 100.0) ** 1.5 if self.res.elev_m > self.spec.dead_level_m else 0.0
        self.res, flows = step(self.res, self.spec, self.inflow, q_total + q_gate, dt)
        # Chastota (izolyatsiyalangan rejim): 2H·dΔω/dt = P_m − P_L − D·Δω; tarmoqda 0
        if grid.get("isolated"):
            p_load = grid.get("p_load_pu", 0.6)
            p_m = total_p / sum(t.rated_power_mw for t in self.turbines)
            self.dw += dt * (p_m - p_load - grid["d_load"] * self.dw) / (2 * grid["h_inertia"])
        else:
            self.dw += (0.0 - self.dw) * min(dt / 5.0, 1.0)
        d = dispatch(q_total, gross, self.turbines, self.penstock, True) if q_total > 0 else None
        tags = {
            "RES.H": self.res.elev_m,
            "RES.QIN": self.inflow,
            "RES.QSPILL": flows["spill"],
            "TW.H": self.spec.tailwater_m + 0.002 * (q_total + q_gate + flows["spill"]),
            "GATE1.SP": self.gate_sp,
            "GATE1.POS": self.gate_pos,
            "GRID.F": 50.0 * (1 + self.dw),
            "TR1.OIL": 40.0 + 0.5 * total_p,
            "NET.H": d.head_net_m if d else gross,
        }
        for i, u in enumerate(self.units, 1):
            tags[f"AGG{i}.P"] = u.p_mw
            tags[f"AGG{i}.Q"] = u.q_m3s
            tags[f"AGG{i}.RUN"] = 1.0 if u.run and not u.tripped else 0.0
            tags[f"AGG{i}.SP"] = u.sp_mw
            tags[f"AGG{i}.VIB"] = u.vib
            tags[f"AGG{i}.TEMP"] = u.temp
        # Sensor nosozliklari
        for k, sigma in self.noisy.items():
            if k in tags:
                tags[k] += random.gauss(0, sigma)
        for k in self.stuck:
            if k in self.last:
                tags[k] = self.last[k]
        self.last = dict(tags)
        return tags

    # ---- stsenariy amallari ----
    def trip(self, idx: int, reason: str = "himoya") -> None:
        u = self.units[idx - 1]
        if not u.tripped:
            u.tripped, u.run = True, False
            self.event(f"AGG{idx}.PROT", "TRIP", reason)
            self.event(f"AGG{idx}.CB", "OPEN", "generator uzgichi")

    def reset_trip(self, idx: int) -> None:
        u = self.units[idx - 1]
        u.tripped = False
        self.event(f"AGG{idx}.PROT", "RESET", "")


# ---------- Stsenariylar ----------
# (t soniya, funksiya(plant)) — vaqt bo'yicha o'sib boruvchi jadval

SCENARIOS: dict[str, dict] = {
    "normal": {"desc": "normal ish: 2 agregat 35 MW, kiruvchi 150 m³/s", "timeline": []},
    "load_rejection": {
        "desc": "t=30 s: izolyatsiyalangan tarmoq, t=60 s: yuk tashlash (P_L → 0) — ortiqcha tezlik",
        "timeline": [
            (30, lambda p: p.cfg["grid"].update(isolated=True, p_load_pu=0.58)),
            (60, lambda p: (p.cfg["grid"].update(p_load_pu=0.0), p.event("GRID.CB", "OPEN", "yuk tashlash"))),
            (120, lambda p: (p.cfg["grid"].update(p_load_pu=0.58), p.event("GRID.CB", "CLOSE", ""))),
        ],
    },
    "unit_trip": {
        "desc": "t=40 s: Agregat 1 himoya bilan o'chadi (trip), t=300 s: qayta ishga tushirish",
        "timeline": [
            (40, lambda p: p.trip(1, "podshipnik harorati")),
            (300, lambda p: (p.reset_trip(1), p.write("AGG1.SP", 35.0))),
        ],
    },
    "gate_fault": {
        "desc": "t=20 s: zatvor 80 % ga buyruq, t=25 s: zatvor qotadi (STUCK) — buyruq bajarilmaydi",
        "timeline": [
            (20, lambda p: p.write("GATE1.SP", 80.0)),
            (25, lambda p: (setattr(p, "gate_stuck", True), p.event("GATE1", "STUCK", "mexanik nosozlik"))),
        ],
    },
    "flood": {
        "desc": "kiruvchi oqim 150 → 2500 m³/s (t=10…120 min), sath NPU dan oshadi, tashlama boshlanadi (dt=60 s)",
        "dt": 60.0,
        "timeline": [(600 + 600 * k, (lambda v: lambda p: setattr(p, "inflow", v))(150 + 2350 * k / 11)) for k in range(12)],
    },
    "comms_loss": {
        "desc": "t=30…90 s aloqa yo'q (Modbus javob bermaydi, OPC UA Bad status)",
        "timeline": [(30, lambda p: setattr(p, "comms", False)), (90, lambda p: setattr(p, "comms", True))],
    },
    "sensor_stuck": {
        "desc": "t=20 s: RES.H sensori qotadi (qiymat o'zgarmaydi), inflow 400 m³/s",
        "timeline": [(20, lambda p: (p.stuck.add("RES.H"), setattr(p, "inflow", 400.0)))],
    },
    "sensor_noisy": {
        "desc": "t=20 s: AGG1.VIB shovqinli (σ = 2 mm/s) — alarm chatter uchun",
        "timeline": [(20, lambda p: p.noisy.update({"AGG1.VIB": 2.0}))],
    },
    "chatter": {
        "desc": "AGG2.P chegara atrofida tebranadi: setpoint 30 ↔ 31 MW har 10 s (deadband/kechikish testi)",
        "timeline": [(10 + 10 * k, (lambda v: lambda p: p.write("AGG2.SP", v))(31.0 if k % 2 == 0 else 30.0)) for k in range(30)],
    },
}


class Runner:
    """Stsenariyni real vaqtda (yoki tezlashtirib) ijro etadi; har tickda teglar serverlarga yoziladi."""

    def __init__(self, plant: Plant, scenario: str, dt: float = 1.0, speed: float = 1.0, record: str | None = None):
        self.plant = plant
        self.timeline = sorted(SCENARIOS[scenario]["timeline"], key=lambda x: x[0])
        self.dt, self.speed = dt, speed
        self.done = 0
        self.record = open(record, "a", encoding="utf-8") if record else None
        self.tags: dict[str, float] = {}
        self._stop = threading.Event()

    def step(self) -> dict[str, float]:
        while self.done < len(self.timeline) and self.timeline[self.done][0] <= self.plant.t + self.dt:
            self.timeline[self.done][1](self.plant)
            self.done += 1
        self.tags = self.plant.tick(self.dt)
        if self.record:
            self.record.write(json.dumps({"t": round(self.plant.t, 3), "tags": {k: round(v, 4) for k, v in self.tags.items()}, "soe": self.plant.soe[-3:]}) + "\n")
        return self.tags

    def run(self, servers: list, duration_s: float | None = None) -> None:
        try:
            while not self._stop.is_set() and (duration_s is None or self.plant.t < duration_s):
                tags = self.step()
                for s in servers:
                    s.update(tags, self.plant)
                time.sleep(self.dt / self.speed)
        finally:
            if self.record:
                self.record.close()

    def stop(self) -> None:
        self._stop.set()


class Replayer:
    """Yozib olingan seriyani qayta ijro etadi (operator mashqi): teglar faylga yozilgan tartibda."""

    def __init__(self, path: str, dt: float = 1.0, speed: float = 1.0):
        self.rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        self.dt, self.speed = dt, speed
        self.i = 0

    def run(self, servers: list, plant: Plant | None = None) -> None:
        for row in self.rows:
            for s in servers:
                s.update(row["tags"], plant)
            time.sleep(self.dt / self.speed)


# ---------- Protokol serverlari ----------

REGISTER_BASE = 100  # har teg 2 registr (float32), tartib TAG_ORDER bo'yicha
TAG_ORDER = [
    "RES.H", "RES.QIN", "RES.QSPILL", "TW.H", "GATE1.SP", "GATE1.POS", "GRID.F", "TR1.OIL", "NET.H",
    "AGG1.P", "AGG1.Q", "AGG1.RUN", "AGG1.SP", "AGG1.VIB", "AGG1.TEMP",
    "AGG2.P", "AGG2.Q", "AGG2.RUN", "AGG2.SP", "AGG2.VIB", "AGG2.TEMP",
    "AGG3.P", "AGG3.Q", "AGG3.RUN", "AGG3.SP", "AGG3.VIB", "AGG3.TEMP",
]
WRITABLE = {"GATE1.SP", "AGG1.SP", "AGG2.SP", "AGG3.SP"}


def register_of(key: str) -> int:
    return REGISTER_BASE + 2 * TAG_ORDER.index(key)


def gateway_config(server: str = "http://localhost:8000", project_id: int = 1, modbus: str = "127.0.0.1:5020", opcua: str | None = None, iec104: str | None = None) -> dict:
    host, port = modbus.rsplit(":", 1)
    src = {
        "type": "modbus",
        "host": host or "127.0.0.1",
        "port": int(port),
        "tags": [{"key": k, "address": register_of(k), "type": "float32", "scale": 1, "unit_id": 1} for k in TAG_ORDER],
    }
    cfg = {"server": server, "project_id": project_id, "ingest_key": "<ingest key>", "commands": True, "command_key": "<command key>", "interval_s": 5, "diag": True, "sources": [src]}
    if opcua:
        cfg["sources"].append({"type": "opcua", "url": opcua, "mode": "subscribe", "publishing_interval_ms": 500, "tags": [{"key": k, "node_id": f"ns=2;s={k}"} for k in TAG_ORDER]})
    if iec104:
        h, p = iec104.rsplit(":", 1)
        cfg["sources"].append(iec104_gateway_source(h or "127.0.0.1", int(p)))
    return cfg


class ModbusServer:
    """pymodbus TCP server: har teg float32 (2 registr) holding registrlarida; yoziladigan teglar
    (GATE1.SP, AGGn.SP) gateway yozganda Plant.write ga o'tadi. comms=False → server to'xtaydi."""

    def __init__(self, bind: str = "0.0.0.0:5020"):
        from pymodbus.datastore import (
            ModbusSequentialDataBlock,
            ModbusServerContext,
            ModbusSlaveContext,
        )

        host, port = bind.rsplit(":", 1)
        self.host, self.port = host or "0.0.0.0", int(port)
        self.block = ModbusSequentialDataBlock(0, [0] * (REGISTER_BASE + 2 * len(TAG_ORDER) + 10))
        self.store = ModbusSlaveContext(hr=self.block, ir=self.block)
        # pymodbus 3.9 kontekst bloklarni nusxalaydi — server ishlatadigan blokka yozamiz
        self.block = self.store.store["h"]
        self.store.store["i"] = self.block  # input registrlar ham shu qiymatlar
        self.context = ModbusServerContext(slaves=self.store, single=True)
        self._thread = None
        self._loop = None
        self._server = None
        self._running = False
        self._plant = None
        self._last_written: dict[str, float] = {}
        self._initialized = False

    def _encode(self, value: float) -> list[int]:
        from pymodbus.client.mixin import ModbusClientMixin

        return ModbusClientMixin.convert_to_registers(float(value), ModbusClientMixin.DATATYPE.FLOAT32)

    def _decode(self, regs: list[int]) -> float:
        from pymodbus.client.mixin import ModbusClientMixin

        return float(ModbusClientMixin.convert_from_registers(regs, ModbusClientMixin.DATATYPE.FLOAT32))

    def start(self) -> None:
        import asyncio

        from pymodbus.server import ModbusTcpServer

        async def serve():
            self._server = ModbusTcpServer(self.context, address=(self.host, self.port))
            await self._server.serve_forever()

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(serve())
            except Exception as e:  # noqa: BLE001
                log.error("Modbus server: %s", e)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        self._running = True
        time.sleep(0.3)
        log.info("Modbus TCP server %s:%d", self.host, self.port)

    def stop(self) -> None:
        if self._server is not None and self._loop is not None:
            import asyncio

            asyncio.run_coroutine_threadsafe(self._server.shutdown(), self._loop)
        self._running = False

    def update(self, tags: dict[str, float], plant: Plant | None) -> None:
        self._plant = plant
        if plant is not None and not plant.comms:
            if self._running:
                self.stop()  # aloqa yo'q — server javob bermaydi
            return
        if plant is not None and plant.comms and not self._running and self._thread is not None:
            self.start()
        # gateway yozgan setpointlar → plant (yozilgan registr o'qilgan qiymatdan farq qilsa);
        # birinchi yangilanishda registrlar hali 0 — avval to'ldiriladi
        if self._initialized:
            for key in WRITABLE:
                regs = self.block.getValues(register_of(key) + 1, 2)  # pymodbus datablock 1-asosli
                try:
                    v = self._decode(regs)
                except Exception:  # noqa: BLE001
                    continue
                if plant is not None and key in tags and abs(v - tags[key]) > 1e-3 and self._last_written.get(key) != v:
                    self._last_written[key] = v
                    plant.write(key, v)
        self._initialized = True
        for key, val in tags.items():
            if key in TAG_ORDER:
                self.block.setValues(register_of(key) + 1, self._encode(val))


class OpcUaServer:
    """asyncua sync server: ns=2;s=<KEY> o'zgaruvchilari; yoziladigan teglar → Plant.write;
    comms=False → barcha o'zgaruvchilar Bad status bilan."""

    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/sath-sim/"):
        from asyncua.sync import Server

        self.server = Server()
        self.endpoint = endpoint
        self.server.set_endpoint(endpoint)
        self.idx = self.server.register_namespace("sath-sim")
        self.server.register_namespace("sath-sim-2")
        obj = self.server.nodes.objects.add_object(self.idx, "GES")
        from asyncua import ua

        self.vars = {}
        for k in TAG_ORDER:
            v = obj.add_variable(ua.NodeId(k, 2), k, 0.0)
            if k in WRITABLE:
                v.set_writable()
            self.vars[k] = v
        self._last: dict[str, float] = {}
        self._initialized = False

    def start(self) -> None:
        self.server.start()
        log.info("OPC UA server ishga tushdi")

    def stop(self) -> None:
        self.server.stop()

    def update(self, tags: dict[str, float], plant: Plant | None) -> None:
        from asyncua import ua

        if self._initialized:
            for key in WRITABLE:
                try:
                    v = float(self.vars[key].read_value())
                except Exception:  # noqa: BLE001
                    continue
                if plant is not None and key in tags and abs(v - tags[key]) > 1e-3 and self._last.get(key) != v:
                    self._last[key] = v
                    plant.write(key, v)
        self._initialized = True
        bad = plant is not None and not plant.comms
        for key, val in tags.items():
            if key not in self.vars:
                continue
            dv = ua.DataValue(
                ua.Variant(float(val), ua.VariantType.Double),
                ua.StatusCode(ua.StatusCodes.BadCommunicationError) if bad else ua.StatusCode(ua.StatusCodes.Good),
                SourceTimestamp=datetime.now(timezone.utc),
            )
            self.vars[key].write_value(dv)


IEC104_CA = 1
IEC104_MEAS_BASE = 100  # M_ME_NC_1 (float); *.RUN teglari M_SP_TB_1 (vaqt tamg'ali — SOE)
IEC104_CMD_BASE = 200  # C_SE_NC_1 setpointlar (WRITABLE tartibida)


def ioa_of(key: str) -> int:
    return IEC104_MEAS_BASE + TAG_ORDER.index(key)


def cmd_ioa_of(key: str) -> int:
    return IEC104_CMD_BASE + sorted(WRITABLE).index(key)


def iec104_gateway_source(host: str = "127.0.0.1", port: int = 2404) -> dict:
    """Gateway `iec104` manbasi konfiguratsiyasi (simulyator 104 serveriga mos)."""
    tags = [{"key": k, "ioa": ioa_of(k), "type": "M_SP_TB_1" if k.endswith(".RUN") else "M_ME_NC_1"} for k in TAG_ORDER]
    return {
        "type": "iec104",
        "host": host,
        "port": port,
        "common_address": IEC104_CA,
        "interrogation_s": 300,
        "tags": tags,
        "commands": [{"key": k, "ioa": cmd_ioa_of(k), "type": "C_SE_NC_1"} for k in sorted(WRITABLE)],
    }


class Iec104Server:
    """IEC 60870-5-104 server (c104): o'lchovlar M_ME_NC_1 (IOA 100+), *.RUN — M_SP_TB_1 (vaqt tamg'ali,
    SOE), setpointlar C_SE_NC_1 (IOA 200+) → Plant.write. comms=False → server to'xtaydi (aloqa uzilishi)."""

    def __init__(self, bind: str = "0.0.0.0:2404"):
        import c104

        self.c104 = c104
        host, port = bind.rsplit(":", 1)
        self.host, self.port = host or "0.0.0.0", int(port)
        self.server = c104.Server(ip=self.host, port=self.port)
        self.station = self.server.add_station(common_address=IEC104_CA)
        self.points = {}
        for k in TAG_ORDER:
            typ = c104.Type.M_SP_TB_1 if k.endswith(".RUN") else c104.Type.M_ME_NC_1
            self.points[k] = self.station.add_point(io_address=ioa_of(k), type=typ)
        self.cmd_points: dict[int, str] = {}
        self._plant: Plant | None = None
        cb = self._on_command
        cb.__func__.__annotations__ = {  # c104 callback imzosini tekshiradi
            "point": c104.Point,
            "previous_info": c104.Information,
            "message": c104.IncomingMessage,
            "return": c104.ResponseState,
        }
        for k in sorted(WRITABLE):
            pt = self.station.add_point(io_address=cmd_ioa_of(k), type=c104.Type.C_SE_NC_1)
            pt.on_receive(cb)
            self.cmd_points[cmd_ioa_of(k)] = k
        self._last: dict = {}
        self._running = False

    def _on_command(self, point, previous_info, message):
        key = self.cmd_points.get(point.io_address)
        if key is None or self._plant is None:
            return self.c104.ResponseState.FAILURE
        self._plant.write(key, float(point.value))
        return self.c104.ResponseState.SUCCESS

    def start(self) -> None:
        self.server.start()
        self._running = True
        log.info("IEC 104 server %s:%d", self.host, self.port)

    def stop(self) -> None:
        if self._running:
            self.server.stop()
            self._running = False

    def update(self, tags: dict, plant) -> None:
        self._plant = plant
        if plant is not None and not plant.comms:
            self.stop()
            return
        if not self._running:
            self.start()
        c104 = self.c104
        for key, val in tags.items():
            pt = self.points.get(key)
            if pt is None:
                continue
            v = bool(val >= 0.5) if key.endswith(".RUN") else float(val)
            if key in self._last and self._last[key] == v:
                continue
            pt.value = v
            if self.server.has_active_connections:
                pt.transmit(cause=c104.Cot.SPONTANEOUS)
            self._last[key] = v


def write_soe(plant: Plant, path: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for ev in plant.soe:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Sath GES simulyatori (sinov stendi)")
    ap.add_argument("--scenario", default="normal", choices=sorted(SCENARIOS))
    ap.add_argument("--modbus", default="", help="masalan 0.0.0.0:5020")
    ap.add_argument("--opcua", default="", help="masalan opc.tcp://0.0.0.0:4840/sath-sim/")
    ap.add_argument("--iec104", default="", help="masalan 0.0.0.0:2404 (c104 kutubxonasi kerak)")
    ap.add_argument("--dt", type=float, default=None, help="qadam, s (default stsenariy bo'yicha, 1 s)")
    ap.add_argument("--speed", type=float, default=1.0, help="tezlashtirish (10 = 10× tez)")
    ap.add_argument("--duration", type=float, default=None, help="soniya (modelda)")
    ap.add_argument("--record", default="", help="teglarni JSONL ga yozish")
    ap.add_argument("--replay", default="", help="yozib olingan JSONL ni qayta ijro etish")
    ap.add_argument("--soe", default="soe.jsonl")
    ap.add_argument("--print-gateway-config", action="store_true")
    ap.add_argument("--list", action="store_true", help="stsenariylar ro'yxati")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.list:
        for k, v in SCENARIOS.items():
            print(f"{k:16s} {v['desc']}")
        return
    if a.print_gateway_config:
        print(json.dumps(gateway_config(modbus=a.modbus or "127.0.0.1:5020", opcua=a.opcua or None, iec104=a.iec104 or None), indent=2, ensure_ascii=False))
        return
    servers: list = []
    if a.modbus:
        ms = ModbusServer(a.modbus)
        ms.start()
        servers.append(ms)
    if a.opcua:
        os_ = OpcUaServer(a.opcua)
        os_.start()
        servers.append(os_)
    if a.iec104:
        i104 = Iec104Server(a.iec104)
        i104.start()
        servers.append(i104)
    plant = Plant(default_plant())
    dt = a.dt if a.dt is not None else SCENARIOS[a.scenario].get("dt", 1.0)
    try:
        if a.replay:
            Replayer(a.replay, dt, a.speed).run(servers, plant)
        else:
            log.info("stsenariy %s: %s", a.scenario, SCENARIOS[a.scenario]["desc"])
            Runner(plant, a.scenario, dt, a.speed, a.record or None).run(servers, a.duration)
    except KeyboardInterrupt:
        pass
    finally:
        write_soe(plant, a.soe)
        for s in servers:
            s.stop()


if __name__ == "__main__":
    main()
