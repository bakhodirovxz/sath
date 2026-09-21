"""MQTT ko'prigi (ixtiyoriy): GES_MQTT_URL berilsa broker ga ulanib, protocol="mqtt" sensorlar
uchun `address.topic` ga obuna bo'ladi. Xabar: raqam ("24.3") yoki JSON ({"value": 24.3, "ts": ...,
"quality": "good"} yoki address.field ko'rsatilgan maydon).

Xavfsizlik (E6):
- Parol URL da emas — `GES_MQTT_USERNAME`/`GES_MQTT_PASSWORD` yoki `GES_MQTT_PASSWORD_FILE` (Docker secret).
  URL dagi parol hali ishlaydi, lekin ogohlantiriladi (URL loglarga/`ps` ga tushadi).
- `mqtts://` — `GES_MQTT_CA_FILE` majburiy (CA pinning), `GES_MQTT_CERT_FILE` + `GES_MQTT_KEY_FILE` — mTLS.
- TLS siz `mqtt://` faqat loopback ga (dev) yoki `GES_MQTT_ALLOW_INSECURE=true` bilan — aks holda server
  ishga tushmaydi (ValueError).
- Topik ruxsati `GES_MQTT_TOPIC_ALLOW` (vergul bilan MQTT filtrlar, `{project_id}` o'rinbosari):
  sensor `address.topic` ro'yxatga mos kelmasa obuna bo'lmaydi.
- Partiyalash: xabarlar buferda, `GES_MQTT_BATCH_MS` yoki `GES_MQTT_BATCH_SIZE` bo'yicha bitta
  sessiya/`live.ingest` chaqiruvi bilan yoziladi.
- Uzilish (`on_disconnect`): obuna sensorlari `quality=bad` (Reading + last_quality), qayta ulanishda
  barcha topiklarga qayta obuna.

Kutubxona: paho-mqtt (pip install ges-server[mqtt]). Broker yo'q bo'lsa jimgina o'chiq turadi.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..orm import Sensor
from . import live

log = logging.getLogger("ges_server.mqtt")

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT filtr (`+`, `#`) topikka mos keladimi (MQTT 3.1.1 §4.7)."""
    if pattern == "#":
        return not topic.startswith("$")
    p, t = pattern.split("/"), topic.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return i == len(p) - 1
        if i >= len(t):
            return False
        if seg != "+" and seg != t[i]:
            return False
    return len(p) == len(t)


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_url(
    url: str,
    *,
    allow_insecure: bool = False,
    ca_file: Path | None = None,
    cert_file: Path | None = None,
    key_file: Path | None = None,
) -> tuple[str, int, bool, list[str]]:
    """URL va TLS sozlamasini tekshiradi → (host, port, secure, ogohlantirishlar).
    Rad etish (ValueError): loopback bo'lmagan hostga TLS siz `mqtt://` (allow_insecure=False),
    `mqtts://` CA siz, sertifikat/kalit fayli yo'q yoki juftsiz."""
    u = urlparse(url)
    if u.scheme not in ("mqtt", "tcp", "mqtts", "ssl"):
        raise ValueError(f"GES_MQTT_URL sxemasi noma'lum: {u.scheme!r} (mqtt:// yoki mqtts://)")
    host = u.hostname or "localhost"
    secure = u.scheme in ("mqtts", "ssl")
    port = u.port or (8883 if secure else 1883)
    warnings: list[str] = []
    if u.password:
        warnings.append(
            "GES_MQTT_URL ichida parol bor — GES_MQTT_PASSWORD (yoki GES_MQTT_PASSWORD_FILE) ga ko'chiring: "
            "URL loglarga va jarayonlar ro'yxatiga tushadi"
        )
    if not secure:
        if is_loopback(host):
            warnings.append(f"MQTT TLS siz (mqtt://{host}) — faqat loopback/dev uchun")
        elif allow_insecure:
            warnings.append(
                f"MQTT TLS siz mqtt://{host}:{port} — GES_MQTT_ALLOW_INSECURE=true: o'lchovlar va parol ochiq matnda"
            )
        else:
            raise ValueError(
                f"mqtt://{host}:{port} TLS siz, loopback emas — mqtts:// (GES_MQTT_CA_FILE bilan) ishlating "
                "yoki ochiq tarmoq xavfini qabul qilib GES_MQTT_ALLOW_INSECURE=true qo'ying"
            )
    else:
        if not ca_file:
            raise ValueError("mqtts:// uchun GES_MQTT_CA_FILE (broker CA sertifikati) majburiy")
        if not Path(ca_file).is_file():
            raise ValueError(f"GES_MQTT_CA_FILE topilmadi: {ca_file}")
        if bool(cert_file) != bool(key_file):
            raise ValueError("mTLS: GES_MQTT_CERT_FILE va GES_MQTT_KEY_FILE birga berilishi kerak")
        for f in (cert_file, key_file):
            if f and not Path(f).is_file():
                raise ValueError(f"MQTT sertifikat/kalit fayli topilmadi: {f}")
    return host, port, secure, warnings


class MqttBridge:
    def __init__(
        self,
        url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        password_file: Path | None = None,
        ca_file: Path | None = None,
        cert_file: Path | None = None,
        key_file: Path | None = None,
        allow_insecure: bool = False,
        topic_allow: str = "#",
        batch_size: int = 200,
        batch_ms: int = 250,
    ):
        self.url = url
        self.username, self.password, self.password_file = username, password, password_file
        self.ca_file, self.cert_file, self.key_file = ca_file, cert_file, key_file
        self.allow_insecure = allow_insecure
        self.topic_allow = [p.strip() for p in topic_allow.split(",") if p.strip()]
        self.batch_size, self.batch_ms = max(1, int(batch_size)), max(10, int(batch_ms))
        self.client = None
        self.connected = False
        self._topics: dict[str, list[tuple[int, int, str | None]]] = {}  # topic → [(project_id, sensor_id, field)]
        self._denied: set[str] = set()
        self._lock = threading.Lock()
        self._buf: dict[int, list[dict]] = {}
        self._buf_n = 0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._flusher: threading.Thread | None = None

    @classmethod
    def from_settings(cls, s: Settings) -> MqttBridge:
        return cls(
            s.mqtt_url or "",
            username=s.mqtt_username,
            password=s.mqtt_password,
            password_file=s.mqtt_password_file,
            ca_file=s.mqtt_ca_file,
            cert_file=s.mqtt_cert_file,
            key_file=s.mqtt_key_file,
            allow_insecure=s.mqtt_allow_insecure,
            topic_allow=s.mqtt_topic_allow,
            batch_size=s.mqtt_batch_size,
            batch_ms=s.mqtt_batch_ms,
        )

    # --- obunalar -------------------------------------------------------------------------------

    def topic_allowed(self, project_id: int, topic: str) -> bool:
        return any(topic_matches(p.replace("{project_id}", str(project_id)), topic) for p in self.topic_allow)

    def refresh_subscriptions(self, resubscribe: bool = False) -> None:
        """DB dagi mqtt sensorlardan topik xaritasini quradi; ruxsatsiz topik obuna qilinmaydi.
        resubscribe=True (qayta ulanish) — barcha topiklar qaytadan subscribe qilinadi."""
        with SessionLocal() as db, self._lock:
            new: dict[str, list[tuple[int, int, str | None]]] = {}
            for s in db.query(Sensor).filter_by(protocol="mqtt", enabled=True).all():
                addr = s.address or {}
                topic = addr.get("topic")
                if not topic:
                    continue
                if not self.topic_allowed(s.project_id, topic):
                    if topic not in self._denied:
                        self._denied.add(topic)
                        log.warning(
                            "mqtt: %s (loyiha %s, sensor %s) GES_MQTT_TOPIC_ALLOW=%s ga mos emas — obuna yo'q",
                            topic, s.project_id, s.key, ",".join(self.topic_allow),
                        )
                    continue
                self._denied.discard(topic)
                new.setdefault(topic, []).append((s.project_id, s.id, addr.get("field")))
            if self.client is not None:
                add = set(new) if resubscribe else set(new) - set(self._topics)
                for t in sorted(add):
                    self.client.subscribe(t, qos=1)
                for t in set(self._topics) - set(new):
                    self.client.unsubscribe(t)
            self._topics = new

    def _targets_for(self, topic: str) -> list[tuple[int, int, str | None]]:
        with self._lock:
            hit = self._topics.get(topic)
            if hit is not None:
                return list(hit)
            out: list[tuple[int, int, str | None]] = []
            for pattern, targets in self._topics.items():
                if ("+" in pattern or "#" in pattern) and topic_matches(pattern, topic):
                    out.extend(targets)
            return out

    # --- xabarlar → partiya ---------------------------------------------------------------------

    def _on_message(self, _client, _userdata, msg) -> None:
        raw = msg.payload.decode("utf-8", errors="replace").strip()
        targets = self._targets_for(msg.topic)
        if not targets:
            return
        value, ts, quality = _parse_payload(raw, None)
        for project_id, sensor_id, field in targets:
            v, t, q = (value, ts, quality) if field is None else _parse_payload(raw, field)
            if v is None:
                log.debug("mqtt %s: raqam topilmadi: %s", msg.topic, raw[:80])
                continue
            self._enqueue(project_id, {"sensor_id": sensor_id, "value": v, "ts": t, "quality": q})

    def _enqueue(self, project_id: int, item: dict) -> None:
        with self._lock:
            self._buf.setdefault(project_id, []).append(item)
            self._buf_n += 1
            full = self._buf_n >= self.batch_size
        if full:
            self._wake.set()

    def flush(self) -> int:
        """Buferdagi xabarlarni loyiha bo'yicha bitta sessiya/ingest bilan yozadi → yozilgan soni."""
        with self._lock:
            buf, self._buf, self._buf_n = self._buf, {}, 0
        if not buf:
            return 0
        n = 0
        max_age = timedelta(days=get_settings().ingest_max_age_days)
        for project_id, items in buf.items():
            try:
                with SessionLocal() as db:
                    res = live.ingest(db, project_id, items, source="mqtt", max_age=max_age)
                n += int(res.get("accepted", 0))
            except Exception:  # noqa: BLE001 — bitta partiya xatosi flusher oqimini o'ldirmasin; iz logda
                log.exception("mqtt: loyiha %s uchun %d xabar yozilmadi", project_id, len(items))
        return n

    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.batch_ms / 1000.0)
            self._wake.clear()
            self.flush()
        self.flush()

    # --- ulanish hodisalari ---------------------------------------------------------------------

    def _on_connect(self, *_args) -> None:
        was = self.connected
        self.connected = True
        log.info("mqtt: ulandi%s", " (qayta)" if was is False and self._topics else "")
        self.refresh_subscriptions(resubscribe=True)

    def _on_disconnect(self, *_args) -> None:
        if not self.connected:
            return
        self.connected = False
        log.warning("mqtt: broker bilan aloqa uzildi — obuna sensorlari bad, qayta ulanish kutilmoqda")
        self.mark_disconnected()

    def mark_disconnected(self) -> None:
        """Obuna qilingan barcha sensorlarga `quality=bad` (aloqa yo'q — oxirgi qiymat ishonchsiz)."""
        with self._lock:
            by_project: dict[int, set[int]] = {}
            for targets in self._topics.values():
                for project_id, sensor_id, _ in targets:
                    by_project.setdefault(project_id, set()).add(sensor_id)
        for project_id, ids in by_project.items():
            with SessionLocal() as db:
                live.mark_bad(db, project_id, sorted(ids), source="mqtt")

    # --- start/stop ------------------------------------------------------------------------------

    def _resolve_password(self, url_password: str | None) -> str | None:
        if self.password:
            return self.password
        if self.password_file:
            return Path(self.password_file).read_text(encoding="utf-8").strip()
        return url_password

    def start(self) -> bool:
        host, port, secure, warnings = check_url(
            self.url,
            allow_insecure=self.allow_insecure,
            ca_file=self.ca_file,
            cert_file=self.cert_file,
            key_file=self.key_file,
        )
        for w in warnings:
            log.warning("mqtt: %s", w)
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
        username = self.username or u.username
        password = self._resolve_password(u.password)
        if username:
            client.username_pw_set(username, password)
        if secure:
            client.tls_set(
                ca_certs=str(self.ca_file),
                certfile=str(self.cert_file) if self.cert_file else None,
                keyfile=str(self.key_file) if self.key_file else None,
            )
        client.on_message = self._on_message
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        try:
            client.connect_async(host, port, keepalive=60)
            client.loop_start()
        except Exception as e:  # noqa: BLE001 — tarmoq xatosi serverni to'xtatmasin (paho o'zi qayta uladi)
            log.warning("MQTT ulanish xatosi: %s", e)
            return False
        self.client = client
        self._stop.clear()
        self._flusher = threading.Thread(target=self._flush_loop, name="mqtt-flush", daemon=True)
        self._flusher.start()
        log.info("MQTT ko'prigi: %s://%s:%d%s", "mqtts" if secure else "mqtt", host, port, " (mTLS)" if self.cert_file else "")
        return True

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._flusher is not None:
            self._flusher.join(timeout=5)
            self._flusher = None
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
        self.connected = False


def _parse_payload(
    raw: str, field: str | None
) -> tuple[float | None, str | float | None, str | None]:
    """Qaytaradi: (qiymat, ts, quality). JSON da "quality" (yoki "q") bo'lsa olinadi."""
    try:
        return float(raw), None, None
    except ValueError:
        pass
    try:
        data = json.loads(raw)
    except ValueError:
        return None, None, None
    if isinstance(data, dict):
        v = data.get(field) if field else data.get("value", data.get("v"))
        ts = data.get("ts") or data.get("timestamp") or data.get("time")
        q = data.get("quality") or data.get("q")
        try:
            return float(v), ts, (str(q).lower() if q is not None else None)
        except (TypeError, ValueError):
            return None, None, None
    if isinstance(data, int | float):
        return float(data), None, None
    return None, None, None


bridge: MqttBridge | None = None


def start_if_configured(settings: Settings) -> None:
    """GES_MQTT_URL bo'lsa ko'prikni ishga tushiradi; noto'g'ri xavfsizlik sozlamasi (TLS siz ochiq
    tarmoq, CA yo'q) ValueError — server ishga tushmaydi."""
    global bridge
    if not settings.mqtt_url:
        return
    bridge = MqttBridge.from_settings(settings)
    bridge.start()


def refresh() -> None:
    if bridge is not None:
        bridge.refresh_subscriptions()
