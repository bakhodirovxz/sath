"""SRV-06: strukturalangan log (JSON), so'rov identifikatori, Prometheus /api/metrics."""

import json
import logging

import pytest


def test_request_id_header_roundtrip(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    r = client.get("/api/health", headers={"X-Request-ID": "yomon id\n<script>"})
    rid = r.headers["x-request-id"]
    assert rid != "yomon id\n<script>" and len(rid) == 16


def test_json_log_contains_request_id(capsys):
    from ges_server import observability as obs

    h = obs.configure_logging("json", "INFO")
    try:
        token = obs.request_id_var.set("rid-42")
        logging.getLogger("ges_server.sinov").warning("salom %s", "dunyo")
        obs.request_id_var.reset(token)
        line = [ln for ln in capsys.readouterr().err.splitlines() if "salom" in ln][-1]
        rec = json.loads(line)
        assert rec["msg"] == "salom dunyo" and rec["level"] == "WARNING" and rec["request_id"] == "rid-42"
        assert rec["logger"] == "ges_server.sinov" and rec["ts"].endswith("+00:00")
    finally:
        obs.configure_logging("text", "INFO")
        assert sum(getattr(x, obs._HANDLER_MARK, False) for x in logging.getLogger().handlers) == 1  # idempotent
        del h


def test_metrics_protected_and_exposes_counters(client, users, monkeypatch):
    from ges_server import config
    from ges_server.observability import metrics

    s = config.get_settings()
    # token yo'q — faqat loopback (TestClient manzili "testclient")
    assert client.get("/api/metrics").status_code == 403
    monkeypatch.setattr(s, "metrics_token", "m-token")
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/metrics", headers={"Authorization": "Bearer boshqa"}).status_code == 401
    metrics.reset()
    client.get("/api/health")
    client.get("/api/yoq-yol")
    client.post(f"/api/projects/{users['project_id']}/readings", json=[])  # kalitsiz ingest — rad
    r = client.get("/api/metrics", headers={"Authorization": "Bearer m-token"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert 'sath_http_requests_total{method="GET",status="200"}' in body
    assert 'sath_http_requests_total{method="GET",status="404"} 1' in body
    assert 'sath_ingest_requests_total{result="rejected"} 1' in body
    assert 'sath_job_queue_depth{queue="sim",status="queued"} 0' in body
    assert 'sath_job_queue_depth{queue="derived",status="running"}' in body
    assert "sath_http_request_duration_seconds_count" in body


@pytest.mark.parametrize("name", ["Caddyfile", "Caddyfile.ha"])
def test_metrics_not_exposed_through_caddy(name):
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "deploy" / name).read_text(encoding="utf-8")
    assert "respond /api/metrics 404" in text
