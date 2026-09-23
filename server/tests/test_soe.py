"""D3: SOE — ms aniqlikdagi hodisalar tartibi, takror, ingest kaliti, filtr, birlashtirilgan vaqt chizig'i, muddat."""

from datetime import datetime, timedelta, timezone

from conftest import ingest_headers
from ges_server.db import SessionLocal
from ges_server.monitoring import soe
from ges_server.orm import SequenceEvent


def _key(client, users):
    r = client.get(f"/api/projects/{users['project_id']}/keys/ingest", headers=users["approver"])
    assert r.status_code == 200, r.text
    return r.json()["key"]


def test_soe_ms_order_dedup_and_filters(client, users):
    pid = users["project_id"]
    key = _key(client, users)
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)  # so'rov oynasi (48 soat) ichida
    # trip ketma-ketligi: PROT 0 ms, CB 12 ms, AGG1.RUN 0 → 15 ms, GATE STUCK 1.5 s (tartibsiz yuboriladi)
    items = [
        {"point": "GATE1", "state": "STUCK", "ts": (t0 + timedelta(milliseconds=1500)).isoformat(timespec="milliseconds")},
        {"point": "AGG1.CB", "state": "OPEN", "ts": (t0 + timedelta(milliseconds=12)).isoformat(timespec="milliseconds")},
        {"point": "AGG1.PROT", "state": "TRIP", "ts": t0.isoformat(timespec="milliseconds"), "raw": {"code": 87}},
        {"point": "AGG1.RUN", "state": False, "ts": t0.timestamp() + 0.015},  # epoch float (ms kasri)
        {"point": "AGG1.CB", "state": "OPEN", "ts": (t0 + timedelta(milliseconds=12)).isoformat(timespec="milliseconds")},  # takror
        {"point": "", "state": "X", "ts": t0.isoformat()},  # nuqtasiz
        {"point": "Y", "state": "X", "ts": "buzuq"},
    ]
    r = client.post(f"/api/projects/{pid}/soe", json=items, headers={"X-Ingest-Key": key})
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 4 and r.json()["duplicates"] == 1
    assert {x["reason"] for x in r.json()["rejected"]} == {"point_missing", "ts_invalid"}
    # qayta yuborish (spool retry) — hammasi takror
    r = client.post(f"/api/projects/{pid}/soe", json=items[:4], headers={"X-Ingest-Key": key})
    assert r.json() == {"accepted": 0, "duplicates": 4, "rejected": []}
    # kalitsiz — 401; SCADA-07: muhandis/ko'ruvchi tokeni — 403, qo'lda kiritish faqat smena boshlig'i
    assert client.post(f"/api/projects/{pid}/soe", json=items[:1]).status_code == 401
    for who in ("viewer", "engineer"):
        assert client.post(f"/api/projects/{pid}/soe", json=[{"point": "M", "state": "1", "ts": t0.isoformat()}], headers=users[who]).status_code == 403
    from conftest import add_member

    sup = add_member(client, users["admin"], pid, "sup", "shift_supervisor")
    r = client.post(f"/api/projects/{pid}/soe", json=[{"point": "M", "state": "1", "ts": t0.isoformat(), "source": "manual"}], headers=sup)
    assert r.status_code == 200 and r.json()["accepted"] == 1
    # ro'yxat: ms tartibi (eng yangisi birinchi), 1 ms aniqlik saqlangan
    rows = client.get(f"/api/projects/{pid}/soe?hours=48", headers=users["viewer"]).json()
    # M va AGG1.PROT bir xil ms — keyin kelgani (id katta) birinchi
    assert [x["point"] for x in rows] == ["GATE1", "AGG1.RUN", "AGG1.CB", "M", "AGG1.PROT"]
    ms = {x["point"]: x["ts_ms"] for x in rows}
    assert ms["AGG1.CB"] - ms["AGG1.PROT"] == 12 and ms["AGG1.RUN"] - ms["AGG1.PROT"] == 15
    assert rows[-1]["ts"].endswith("+00:00") and ".012" in next(x["ts"] for x in rows if x["point"] == "AGG1.CB")
    assert next(x for x in rows if x["point"] == "AGG1.PROT")["raw"] == {"code": 87}
    assert next(x for x in rows if x["point"] == "AGG1.RUN")["state"] == "0"
    # filtrlar
    assert [x["point"] for x in client.get(f"/api/projects/{pid}/soe?hours=48&point=AGG1.*", headers=users["viewer"]).json()] == ["AGG1.RUN", "AGG1.CB", "AGG1.PROT"]
    assert [x["point"] for x in client.get(f"/api/projects/{pid}/soe?hours=48&source=manual", headers=users["viewer"]).json()] == ["M"]
    # audit
    with SessionLocal() as db:
        from ges_server.orm import AuditLog

        a = db.query(AuditLog).filter_by(action="soe.ingest").first()
        assert a is not None and a.detail["accepted"] == 4 and a.detail["auth"] == "key"


def test_timeline_merges_soe_and_alarms(client, users):
    pid = users["project_id"]
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "AGG1.VIB", "name": "Vib", "kind": "vibration", "unit": "mm/s", "high_alarm": 5}, headers=users["engineer"])
    assert r.status_code == 201
    now = datetime.now(timezone.utc)
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "AGG1.VIB", "value": 9}], headers=ingest_headers(client, users))
    client.post(
        f"/api/projects/{pid}/soe",
        json=[{"point": "AGG1.PROT", "state": "TRIP", "ts": (now - timedelta(seconds=2)).isoformat(timespec="milliseconds"), "source": "iec104"}],
        headers=ingest_headers(client, users),
    )
    tl = client.get(f"/api/projects/{pid}/timeline?hours=1", headers=users["viewer"]).json()
    assert [x["type"] for x in tl] == ["alarm", "soe"]  # alarm (hozir) yangiroq, trip 2 s oldin
    assert tl[0]["point"] == "AGG1.VIB" and tl[0]["state"] == "yuqori" and tl[0]["raw"]["value"] == 9
    assert tl[1]["point"] == "AGG1.PROT" and tl[1]["source"] == "iec104"


def test_soe_purge_and_future_rejected(client, users):
    pid = users["project_id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        res = soe.ingest(db, pid, [
            {"point": "OLD", "state": "1", "ts": (now - timedelta(days=400)).isoformat()},
            {"point": "NEW", "state": "1", "ts": (now - timedelta(days=1)).isoformat()},
            {"point": "FUT", "state": "1", "ts": (now + timedelta(hours=1)).isoformat()},
        ], source="sim")
        assert res["accepted"] == 2 and res["rejected"] == [{"point": "FUT", "reason": "ts_future"}]
        assert soe.purge(db, retention_days=365, now=now) == 1
        assert [e.point for e in db.query(SequenceEvent).all()] == ["NEW"]
        assert soe.purge(db, retention_days=0, now=now) == 0
