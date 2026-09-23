"""SCADA-07: jonli o'lchov faqat gateway kaliti bilan; qo'lda kiritish / CSV — scada.manual_entry, manual, audit."""

import pytest
from conftest import add_member, ingest_headers
from ges_server.db import SessionLocal
from ges_server.orm import Reading, SequenceEvent


@pytest.fixture
def level(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": "RES.H", "name": "Sath", "kind": "level", "unit": "m", "high_alarm": 905},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_user_tokens_cannot_push_live_readings(client, users, admin, level):
    pid = users["project_id"]
    op = add_member(client, admin, pid, "opr", "operator")
    for hdr in (users["engineer"], users["approver"], users["viewer"], users["admin"], op):
        r = client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 900}], headers=hdr)
        assert r.status_code == 403, r.text
        r = client.post(f"/api/projects/{pid}/soe", json=[{"point": "M", "state": "1", "ts": "2026-01-01T00:00:00Z"}], headers=hdr)
        assert r.status_code == 403, r.text
    assert client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 900}]).status_code == 401
    r = client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 900}], headers=ingest_headers(client, users))
    assert r.status_code == 200 and r.json()["accepted"] == 1
    with SessionLocal() as db:
        assert [x.quality for x in db.query(Reading).all()] == ["good"]


def test_manual_entry_marked_and_audited(client, users, admin, level):
    pid = users["project_id"]
    sup = add_member(client, admin, pid, "sup", "shift_supervisor")
    r = client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "RES.H", "value": 906, "quality": "good"}, {"key": "RES.H", "value": 1, "quality": "bad"}],
        headers=sup,
    )
    assert r.status_code == 200 and r.json()["accepted"] == 2, r.text
    with SessionLocal() as db:
        assert sorted(x.quality for x in db.query(Reading).all()) == ["bad", "manual"]
    s = next(x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json() if x["key"] == "RES.H")
    assert s["last_value"] == 906 and s["last_quality"] == "manual" and s["alarm"] == "high"
    logs = client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json()
    man = [a for a in logs if a["action"] == "readings.manual"]
    assert man and man[0]["user_id"] == client.get("/api/auth/me", headers=sup).json()["id"]
    assert man[0]["detail"]["source"] == "manual" and man[0]["detail"]["items"][0]["value"] == 906
    # SOE qo'lda — source=manual
    r = client.post(f"/api/projects/{pid}/soe", json=[{"point": "Q1", "state": "1", "ts": "2026-09-23T00:00:00Z", "source": "iec104"}], headers=sup)
    assert r.status_code == 200 and r.json()["accepted"] == 1, r.text
    with SessionLocal() as db:
        assert db.query(SequenceEvent).one().source == "manual"
    assert any(a["action"] == "soe.manual" for a in client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json())


def test_csv_import_requires_manual_entry(client, users, admin, level):
    pid = users["project_id"]
    csv = "ts,value\n2026-09-23T00:00:00Z,901\n2026-09-23T00:01:00Z,902,bad\n"
    for hdr in (users["engineer"], users["approver"]):
        r = client.post(f"/api/sensors/{level['id']}/import", files={"file": ("h.csv", csv, "text/csv")}, headers=hdr)
        assert r.status_code == 403, r.text
    sup = add_member(client, admin, pid, "sup", "shift_supervisor")
    r = client.post(f"/api/sensors/{level['id']}/import", files={"file": ("h.csv", csv, "text/csv")}, headers=sup)
    assert r.status_code == 200 and r.json()["accepted"] == 2 and r.json()["bad"] == 1, r.text
    with SessionLocal() as db:
        assert sorted(x.quality for x in db.query(Reading).all()) == ["bad", "manual"]
    logs = client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json()
    assert any(a["action"] == "readings.manual" and a["target_type"] == "sensor" for a in logs)
