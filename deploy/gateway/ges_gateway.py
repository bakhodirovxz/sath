"""Sath gateway — SCADA tomonida ishlaydigan kichik skript: Modbus TCP / OPC UA / CSV / sinov
manbalaridan o'qib, Sath serverga HTTP orqali yuboradi (X-Ingest-Key).

Server tomonda hech qanday sanoat protokoli kutubxonasi kerak emas; bu skript SCADA tarmog'ida
(masalan dispetcher kompyuterida) ishlaydi va faqat HTTP chiqishi bo'lsa yetadi.

O'rnatish:  pip install requests pymodbus asyncua   (kerakli protokolga qarab)
Ishga tushirish:  python ges_gateway.py config.json
Windows xizmati sifatida: NSSM yoki Task Scheduler ("At startup").

config.json namunasi — gateway_config.example.json
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger("ges_gateway")


# ---------- Manbalar ----------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Source:
    """Manba: read() → [{key, value, quality?, src_ts?}]. Aloqa uzilganda har teg uchun BITTA
    quality=bad yozuv (takrorlanmaydi), qayta ulanganda haqiqiy qiymatlar davom etadi (E2)."""

    def __init__(self) -> None:
        self._bad_sent: set[str] = set()

    def read(self) -> list[dict]:
        raise NotImplementedError

    def tag_keys(self) -> list[str]:
        return []

    def read_safe(self) -> list[dict]:
        """read() xatosini ushlaydi: aloqa yo'q → har teg uchun bir marta quality=bad."""
        try:
            out = self.read()
        except Exception as e:  # noqa: BLE001 — manba xatosi siklni to'xtatmasin
            log.warning("%s: aloqa yo'q: %s", type(self).__name__, e)
            out = []
            for key in self.tag_keys():
                if key not in self._bad_sent:
                    self._bad_sent.add(key)
                    out.append({"key": key, "value": 0.0, "quality": "bad", "src_ts": now_iso()})
            return out
        for it in out:
            if it.get("quality") != "bad":
                self._bad_sent.discard(it["key"])
        return out

    def close(self) -> None:
        pass


class SimSource(Source):
    """Sinov: sinusoida + shovqin. tags: [{key, base, amplitude, period_s}]"""

    def __init__(self, cfg: dict):
        super().__init__()
        self.tags = cfg["tags"]
        self.t0 = time.time()

    def tag_keys(self) -> list[str]:
        return [t["key"] for t in self.tags]

    def read(self) -> list[dict]:
        t = time.time() - self.t0
        ts = now_iso()
        return [
            {
                "key": tag["key"],
                "value": round(
                    tag.get("base", 0)
                    + tag.get("amplitude", 1) * math.sin(2 * math.pi * t / tag.get("period_s", 600))
                    + random.gauss(0, tag.get("noise", 0.05)),
                    3,
                ),
                "quality": tag.get("quality", "good"),
                "src_ts": ts,
            }
            for tag in self.tags
        ]


class ModbusSource(Source):
    """Modbus TCP. tags: [{key, address, count?:1|2, type?: "int16"|"uint16"|"int32"|"float32", scale?:1, unit_id?:1, kind?: "holding"|"input"}]"""

    def __init__(self, cfg: dict):
        super().__init__()
        from pymodbus.client import ModbusTcpClient

        self.client = ModbusTcpClient(cfg["host"], port=cfg.get("port", 502))
        self.tags = cfg["tags"]
        self.client.connect()

    def tag_keys(self) -> list[str]:
        return [t["key"] for t in self.tags]

    def read(self) -> list[dict]:
        from pymodbus.client.mixin import ModbusClientMixin

        if not self.client.connected and not self.client.connect():
            raise ConnectionError("Modbus ulanmadi")
        out = []
        for tag in self.tags:
            typ = tag.get("type", "int16")
            count = 2 if typ in ("int32", "float32", "uint32") else 1
            fn = (
                self.client.read_input_registers
                if tag.get("kind") == "input"
                else self.client.read_holding_registers
            )
            ts = now_iso()  # o'qish payti — manbadagi vaqt (Modbus tamg'a bermaydi)
            try:
                rr = fn(tag["address"], count=count, slave=tag.get("unit_id", 1))
            except Exception as e:  # noqa: BLE001 — bitta teg xatosi qolganini to'xtatmasin
                rr = None
                log.warning("modbus %s: %s", tag["key"], e)
            if rr is None or rr.isError():
                if rr is not None:
                    log.warning("modbus %s: %s", tag["key"], rr)
                if tag["key"] not in self._bad_sent:
                    self._bad_sent.add(tag["key"])
                    out.append({"key": tag["key"], "value": 0.0, "quality": "bad", "src_ts": ts})
                continue
            dt = {
                "int16": ModbusClientMixin.DATATYPE.INT16,
                "uint16": ModbusClientMixin.DATATYPE.UINT16,
                "int32": ModbusClientMixin.DATATYPE.INT32,
                "uint32": ModbusClientMixin.DATATYPE.UINT32,
                "float32": ModbusClientMixin.DATATYPE.FLOAT32,
            }[typ]
            value = self.client.convert_from_registers(rr.registers, dt)
            out.append(
                {"key": tag["key"], "value": value * tag.get("scale", 1), "quality": "good", "src_ts": ts}
            )
        return out

    def write(self, tag: dict, value: float) -> None:
        """Buyruq (setpoint): holding registrga yozish (type/scale teg sozlamasidan)."""
        from pymodbus.client.mixin import ModbusClientMixin

        typ = tag.get("type", "int16")
        dt = {
            "int16": ModbusClientMixin.DATATYPE.INT16,
            "uint16": ModbusClientMixin.DATATYPE.UINT16,
            "int32": ModbusClientMixin.DATATYPE.INT32,
            "uint32": ModbusClientMixin.DATATYPE.UINT32,
            "float32": ModbusClientMixin.DATATYPE.FLOAT32,
        }[typ]
        raw = value / tag.get("scale", 1)
        regs = self.client.convert_to_registers(raw if typ == "float32" else int(round(raw)), dt)
        rr = self.client.write_registers(tag["address"], regs, slave=tag.get("unit_id", 1))
        if rr.isError():
            raise RuntimeError(str(rr))

    def close(self) -> None:
        self.client.close()


class OpcUaSource(Source):
    """OPC UA (sync klient). tags: [{key, node_id: "ns=2;i=1001", deadband?: 0}]
    mode: "poll" (default) — har siklda read_data_value; "subscribe" — MonitoredItems obunasi
    (publishing_interval_ms, deadband — absolyut), o'zgarish poll davridan tez keladi, tarmoq yuki
    kam; qayta ulanish: obuna tiklanadi, uzilish davrida quality=bad (read_safe orqali) (E3)."""

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.mode = cfg.get("mode", "poll")
        self.publishing_ms = float(cfg.get("publishing_interval_ms", 500))
        self.client = None
        self.nodes: list[tuple[str, object]] = []
        self.sub = None
        self._latest: dict[str, object] = {}  # key → DataValue (obuna)
        self._changed: set[str] = set()
        self._lock = threading.Lock()
        self._connect()

    def _connect(self) -> None:
        from asyncua.sync import Client

        cfg = self.cfg
        self.client = Client(cfg["url"])
        if cfg.get("username"):
            self.client.set_user(cfg["username"])
            self.client.set_password(cfg.get("password", ""))
        self.client.connect()
        self.nodes = [(tag["key"], self.client.get_node(tag["node_id"])) for tag in cfg["tags"]]
        if self.mode == "subscribe":
            self._subscribe()

    def _subscribe(self) -> None:
        from asyncua import ua

        src = self

        class Handler:
            def datachange_notification(self, node, val, data):
                key = next((k for k, n in src.nodes if n.nodeid == node.nodeid), None)
                if key is None:
                    return
                dv = getattr(getattr(data, "monitored_item", None), "Value", None)
                with src._lock:
                    src._latest[key] = dv if dv is not None else val
                    src._changed.add(key)

        self.sub = self.client.create_subscription(self.publishing_ms, Handler())
        plain, filtered = [], []
        for tag, (_key, node) in zip(self.cfg["tags"], self.nodes, strict=False):
            db = float(tag.get("deadband", 0) or 0)
            (filtered if db > 0 else plain).append((node, db))
        if plain:
            self.sub.subscribe_data_change([n for n, _ in plain], sampling_interval=self.publishing_ms)
        for node, db in filtered:
            flt = ua.DataChangeFilter(
                Trigger=ua.DataChangeTrigger.StatusValue,
                DeadbandType=ua.DeadbandType.Absolute,
                DeadbandValue=db,
            )
            req = ua.MonitoredItemCreateRequest(
                ItemToMonitor=ua.ReadValueId(NodeId=node.nodeid, AttributeId=ua.AttributeIds.Value),
                MonitoringMode=ua.MonitoringMode.Reporting,
                RequestedParameters=ua.MonitoringParameters(
                    ClientHandle=abs(hash(node.nodeid.to_string())) % 2_000_000_000,
                    SamplingInterval=self.publishing_ms,
                    Filter=flt,
                    QueueSize=1,
                    DiscardOldest=True,
                ),
            )
            self.sub.create_monitored_items([req])
        log.info("opcua obuna: %d teg, %.0f ms", len(self.nodes), self.publishing_ms)

    def _reconnect(self) -> None:
        log.warning("opcua: qayta ulanish %s", self.cfg["url"])
        self.close()
        self._latest.clear()
        self._connect()

    def tag_keys(self) -> list[str]:
        return [k for k, _ in self.nodes]

    def read(self) -> list[dict]:
        if self.mode == "subscribe":
            return self._read_subscribed()
        out = []
        for key, node in self.nodes:
            try:
                dv = node.read_data_value()  # StatusCode + SourceTimestamp (E2)
                out.append(opcua_item(key, dv))
            except Exception as e:  # noqa: BLE001 — bitta teg xatosi qolganini to'xtatmasin
                log.warning("opcua %s: %s", key, e)
                if key not in self._bad_sent:
                    self._bad_sent.add(key)
                    out.append({"key": key, "value": 0.0, "quality": "bad", "src_ts": now_iso()})
        return out

    def _read_subscribed(self) -> list[dict]:
        # Aloqa tekshiruvi: sessiya o'lgan bo'lsa xato → read_safe bad yozadi, keyin qayta ulanamiz
        try:
            self.client.get_node("i=2258").read_value()  # Server_ServerStatus_CurrentTime
        except Exception as e:
            try:
                self._reconnect()
            except Exception as e2:  # noqa: BLE001
                raise ConnectionError(f"opcua aloqa yo'q: {e2}") from e
            raise ConnectionError(f"opcua aloqa uzildi, qayta ulandi: {e}") from e
        with self._lock:
            changed = [(k, self._latest[k]) for k in self._changed if k in self._latest]
            self._changed.clear()
        out = []
        for key, dv in changed:
            if hasattr(dv, "StatusCode"):
                out.append(opcua_item(key, dv))
            else:
                try:
                    out.append({"key": key, "value": float(dv), "quality": "good", "src_ts": now_iso()})
                except (TypeError, ValueError):
                    out.append({"key": key, "value": 0.0, "quality": "bad", "src_ts": now_iso()})
        return out

    def write(self, tag: dict, value: float) -> None:
        node = self.client.get_node(tag["node_id"])
        node.write_value(float(value))

    def close(self) -> None:
        try:
            if self.sub is not None:
                self.sub.delete()
        except Exception:  # noqa: BLE001
            pass
        self.sub = None
        try:
            if self.client is not None:
                self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def opcua_quality(status_code) -> str:
    """OPC UA StatusCode → Sath sifati: Good* → good, Uncertain* → uncertain, Bad* → bad."""
    try:
        v = int(status_code.value)
    except (AttributeError, TypeError, ValueError):
        return "good"
    sev = (v >> 30) & 0x3  # yuqori 2 bit: 00 Good, 01 Uncertain, 10 Bad
    return {0: "good", 1: "uncertain", 2: "bad", 3: "bad"}[sev]


def opcua_item(key: str, dv) -> dict:
    """DataValue → o'lchov: qiymat (bad bo'lsa 0), sifat, SourceTimestamp (bo'lmasa ServerTimestamp)."""
    q = opcua_quality(getattr(dv, "StatusCode", None))
    try:
        value = float(dv.Value.Value) if q != "bad" else 0.0
    except (TypeError, ValueError):
        value, q = 0.0, "bad"
    if not math.isfinite(value):
        value, q = 0.0, "bad"
    ts = getattr(dv, "SourceTimestamp", None) or getattr(dv, "ServerTimestamp", None)
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {"key": key, "value": value, "quality": q, "src_ts": (ts or datetime.now(timezone.utc)).isoformat()}


class CsvTailSource(Source):
    """SCADA eksport qiladigan CSV faylning yangi qatorlarini o'qiydi: ts,key,value[,quality]"""

    def __init__(self, cfg: dict):
        super().__init__()
        self.path = cfg["path"]
        self.pos = 0

    def read(self) -> list[dict]:
        out = []
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            fh.seek(self.pos)
            for line in fh:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        it = {"ts": parts[0], "src_ts": parts[0], "key": parts[1], "value": float(parts[2])}
                        if len(parts) >= 4 and parts[3]:
                            it["quality"] = parts[3].lower()
                        out.append(it)
                    except ValueError:
                        pass
            self.pos = fh.tell()
        return out


class Iec104Source(Source):
    """IEC 60870-5-104 klienti (`c104`, lib60870 ustida; GPLv3 — gateway alohida jarayon) (E5).

    cfg: {host, port: 2404, common_address: 1, interrogation_s: 300, originator: 0,
          tags: [{key, ioa, type: "M_ME_NC_1" | "M_ME_NB_1" | "M_ME_NA_1" | "M_SP_NA_1" | "M_DP_NA_1" |
                  "M_ME_TF_1" | "M_SP_TB_1" | "M_DP_TB_1" | "M_IT_NA_1", scale?}],
          commands: [{key, ioa, type: "C_SE_NC_1" | "C_SE_NB_1" | "C_SC_NA_1"}]}   — default bo'sh (o'chiq)
    Ulanishda va har `interrogation_s` da umumiy so'rov (C_IC_NA_1); spontan xabarlar obuna kabi keladi.
    Sifat (QDS): IV → bad, NT/BL/OV → uncertain, SB → substituted. Vaqt tamg'ali turlar (…_TB_1/_TF_1)
    `recorded_at` (ms) ni `src_ts` sifatida beradi; diskret vaqt tamg'ali hodisalar (SP/DP _TB) SOE
    ro'yxatiga ham yoziladi (`self.soe`, D3 da serverga). Aloqa uzilsa read() ConnectionError → bad."""

    def __init__(self, cfg: dict):
        super().__init__()
        import c104

        self.c104 = c104
        self.cfg = cfg
        self.ca = int(cfg.get("common_address", 1))
        self.client = c104.Client(tick_rate_ms=int(cfg.get("tick_ms", 100)))
        if cfg.get("originator") is not None:
            self.client.originator_address = int(cfg["originator"])
        self.conn = self.client.add_connection(ip=cfg["host"], port=int(cfg.get("port", 2404)), init=c104.Init.ALL)
        self.station = self.conn.add_station(common_address=self.ca)
        self._lock = threading.Lock()
        self._latest: dict[str, dict] = {}
        self._changed: set[str] = set()
        self.soe: list[dict] = []
        self.keys_by_ioa: dict[int, dict] = {}
        # c104 callback imzosini tekshiradi — `from __future__ import annotations` satrli
        # annotatsiya beradi, shuning uchun haqiqiy turlar bilan qayta belgilaymiz
        cb = self._on_receive
        cb.__func__.__annotations__ = {
            "point": c104.Point,
            "previous_info": c104.Information,
            "message": c104.IncomingMessage,
            "return": c104.ResponseState,
        }
        for tag in cfg["tags"]:
            typ = getattr(c104.Type, tag.get("type", "M_ME_NC_1"))
            pt = self.station.add_point(io_address=int(tag["ioa"]), type=typ)
            self.keys_by_ioa[int(tag["ioa"])] = tag
            pt.on_receive(cb)
        self.cmd_points: dict[str, object] = {}
        for c in cfg.get("commands", []):
            typ = getattr(c104.Type, c.get("type", "C_SE_NC_1"))
            self.cmd_points[c["key"]] = (self.station.add_point(io_address=int(c["ioa"]), type=typ), c)
        self.interrogation_s = float(cfg.get("interrogation_s", 300))
        self._last_gi = time.time()
        self.client.start()

    def _on_receive(self, point, previous_info, message):  # noqa: ANN001 — c104 imzosi
        c104 = self.c104
        tag = self.keys_by_ioa.get(point.io_address)
        if tag is None:
            return c104.ResponseState.SUCCESS
        q = point.quality
        if c104.Quality.Invalid in q:
            quality = "bad"
        elif c104.Quality.Substituted in q:
            quality = "substituted"
        elif any(b in q for b in (c104.Quality.NonTopical, c104.Quality.Blocked, c104.Quality.Overflow)):
            quality = "uncertain"
        else:
            quality = "good"
        v = point.value
        try:
            value = float(v) if not isinstance(v, bool) else (1.0 if v else 0.0)
        except (TypeError, ValueError):
            value = float(int(v)) if hasattr(v, "__int__") else 0.0
        value *= float(tag.get("scale", 1))
        ts = point.recorded_at
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        item = {"key": tag["key"], "value": value, "quality": quality, "src_ts": (ts or datetime.now(timezone.utc)).isoformat()}
        with self._lock:
            self._latest[tag["key"]] = item
            self._changed.add(tag["key"])
            if ts is not None and str(point.type).split(".")[-1] in ("M_SP_TB_1", "M_DP_TB_1", "M_SP_TA_1", "M_DP_TA_1"):
                self.soe.append({"ts": ts.isoformat(timespec="milliseconds"), "point": tag["key"], "state": v if isinstance(v, bool) else str(v), "quality": quality, "cot": str(message.cot).split(".")[-1]})
        return c104.ResponseState.SUCCESS

    def tag_keys(self) -> list[str]:
        return [t["key"] for t in self.cfg["tags"]]

    def read(self) -> list[dict]:
        if not self.conn.is_connected:
            raise ConnectionError(f"IEC 104 aloqa yo'q: {self.conn.state}")
        if time.time() - self._last_gi > self.interrogation_s:
            self._last_gi = time.time()
            try:
                self.conn.interrogation(common_address=self.ca, wait_for_response=False)
            except Exception as e:  # noqa: BLE001
                log.warning("iec104 interrogation: %s", e)
        with self._lock:
            out = [self._latest[k] for k in self._changed if k in self._latest]
            self._changed.clear()
        return out

    def write(self, tag: dict, value: float) -> None:
        """Setpoint (C_SE_NC_1 / C_SE_NB_1) yoki bitta buyruq (C_SC_NA_1) — faqat `commands` da
        e'lon qilingan nuqtalar; muvaffaqiyatsiz ACTIVATION_CON → xato (server B qoidalari ustida)."""
        entry = self.cmd_points.get(tag["key"])
        if entry is None:
            raise RuntimeError(f"IEC 104: {tag['key']} uchun buyruq nuqtasi konfiguratsiyada yo'q (commands)")
        pt, c = entry
        typ = c.get("type", "C_SE_NC_1")
        pt.value = bool(value) if typ == "C_SC_NA_1" else (int(round(value)) if typ == "C_SE_NB_1" else float(value))
        ok = pt.transmit(cause=self.c104.Cot.ACTIVATION)
        if not ok:
            raise RuntimeError(f"IEC 104: {tag['key']} buyrug'i tasdiqlanmadi (ACTIVATION_CON salbiy)")

    def close(self) -> None:
        try:
            self.client.stop()
        except Exception:  # noqa: BLE001
            pass


SOURCES = {"sim": SimSource, "modbus": ModbusSource, "opcua": OpcUaSource, "csv": CsvTailSource, "iec104": Iec104Source}


# ---------- Yuborish ----------


class Commander:
    """Supervisory control: serverdagi kutayotgan buyruqlarni olib, manbaga yozadi (modbus/opcua/sim)
    va natijani qaytaradi. Teg konfiguratsiyasi kalit bo'yicha topiladi (writable teglar)."""

    def __init__(self, cfg: dict, sources: list, source_cfgs: list[dict]):
        base = cfg["server"].rstrip("/")
        self.claim_url = base + f"/api/projects/{cfg['project_id']}/commands/claim"
        self.ack_url = base + "/api/commands/{id}/ack"
        self.readback_url = base + "/api/commands/{id}/readback"
        if not cfg.get("command_key"):
            raise ValueError(
                "commands=true uchun command_key (Monitoring → Buyruq kaliti) yoki "
                "GES_GATEWAY_COMMAND_KEY muhit o'zgaruvchisi kerak — ingest kaliti buyruq kanaliga yaramaydi"
            )
        self.headers = {"X-Command-Key": cfg["command_key"]}
        self.tags: dict[str, tuple[object, dict]] = {}
        for src, scfg in zip(sources, source_cfgs, strict=False):
            for tag in scfg.get("tags", []):
                self.tags[tag["key"]] = (src, tag)

    def run_once(self) -> None:
        try:
            cmds = requests.post(self.claim_url, headers=self.headers, timeout=10).json()
        except (requests.RequestException, ValueError) as e:
            log.warning("buyruqlarni olib bo'lmadi: %s", e)
            return
        for c in cmds:
            status, result = "acked", ""
            src_tag = self.tags.get(c["key"])
            try:
                if src_tag is None:
                    raise RuntimeError("gateway konfiguratsiyasida bunday teg yo'q")
                src, tag = src_tag
                if hasattr(src, "write"):
                    src.write(tag, float(c["value"]))
                elif isinstance(src, SimSource):
                    tag["base"] = float(c["value"])  # simulyatorda qiymatni o'rnatamiz
                else:
                    raise RuntimeError(f"{type(src).__name__} yozishni qo'llamaydi")
                result = f"{c['key']} = {c['value']}"
                log.info("buyruq #%s bajarildi: %s", c["id"], result)
            except Exception as e:  # noqa: BLE001 — natija serverga qaytariladi
                status, result = "failed", str(e)[:400]
                log.warning("buyruq #%s xato: %s", c["id"], e)
            try:
                requests.post(
                    self.ack_url.format(id=c["id"]),
                    json={"status": status, "result": result},
                    headers=self.headers,
                    timeout=10,
                )
            except requests.RequestException as e:
                log.warning("buyruq #%s natijasi yuborilmadi: %s", c["id"], e)
            if status == "acked":
                self._readback(c, src_tag)

    def _readback(self, c: dict, src_tag) -> None:
        """Yozgandan keyin o'sha tegni qayta o'qib serverga yuboradi — server kutilgan qiymat bilan
        solishtiradi (mismatch bo'lsa alarm/bildirishnoma). O'qib bo'lmasa — o'tkazib yuboriladi."""
        try:
            src, tag = src_tag
            if isinstance(src, SimSource):
                value = float(c["value"])  # simulyatorda o'rnatilgan qiymat
            else:
                rows = [r for r in src.read() if r.get("key") == c["key"]]
                if not rows:
                    log.warning("buyruq #%s readback: teg o'qilmadi", c["id"])
                    return
                value = float(rows[0]["value"])
            requests.post(
                self.readback_url.format(id=c["id"]),
                json={"value": value, "ts": datetime.now(timezone.utc).isoformat()},
                headers=self.headers,
                timeout=10,
            )
        except Exception as e:  # noqa: BLE001 — readback ixtiyoriy, asosiy siklni to'xtatmasin
            log.warning("buyruq #%s readback yuborilmadi: %s", c["id"], e)


class Spool:
    """Diskdagi store-and-forward navbati (SQLite): restartda yo'qolmaydi (E1).

    Qatorlar: (id, ts, payload JSON, attempts). Yuborilgach o'chiriladi. To'lganda (`max_rows`)
    siyosat: `drop_oldest` (eng eskisi o'chiriladi, ogohlantirish) yoki `stop` (yangi yozuv qabul
    qilinmaydi, ogohlantirish) — konfiguratsiyada."""

    def __init__(self, path: str, max_rows: int = 1_000_000, overflow: str = "drop_oldest"):
        self.path = path
        self.max_rows = int(max_rows)
        self.overflow = overflow
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS spool (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, "
            "payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)"
        )
        self.conn.commit()
        self.dropped = 0

    def add(self, items: list[dict]) -> int:
        """Qaytaradi: qo'shilgan qatorlar soni (stop siyosatida to'lganda 0)."""
        if not items:
            return 0
        with self._lock:
            n = self.size()
            if self.overflow == "stop" and n + len(items) > self.max_rows:
                log.warning("spool to'lgan (%d) — yangi o'lchovlar qabul qilinmayapti (stop)", n)
                return 0
            self.conn.executemany(
                "INSERT INTO spool (ts, payload) VALUES (?, ?)",
                [(it.get("ts") or now_iso(), json.dumps(it, separators=(",", ":"))) for it in items],
            )
            excess = n + len(items) - self.max_rows
            if excess > 0:  # drop_oldest
                self.conn.execute(
                    "DELETE FROM spool WHERE id IN (SELECT id FROM spool ORDER BY id LIMIT ?)", (excess,)
                )
                self.dropped += excess
                log.warning("spool to'lgan — eng eski %d yozuv o'chirildi (jami %d)", excess, self.dropped)
            self.conn.commit()
            return len(items)

    def batch(self, limit: int = 5000) -> tuple[list[int], list[dict]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, payload FROM spool ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows], [json.loads(r[1]) for r in rows]

    def ack(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self.conn.executemany("DELETE FROM spool WHERE id = ?", [(i,) for i in ids])
            self.conn.commit()

    def fail(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self.conn.executemany("UPDATE spool SET attempts = attempts + 1 WHERE id = ?", [(i,) for i in ids])
            self.conn.commit()

    def size(self) -> int:
        return int(self.conn.execute("SELECT count(*) FROM spool").fetchone()[0])

    def oldest_age_s(self) -> float:
        row = self.conn.execute("SELECT ts FROM spool ORDER BY id LIMIT 1").fetchone()
        if not row:
            return 0.0
        try:
            t = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return max((datetime.now(timezone.utc) - t).total_seconds(), 0.0)
        except ValueError:
            return 0.0

    def close(self) -> None:
        self.conn.close()


class Pusher:
    """O'lchovlarni spool orqali serverga yuboradi: har siklda eng eski partiyalar, xatoda eksponensial
    kechikish (2…300 s). Diagnostika teglari (`diag: true`): GW.spool_rows, GW.spool_oldest_age_s,
    GW.spool_dropped, GW.clock_offset_s (server Date sarlavhasi bilan farq; NTP tekshiruvi o'rnini bosadi)."""

    def __init__(self, cfg: dict):
        self.url = cfg["server"].rstrip("/") + f"/api/projects/{cfg['project_id']}/readings"
        self.soe_url = cfg["server"].rstrip("/") + f"/api/projects/{cfg['project_id']}/soe"
        self.headers = {"X-Ingest-Key": cfg["ingest_key"]}
        self.spool = Spool(
            cfg.get("spool_path", "gateway_spool.db"),
            cfg.get("spool_max_rows", 1_000_000),
            cfg.get("spool_overflow", "drop_oldest"),
        )
        self.batch_size = int(cfg.get("batch_size", 5000))
        self.max_batches_per_cycle = int(cfg.get("max_batches_per_cycle", 10))
        self.diag = bool(cfg.get("diag", False))
        self.diag_prefix = cfg.get("diag_prefix", "GW")
        self.clock_warn_s = float(cfg.get("clock_warn_s", 5.0))
        self.backoff_s = 0.0
        self.next_try = 0.0
        self.clock_offset_s: float | None = None

    @staticmethod
    def sanitize(items: list[dict]) -> list[dict]:
        now = now_iso()
        for it in items:
            it.setdefault("ts", now)
            it.setdefault("src_ts", it["ts"])
            # Server chekli bo'lmagan qiymatga butun paketni 422 bilan rad etadi — o'qish xatosi
            # (NaN/inf registr) sifat bayrog'i bilan yuboriladi, qiymat 0 (A3)
            try:
                v = float(it.get("value"))
            except (TypeError, ValueError):
                v = math.nan
            if not math.isfinite(v):
                it["value"] = 0.0
                it["quality"] = "bad"
        return items

    def diag_items(self) -> list[dict]:
        p = self.diag_prefix
        out = [
            {"key": f"{p}.spool_rows", "value": float(self.spool.size())},
            {"key": f"{p}.spool_oldest_age_s", "value": round(self.spool.oldest_age_s(), 1)},
            {"key": f"{p}.spool_dropped", "value": float(self.spool.dropped)},
        ]
        if self.clock_offset_s is not None:
            out.append({"key": f"{p}.clock_offset_s", "value": round(self.clock_offset_s, 2)})
        return out

    def push(self, items: list[dict], soe: list[dict] | None = None) -> None:
        items = self.sanitize(items)
        if self.diag:
            items = items + self.sanitize(self.diag_items())
        # SOE hodisalari ham spool orqali (uzilishda yo'qolmaydi), `_soe` belgisi bilan ajratiladi
        self.spool.add(items + [{"_soe": True, **e} for e in (soe or [])])
        self.flush()

    def flush(self) -> None:
        if time.time() < self.next_try:
            return
        for _ in range(self.max_batches_per_cycle):
            ids, batch = self.spool.batch(self.batch_size)
            if not ids:
                return
            readings = [b for b in batch if not b.get("_soe")]
            soe = [{k: v for k, v in b.items() if k != "_soe"} for b in batch if b.get("_soe")]
            try:
                if soe:
                    rs = requests.post(self.soe_url, json=soe, headers=self.headers, timeout=15)
                    if rs.status_code == 422:
                        log.error("server 422 (SOE): partiya (%d) tashlandi: %s", len(soe), rs.text[:300])
                    else:
                        rs.raise_for_status()
                        log.info("SOE yuborildi: %d (qabul %d)", len(soe), rs.json().get("accepted", 0))
                if not readings:
                    self.spool.ack(ids)
                    self.backoff_s = 0.0
                    continue
                r = requests.post(self.url, json=readings, headers=self.headers, timeout=15)
                self._check_clock(r)
                if r.status_code == 422:
                    # Validatsiya xatosi — partiya hech qachon qabul qilinmaydi: o'chirib, loglaymiz
                    log.error("server 422: partiya (%d) tashlandi: %s", len(readings), r.text[:300])
                    self.spool.ack(ids)
                    continue
                r.raise_for_status()
                resp = r.json()
                if resp.get("unknown"):
                    log.warning("serverda noma'lum kalitlar: %s", resp["unknown"][:10])
                if resp.get("rejected"):
                    log.warning("server rad etdi: %s", resp["rejected"][:10])
                log.info("yuborildi: %d (qabul %d, spoolda %d)", len(readings), resp.get("accepted", 0), self.spool.size() - len(ids))
                self.spool.ack(ids)
                self.backoff_s = 0.0
            except requests.RequestException as e:
                self.spool.fail(ids)
                self.backoff_s = min(max(self.backoff_s * 2, 2.0), 300.0)
                self.next_try = time.time() + self.backoff_s
                log.warning(
                    "yuborib bo'lmadi (spoolda %d, %.0f s dan keyin qayta): %s",
                    self.spool.size(),
                    self.backoff_s,
                    e,
                )
                return

    def _check_clock(self, r) -> None:
        """Server `Date` sarlavhasi (1 s aniqlik) bilan lokal soat farqi — NTP buzilganini ko'rsatadi."""
        date = r.headers.get("Date") if hasattr(r, "headers") else None
        if not date:
            return
        try:
            server = parsedate_to_datetime(date)
            if server.tzinfo is None:
                server = server.replace(tzinfo=timezone.utc)
            self.clock_offset_s = (datetime.now(timezone.utc) - server).total_seconds()
            if abs(self.clock_offset_s) > self.clock_warn_s:
                log.warning(
                    "gateway soati server bilan %.0f s farq qiladi — NTP ni tekshiring", self.clock_offset_s
                )
        except (TypeError, ValueError):
            pass


def load_config(config_path: str | None) -> dict:
    """Konfiguratsiya: JSON fayl (ixtiyoriy) + muhit o'zgaruvchilari (ustun): GES_GATEWAY_SERVER,
    GES_GATEWAY_PROJECT_ID, GES_GATEWAY_INGEST_KEY, GES_GATEWAY_COMMAND_KEY, GES_GATEWAY_COMMANDS.
    Kalitlar faylda ochiq matnda turmasligi uchun muhitdan berish tavsiya etiladi."""
    cfg: dict = {}
    if config_path:
        with open(config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    env = os.environ
    for key, name in (
        ("server", "GES_GATEWAY_SERVER"),
        ("ingest_key", "GES_GATEWAY_INGEST_KEY"),
        ("command_key", "GES_GATEWAY_COMMAND_KEY"),
    ):
        if env.get(name):
            cfg[key] = env[name]
    if env.get("GES_GATEWAY_PROJECT_ID"):
        cfg["project_id"] = int(env["GES_GATEWAY_PROJECT_ID"])
    if env.get("GES_GATEWAY_COMMANDS"):
        cfg["commands"] = env["GES_GATEWAY_COMMANDS"].lower() in ("1", "true", "yes")
    # Buyruq kanali default O'CHIQ: minimal konfiguratsiya bilan ikki tomonlama boshqaruv ochilmasin (B3)
    cfg.setdefault("commands", False)
    for req in ("server", "project_id", "ingest_key"):
        if not cfg.get(req):
            raise ValueError(f"gateway konfiguratsiyasi: {req} kerak (fayl yoki muhit o'zgaruvchisi)")
    return cfg


def build_commander(cfg: dict, sources: list) -> Commander | None:
    """commands=true va command_key bo'lsa Commander, aks holda None (faqat o'lchov)."""
    if not cfg.get("commands"):
        return None
    return Commander(cfg, sources, cfg["sources"])


def main(config_path: str | None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(config_path)
    pusher = Pusher(cfg)
    sources = [SOURCES[s["type"]](s) for s in cfg["sources"]]
    commander = build_commander(cfg, sources)
    if commander is None:
        log.info("buyruq kanali o'chiq (commands=false) — faqat o'lchov yuboriladi")
    interval = cfg.get("interval_s", 10)
    log.info("gateway: %d manba, har %ss → %s", len(sources), interval, pusher.url)
    try:
        while True:
            items, soe = [], []
            for src in sources:
                items.extend(src.read_safe())
                buf = getattr(src, "soe", None)
                if buf:  # vaqt tamg'ali diskret hodisalar (IEC 104 M_SP_TB_1 …) → SOE
                    soe.extend({**e, "source": s_type} for e, s_type in ((x, src.__class__.__name__.replace("Source", "").lower()) for x in buf))
                    buf.clear()
            pusher.push(items, soe)
            if commander is not None:
                commander.run_once()  # dispetcher buyruqlari (setpoint) → SCADA
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        for src in sources:
            src.close()
        pusher.spool.close()


def browse_opcua(url: str, out_csv: str, depth: int = 4, username: str = "", password: str = "") -> int:
    """OPC UA serverdagi o'zgaruvchilarni (Variable node lar) topib, Sath «CSV import» formatida yozadi:
    key;name;kind;unit;protocol;address;element;low;high — keyin webda Monitoring → CSV import (element
    ustunini to'ldirib) yoki gateway_config tags ga ko'chiriladi. kind nomdan taxmin qilinadi."""
    from asyncua import ua
    from asyncua.sync import Client

    client = Client(url)
    if username:
        client.set_user(username)
        client.set_password(password)
    client.connect()
    rows = []
    kinds = (("position", ("pos", "open", "ochil", "gate", "darvoza", "zatvor")), ("level", ("level", "sath", "lvl")),
             ("flow", ("flow", "sarf", "q_", "discharge")), ("pressure", ("press", "bosim", "bar")),
             ("temperature", ("temp", "harorat", "°c")), ("vibration", ("vib", "tebran")),
             ("status", ("run", "state", "holat", "status")), ("power", ("power", "quvvat", "mw")))  # fmt: skip

    def guess(name: str) -> str:
        n = name.lower()
        for kind, hints in kinds:
            if any(h in n for h in hints) or (kind == "power" and n.endswith("_p")):
                return kind
        return "value"

    def walk(node, path: str, level: int) -> None:
        if level > depth:
            return
        for ch in node.get_children():
            try:
                cls = ch.read_node_class()
                name = ch.read_browse_name().Name
            except Exception:  # noqa: BLE001
                continue
            p = f"{path}/{name}" if path else name
            if cls == ua.NodeClass.Variable:
                key = "".join(c if c.isalnum() or c in "._-" else "." for c in p)[:64]
                rows.append((key, name, guess(name), "", "opcua", ch.nodeid.to_string(), "", "", ""))
            elif cls == ua.NodeClass.Object and name not in ("Server", "Aliases"):
                walk(ch, p, level + 1)

    try:
        walk(client.get_objects_node(), "", 0)
    finally:
        client.disconnect()
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        fh.write("key;name;kind;unit;protocol;address;element;low;high\n")
        for r in rows:
            fh.write(";".join(f'"{x}"' if ";" in str(x) else str(x) for x in r) + "\n")
    log.info("OPC UA browse: %d o'zgaruvchi → %s", len(rows), out_csv)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "browse":
        # python ges_gateway.py browse opc.tcp://host:4840 tags.csv [chuqurlik] [user] [parol]
        logging.basicConfig(level=logging.INFO)
        n = browse_opcua(
            sys.argv[2],
            sys.argv[3] if len(sys.argv) > 3 else "tags.csv",
            int(sys.argv[4]) if len(sys.argv) > 4 else 4,
            sys.argv[5] if len(sys.argv) > 5 else "",
            sys.argv[6] if len(sys.argv) > 6 else "",
        )
        print(f"{n} teg topildi")
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else (None if os.environ.get("GES_GATEWAY_SERVER") else "config.json"))
