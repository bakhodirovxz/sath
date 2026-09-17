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
import random
import sys
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger("ges_gateway")


# ---------- Manbalar ----------


class Source:
    def read(self) -> list[dict]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SimSource(Source):
    """Sinov: sinusoida + shovqin. tags: [{key, base, amplitude, period_s}]"""

    def __init__(self, cfg: dict):
        self.tags = cfg["tags"]
        self.t0 = time.time()

    def read(self) -> list[dict]:
        t = time.time() - self.t0
        return [
            {
                "key": tag["key"],
                "value": round(
                    tag.get("base", 0)
                    + tag.get("amplitude", 1) * math.sin(2 * math.pi * t / tag.get("period_s", 600))
                    + random.gauss(0, tag.get("noise", 0.05)),
                    3,
                ),
            }
            for tag in self.tags
        ]


class ModbusSource(Source):
    """Modbus TCP. tags: [{key, address, count?:1|2, type?: "int16"|"uint16"|"int32"|"float32", scale?:1, unit_id?:1, kind?: "holding"|"input"}]"""

    def __init__(self, cfg: dict):
        from pymodbus.client import ModbusTcpClient

        self.client = ModbusTcpClient(cfg["host"], port=cfg.get("port", 502))
        self.tags = cfg["tags"]
        self.client.connect()

    def read(self) -> list[dict]:
        from pymodbus.client.mixin import ModbusClientMixin

        out = []
        for tag in self.tags:
            typ = tag.get("type", "int16")
            count = 2 if typ in ("int32", "float32", "uint32") else 1
            fn = (
                self.client.read_input_registers
                if tag.get("kind") == "input"
                else self.client.read_holding_registers
            )
            rr = fn(tag["address"], count=count, slave=tag.get("unit_id", 1))
            if rr.isError():
                log.warning("modbus %s: %s", tag["key"], rr)
                continue
            dt = {
                "int16": ModbusClientMixin.DATATYPE.INT16,
                "uint16": ModbusClientMixin.DATATYPE.UINT16,
                "int32": ModbusClientMixin.DATATYPE.INT32,
                "uint32": ModbusClientMixin.DATATYPE.UINT32,
                "float32": ModbusClientMixin.DATATYPE.FLOAT32,
            }[typ]
            value = self.client.convert_from_registers(rr.registers, dt)
            out.append({"key": tag["key"], "value": value * tag.get("scale", 1)})
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
    """OPC UA (sync klient). tags: [{key, node_id: "ns=2;i=1001"}]"""

    def __init__(self, cfg: dict):
        from asyncua.sync import Client

        self.client = Client(cfg["url"])
        if cfg.get("username"):
            self.client.set_user(cfg["username"])
            self.client.set_password(cfg.get("password", ""))
        self.client.connect()
        self.nodes = [(tag["key"], self.client.get_node(tag["node_id"])) for tag in cfg["tags"]]

    def read(self) -> list[dict]:
        out = []
        for key, node in self.nodes:
            try:
                out.append({"key": key, "value": float(node.read_value())})
            except Exception as e:  # noqa: BLE001 — bitta teg xatosi qolganini to'xtatmasin
                log.warning("opcua %s: %s", key, e)
        return out

    def write(self, tag: dict, value: float) -> None:
        node = self.client.get_node(tag["node_id"])
        node.write_value(float(value))

    def close(self) -> None:
        self.client.disconnect()


class CsvTailSource(Source):
    """SCADA eksport qiladigan CSV faylning yangi qatorlarini o'qiydi: ts,key,value"""

    def __init__(self, cfg: dict):
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
                        out.append({"ts": parts[0], "key": parts[1], "value": float(parts[2])})
                    except ValueError:
                        pass
            self.pos = fh.tell()
        return out


SOURCES = {"sim": SimSource, "modbus": ModbusSource, "opcua": OpcUaSource, "csv": CsvTailSource}


# ---------- Yuborish ----------


class Commander:
    """Supervisory control: serverdagi kutayotgan buyruqlarni olib, manbaga yozadi (modbus/opcua/sim)
    va natijani qaytaradi. Teg konfiguratsiyasi kalit bo'yicha topiladi (writable teglar)."""

    def __init__(self, cfg: dict, sources: list, source_cfgs: list[dict]):
        base = cfg["server"].rstrip("/")
        self.pending_url = base + f"/api/projects/{cfg['project_id']}/commands/pending"
        self.ack_url = base + "/api/commands/{id}/ack"
        self.headers = {"X-Ingest-Key": cfg["ingest_key"]}
        self.tags: dict[str, tuple[object, dict]] = {}
        for src, scfg in zip(sources, source_cfgs, strict=False):
            for tag in scfg.get("tags", []):
                self.tags[tag["key"]] = (src, tag)

    def run_once(self) -> None:
        try:
            cmds = requests.get(self.pending_url, headers=self.headers, timeout=10).json()
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


class Pusher:
    def __init__(self, cfg: dict):
        self.url = cfg["server"].rstrip("/") + f"/api/projects/{cfg['project_id']}/readings"
        self.headers = {"X-Ingest-Key": cfg["ingest_key"]}
        self.buffer: list[dict] = []
        self.max_buffer = cfg.get("max_buffer", 50000)  # tarmoq uzilganda saqlab turish

    def push(self, items: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for it in items:
            it.setdefault("ts", now)
        self.buffer.extend(items)
        self.buffer = self.buffer[-self.max_buffer :]
        if not self.buffer:
            return
        try:
            r = requests.post(self.url, json=self.buffer, headers=self.headers, timeout=15)
            r.raise_for_status()
            resp = r.json()
            if resp.get("unknown"):
                log.warning("serverda noma'lum kalitlar: %s", resp["unknown"][:10])
            log.info("yuborildi: %d (qabul %d)", len(self.buffer), resp.get("accepted", 0))
            self.buffer.clear()
        except requests.RequestException as e:
            log.warning("yuborib bo'lmadi (buferda %d): %s", len(self.buffer), e)


def main(config_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with open(config_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    pusher = Pusher(cfg)
    sources = [SOURCES[s["type"]](s) for s in cfg["sources"]]
    commander = Commander(cfg, sources, cfg["sources"]) if cfg.get("commands", True) else None
    interval = cfg.get("interval_s", 10)
    log.info("gateway: %d manba, har %ss → %s", len(sources), interval, pusher.url)
    try:
        while True:
            items = []
            for src in sources:
                try:
                    items.extend(src.read())
                except Exception as e:  # noqa: BLE001 — manba xatosi siklni to'xtatmasin
                    log.warning("%s: %s", type(src).__name__, e)
            pusher.push(items)
            if commander is not None:
                commander.run_once()  # dispetcher buyruqlari (setpoint) → SCADA
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        for src in sources:
            src.close()


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
        main(sys.argv[1] if len(sys.argv) > 1 else "config.json")
