"""MQTT ko'prigi (ixtiyoriy): GES_MQTT_URL berilsa broker ga ulanib, protocol="mqtt" sensorlar
uchun `address.topic` ga obuna bo'ladi. Xabar: raqam ("24.3") yoki JSON ({"value": 24.3, "ts": ...}
yoki address.field ko'rsatilgan maydon).

Kutubxona: paho-mqtt (pip install ges-server[mqtt]). Broker yo'q bo'lsa jimgina o'chiq turadi.
"""

from __future__ import annotations

import json
import logging
import threading
from urllib.parse import urlparse

from ..db import SessionLocal
from ..orm import Sensor
from . import live

log = logging.getLogger("ges_server.mqtt")


class MqttBridge:
    def __init__(self, url: str):
        self.url = url
        self.client = None
        self._topics: dict[
            str, list[tuple[int, int, str | None]]
        ] = {}  # topic → [(project_id, sensor_id, field)]
        self._lock = threading.Lock()

    def refresh_subscriptions(self) -> None:
        with SessionLocal() as db, self._lock:
            new: dict[str, list[tuple[int, int, str | None]]] = {}
            for s in db.query(Sensor).filter_by(protocol="mqtt", enabled=True).all():
                topic = (s.address or {}).get("topic")
                if topic:
                    new.setdefault(topic, []).append(
                        (s.project_id, s.id, (s.address or {}).get("field"))
                    )
            if self.client is not None:
                for t in set(new) - set(self._topics):
                    self.client.subscribe(t)
                for t in set(self._topics) - set(new):
                    self.client.unsubscribe(t)
            self._topics = new

    def _on_message(self, _client, _userdata, msg) -> None:
        raw = msg.payload.decode("utf-8", errors="replace").strip()
        with self._lock:
            targets = list(self._topics.get(msg.topic, []))
        if not targets:
            return
        for project_id, sensor_id, field in targets:
            value, ts = _parse_payload(raw, field)
            if value is None:
                log.debug("mqtt %s: raqam topilmadi: %s", msg.topic, raw[:80])
                continue
            with SessionLocal() as db:
                live.ingest(
                    db,
                    project_id,
                    [{"sensor_id": sensor_id, "value": value, "ts": ts}],
                    source="mqtt",
                )

    def start(self) -> bool:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            log.warning("paho-mqtt o'rnatilmagan — MQTT ko'prigi o'chiq (pip install paho-mqtt)")
            return False
        u = urlparse(self.url)
        client = (
            mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if hasattr(mqtt, "CallbackAPIVersion")
            else mqtt.Client()
        )
        if u.username:
            client.username_pw_set(u.username, u.password)
        if u.scheme in ("mqtts", "ssl"):
            client.tls_set()
        client.on_message = self._on_message
        client.on_connect = lambda *_: self.refresh_subscriptions()
        try:
            client.connect_async(
                u.hostname or "localhost",
                u.port or (8883 if u.scheme == "mqtts" else 1883),
                keepalive=60,
            )
            client.loop_start()
        except Exception as e:  # noqa: BLE001 — tarmoq xatosi serverni to'xtatmasin
            log.warning("MQTT ulanish xatosi: %s", e)
            return False
        self.client = client
        log.info("MQTT ko'prigi: %s", u.hostname)
        return True

    def stop(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()


def _parse_payload(raw: str, field: str | None) -> tuple[float | None, str | float | None]:
    try:
        return float(raw), None
    except ValueError:
        pass
    try:
        data = json.loads(raw)
    except ValueError:
        return None, None
    if isinstance(data, dict):
        v = data.get(field) if field else data.get("value", data.get("v"))
        ts = data.get("ts") or data.get("timestamp") or data.get("time")
        try:
            return float(v), ts
        except (TypeError, ValueError):
            return None, None
    if isinstance(data, int | float):
        return float(data), None
    return None, None


bridge: MqttBridge | None = None


def start_if_configured(url: str | None) -> None:
    global bridge
    if not url:
        return
    bridge = MqttBridge(url)
    bridge.start()


def refresh() -> None:
    if bridge is not None:
        bridge.refresh_subscriptions()
