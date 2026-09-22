"""F9: smena topshirish — avtomatik varaqa, ogohlantirishlar (yakunlanmagan), ikki imzo (audit), hodisalar tasmasi."""

from conftest import send_command
from ges_server.db import SessionLocal
from ges_server.orm import AuditLog


def _sensor(client, users, key, **kw):
    r = client.post(f"/api/projects/{users['project_id']}/sensors", json={"key": key, "name": key, "kind": "level", "unit": "m", **kw}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    return r.json()


def test_handover_requires_acknowledging_warnings_and_two_signatures(client, users):
    pid = users["project_id"]
    s = _sensor(client, users, "RES.H", high_alarm=900.0)
    sp = _sensor(client, users, "GATE1.SP", writable=True, min_setpoint=0, max_setpoint=100)
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 905}, {"key": "GATE1.SP", "value": 40}], headers=users["engineer"])
    client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "sinov"}, headers=users["engineer"])
    client.post(f"/api/sensors/{s['id']}/unshelve", headers=users["engineer"])
    send_command(client, users["engineer"], pid, sp["id"], 55.0, "smena")
    # varaqa: kvitlanmagan alarm + kutilayotgan buyruq → ogohlantirishlar
    snap = client.get(f"/api/projects/{pid}/shift/snapshot", headers=users["viewer"]).json()
    assert snap["unacked"] == 1 and len(snap["pending_commands"]) == 1 and snap["alarms"][0]["key"] == "RES.H"
    assert any("kvitlanmagan" in w for w in snap["warnings"]) and any("buyruq" in w for w in snap["warnings"])
    # ogohlantirishlar tasdiqlanmasa — 409
    r = client.post(f"/api/projects/{pid}/shift/handover", json={"notes": "hammasi joyida"}, headers=users["engineer"])
    assert r.status_code == 409 and "yakunlanmagan" in r.json()["detail"]
    assert client.post(f"/api/projects/{pid}/shift/handover", json={"notes": "x", "acknowledge_warnings": True}, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/shift/handover", json={"notes": "RES.H yuqori, zatvor buyrug'i navbatda", "acknowledge_warnings": True}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    h = r.json()
    assert h["status"] == "handed" and h["handed_by"] == users["ids"]["engineer"] and h["received_at"] is None and h["warnings"]
    # ikkinchi topshirish — avvalgisi qabul qilinmaguncha yo'q
    assert client.post(f"/api/projects/{pid}/shift/handover", json={"acknowledge_warnings": True}, headers=users["engineer"]).status_code == 409
    # topshiruvchi o'zi qabul qila olmaydi; viewer ham; approver qabul qiladi
    assert client.post(f"/api/shift/handovers/{h['id']}/receive", json={"notes": "men"}, headers=users["engineer"]).status_code == 409
    assert client.post(f"/api/shift/handovers/{h['id']}/receive", json={}, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/shift/handovers/{h['id']}/receive", json={"notes": "qabul qildim"}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["status"] == "received" and r.json()["received_by_username"] == "approver"
    assert client.post(f"/api/shift/handovers/{h['id']}/receive", json={}, headers=users["approver"]).status_code == 409
    # audit ikkala imzo; jurnalda shift_end/shift_start yozuvlari
    with SessionLocal() as db:
        acts = [a.action for a in db.query(AuditLog).filter(AuditLog.action.like("shift.%")).all()]
    assert sorted(acts) == ["shift.handover", "shift.receive"]
    j = client.get(f"/api/projects/{pid}/journal", headers=users["viewer"]).json()
    assert [x["kind"] for x in j[:2]] == ["shift_start", "shift_end"]
    lst = client.get(f"/api/projects/{pid}/shift/handovers", headers=users["viewer"]).json()
    assert len(lst) == 1 and lst[0]["id"] == h["id"]
    # keyingi varaqa oynasi — qabul vaqtidan
    snap2 = client.get(f"/api/projects/{pid}/shift/snapshot", headers=users["viewer"]).json()
    assert snap2["since"] == r.json()["received_at"]
    # tasma: alarm + buyruq + jurnal bitta xronologiyada
    feed = client.get(f"/api/projects/{pid}/shift/feed?hours=1", headers=users["viewer"]).json()
    types = {x["type"] for x in feed}
    assert {"alarm", "command", "journal"} <= types
    assert feed == sorted(feed, key=lambda x: (x["ts_ms"], x["id"]), reverse=True)


def test_handover_clean_shift_without_warnings(client, users):
    pid = users["project_id"]
    _sensor(client, users, "TW.H")
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "TW.H", "value": 1}], headers=users["engineer"])
    snap = client.get(f"/api/projects/{pid}/shift/snapshot", headers=users["viewer"]).json()
    assert snap["warnings"] == []
    r = client.post(f"/api/projects/{pid}/shift/handover", json={"notes": "tinch smena"}, headers=users["engineer"])
    assert r.status_code == 201 and r.json()["warnings"] == []
