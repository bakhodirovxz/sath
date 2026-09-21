"""E6: MQTT ko'prigi — TLS/parol siyosati, topik ruxsati, partiyalash, uzilishda bad, qayta obuna.
paho-mqtt o'rniga soxta klient (tarmoq kerak emas)."""

import logging
import sys
import types
from pathlib import Path

import pytest
from ges_server.db import SessionLocal
from ges_server.monitoring import live, mqtt_bridge
from ges_server.orm import Reading, Sensor


class FakeClient:
    def __init__(self, *_a, **_k):
        self.calls: list[tuple] = []
        self.on_message = self.on_connect = self.on_disconnect = None

    def __getattr__(self, name):  # subscribe/unsubscribe/tls_set/username_pw_set/connect_async/loop_*
        def rec(*a, **k):
            self.calls.append((name, a, k))

        return rec

    def of(self, name):
        return [c for c in self.calls if c[0] == name]


class Msg:
    def __init__(self, topic, payload):
        self.topic, self.payload = topic, payload.encode()


@pytest.fixture
def fake_paho(monkeypatch):
    pkg = types.ModuleType("paho")
    mq = types.ModuleType("paho.mqtt")
    cl = types.ModuleType("paho.mqtt.client")
    cl.Client = FakeClient
    cl.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    monkeypatch.setitem(sys.modules, "paho", pkg)
    monkeypatch.setitem(sys.modules, "paho.mqtt", mq)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", cl)
    return cl


def _sensor(client, users, key, topic, **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": key, "kind": "power", "unit": "MW", "protocol": "mqtt", "address": {"topic": topic}, **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- URL / TLS siyosati -------------------------------------------------------------------------


def test_plain_mqtt_to_remote_host_rejected_unless_allowed(tmp_path):
    with pytest.raises(ValueError, match="TLS siz"):
        mqtt_bridge.check_url("mqtt://broker.plant:1883")
    host, port, secure, warns = mqtt_bridge.check_url("mqtt://broker.plant", allow_insecure=True)
    assert (host, port, secure) == ("broker.plant", 1883, False)
    assert any("ALLOW_INSECURE" in w for w in warns)
    # loopback — dev, faqat ogohlantirish
    _, _, _, warns = mqtt_bridge.check_url("mqtt://localhost:1883")
    assert any("loopback" in w for w in warns)
    _, _, _, warns = mqtt_bridge.check_url("mqtt://127.0.0.1")
    assert any("loopback" in w for w in warns)


def test_mqtts_requires_ca_and_paired_client_cert(tmp_path):
    with pytest.raises(ValueError, match="CA_FILE"):
        mqtt_bridge.check_url("mqtts://broker.plant")
    ca = tmp_path / "ca.pem"
    ca.write_text("x")
    host, port, secure, _ = mqtt_bridge.check_url("mqtts://broker.plant", ca_file=ca)
    assert (host, port, secure) == ("broker.plant", 8883, True)
    with pytest.raises(ValueError, match="birga"):
        mqtt_bridge.check_url("mqtts://broker.plant", ca_file=ca, cert_file=tmp_path / "c.pem")
    with pytest.raises(ValueError, match="topilmadi"):
        mqtt_bridge.check_url("mqtts://broker.plant", ca_file=tmp_path / "yoq.pem")


def test_password_in_url_warns_and_secret_file_wins(fake_paho, tmp_path, caplog):
    pw = tmp_path / "pw"
    pw.write_text("sirli\n")
    b = mqtt_bridge.MqttBridge("mqtt://sath:urlpass@localhost:1883", password_file=pw, batch_ms=50)
    with caplog.at_level(logging.WARNING, logger="ges_server.mqtt"):
        assert b.start() is True
    try:
        assert any("ichida parol" in r.message for r in caplog.records)
        assert "urlpass" not in caplog.text  # parol logga tushmaydi
        (name, args, _), = b.client.of("username_pw_set")
        assert args == ("sath", "sirli")  # sir fayli URL dagi paroldan ustun
        assert b.client.of("tls_set") == []
    finally:
        b.stop()


def test_mtls_tls_set_with_ca_cert_key(fake_paho, tmp_path):
    for n in ("ca", "cert", "key"):
        (tmp_path / f"{n}.pem").write_text("x")
    b = mqtt_bridge.MqttBridge(
        "mqtts://broker.plant",
        ca_file=tmp_path / "ca.pem",
        cert_file=tmp_path / "cert.pem",
        key_file=tmp_path / "key.pem",
        batch_ms=50,
    )
    assert b.start() is True
    try:
        (_, _, kw), = b.client.of("tls_set")
        assert Path(kw["ca_certs"]).name == "ca.pem" and Path(kw["certfile"]).name == "cert.pem"
        assert Path(kw["keyfile"]).name == "key.pem"
        (_, args, _), = b.client.of("connect_async")
        assert args[:2] == ("broker.plant", 8883)
    finally:
        b.stop()


def test_start_if_configured_rejects_insecure(monkeypatch):
    from ges_server.config import Settings

    s = Settings(mqtt_url="mqtt://broker.plant:1883")
    with pytest.raises(ValueError):
        mqtt_bridge.start_if_configured(s)
    assert mqtt_bridge.bridge is None or mqtt_bridge.bridge.client is None


# --- topik ruxsati ---------------------------------------------------------------------------------


def test_topic_matches():
    tm = mqtt_bridge.topic_matches
    assert tm("#", "a/b/c") and tm("a/#", "a") and tm("a/#", "a/b/c") and not tm("a/#", "b/a")
    assert tm("a/+/c", "a/x/c") and not tm("a/+/c", "a/x/y/c") and not tm("a/+", "a/x/y")
    assert not tm("#", "$SYS/x") and tm("a/b", "a/b") and not tm("a/b", "a/b/c")


def test_topic_acl_blocks_unlisted_and_project_placeholder(fake_paho, client, users, caplog):
    pid = users["project_id"]
    ok = _sensor(client, users, "AGG1.P", f"sath/{pid}/agg1/p")
    bad = _sensor(client, users, "AGG2.P", "sath/999/agg2/p")
    b = mqtt_bridge.MqttBridge("mqtt://localhost", topic_allow="sath/{project_id}/#", batch_ms=50)
    assert b.start()
    try:
        with caplog.at_level(logging.WARNING, logger="ges_server.mqtt"):
            b.refresh_subscriptions()
        assert set(b._topics) == {f"sath/{pid}/agg1/p"}
        assert any("sath/999/agg2/p" in r.message and "mos emas" in r.message for r in caplog.records)
        assert [c[1][0] for c in b.client.of("subscribe")] == [f"sath/{pid}/agg1/p"]
        # ruxsatsiz topikdan xabar — hech narsa yozilmaydi
        b._on_message(None, None, Msg("sath/999/agg2/p", "5"))
        assert b.flush() == 0
        with SessionLocal() as db:
            assert db.get(Sensor, bad).last_value is None and db.get(Sensor, ok).last_value is None
    finally:
        b.stop()


# --- partiyalash, uzilish, qayta obuna ----------------------------------------------------------


def test_batching_single_ingest_per_project(fake_paho, client, users, monkeypatch):
    s1 = _sensor(client, users, "AGG1.P", "ges/agg1/p")
    s2 = _sensor(client, users, "AGG2.P", "ges/agg2/p", address={"topic": "ges/agg2", "field": "mw"})
    calls = []
    real = live.ingest

    def counting(db, project_id, items, **kw):
        calls.append(len(items))
        return real(db, project_id, items, **kw)

    monkeypatch.setattr(live, "ingest", counting)
    b = mqtt_bridge.MqttBridge("mqtt://localhost", batch_size=100, batch_ms=10_000)
    assert b.start()
    try:
        b._on_connect(b.client, None, {}, 0, None)  # V2 imzo
        b._on_message(None, None, Msg("ges/agg1/p", "20.5"))
        b._on_message(None, None, Msg("ges/agg1/p", '{"value": 21, "quality": "uncertain"}'))
        b._on_message(None, None, Msg("ges/agg2", '{"mw": 33.25, "ts": "2026-09-20T10:00:00Z"}'))
        b._on_message(None, None, Msg("ges/agg2", "nima bu"))  # raqam emas — tashlanadi
        with SessionLocal() as db:
            assert db.query(Reading).count() == 0  # hali buferda
        assert b.flush() == 3 and calls == [3]  # bitta ingest, uchta yozuv
        with SessionLocal() as db:
            a1, a2 = db.get(Sensor, s1), db.get(Sensor, s2)
            assert a1.last_value == 21 and a1.last_quality == "uncertain"
            assert a2.last_value == 33.25 and a2.last_ts.strftime("%H:%M") == "10:00"
        # hajm bo'yicha uyg'otish
        b.batch_size = 2
        b._on_message(None, None, Msg("ges/agg1/p", "1"))
        assert not b._wake.is_set()
        b._on_message(None, None, Msg("ges/agg1/p", "2"))
        assert b._wake.is_set()
    finally:
        b.stop()
    # stop() qolgan buferni yozadi
    with SessionLocal() as db:
        assert db.get(Sensor, s1).last_value == 2


def test_disconnect_marks_bad_and_reconnect_resubscribes(fake_paho, client, users):
    s1 = _sensor(client, users, "AGG1.P", "ges/agg1/p")
    s2 = _sensor(client, users, "AGG2.P", "ges/agg2/p")
    b = mqtt_bridge.MqttBridge("mqtt://localhost", batch_ms=10_000)
    assert b.start()
    try:
        b._on_connect(b.client, None, {}, 0, None)
        assert sorted(c[1][0] for c in b.client.of("subscribe")) == ["ges/agg1/p", "ges/agg2/p"]
        b._on_message(None, None, Msg("ges/agg1/p", "20"))
        b.flush()
        b._on_disconnect(b.client, None, {}, 7, None)
        with SessionLocal() as db:
            a1, a2 = db.get(Sensor, s1), db.get(Sensor, s2)
            assert a1.last_quality == "bad" and a1.last_value == 20  # qiymat saqlanadi, sifat bad
            assert a2.last_quality == "bad" and a2.last_value is None
            rows = db.query(Reading).filter_by(sensor_id=s1).order_by(Reading.id).all()
            assert [r.quality for r in rows] == ["good", "bad"] and rows[-1].value == 20
            assert db.query(Reading).filter_by(sensor_id=s2).count() == 0  # qiymat yo'q → yozuv yo'q
        b._on_disconnect(b.client, None, {}, 7, None)  # takroriy — yana bad yozilmaydi
        with SessionLocal() as db:
            assert db.query(Reading).filter_by(sensor_id=s1).count() == 2
        # qayta ulanish: hamma topik qaytadan subscribe, yangi qiymat → good
        b._on_connect(b.client, None, {}, 0, None)
        assert len(b.client.of("subscribe")) == 4
        b._on_message(None, None, Msg("ges/agg1/p", "22"))
        b.flush()
        with SessionLocal() as db:
            a1 = db.get(Sensor, s1)
            assert a1.last_quality == "good" and a1.last_value == 22
        fc = b.client
    finally:
        b.stop()
    assert all(c[2].get("qos") == 1 for c in fc.of("subscribe"))  # obuna QoS 1
