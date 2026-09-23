"""I3: model validatsiya yozuvlari — validatsiyalanmagan natija belgilanadi, mezon bo'yicha verdikt,
muddat o'tishi va model versiyasi o'zgarishi qayta validatsiyani talab qiladi."""

from datetime import datetime, timedelta, timezone

from ges_server.db import SessionLocal
from ges_server.monitoring import validation
from ges_server.orm import Project, ValidationRecord
from test_calibration import _setup, _write_history


def test_unvalidated_twin_is_marked(client, users):
    """Qabul mezoni: validatsiyalanmagan model natijasi shunday belgilanadi."""
    pid = users["project_id"]
    sens = _setup(client, users)
    _write_history(pid, sens)
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "ok"
    assert st["validation"]["status"] == "unvalidated"
    assert "validatsiya qilinmagan" in st["validation"]["note"]
    state = client.get(f"/api/projects/{pid}/validation", headers=users["viewer"]).json()
    assert state["status"]["status"] == "unvalidated" and state["records"] == []
    # baho: kalibrovkasiz model mezonga tushmaydi (pasport FIK 0.92, haqiqiy 0.885)
    ev = state["evaluation"]
    assert ev["ok"] is False and ev["metrics"]["n_points"] >= 72
    assert any(c["name"] in ("rmse", "bias") and not c["ok"] for c in ev["checks"])
    assert ev["reason"] == "qabul mezonlari bajarilmadi"


def test_validation_record_after_calibration(client, users):
    """Kalibrovkadan keyin mezonlar bajariladi; yozuvni faqat tasdiqlovchi imzolaydi."""
    pid = users["project_id"]
    sens = _setup(client, users)
    _write_history(pid, sens)
    r = client.post(
        f"/api/projects/{pid}/calibration/run",
        json={"days": 7, "apply": True},
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["applied"]
    ev = client.get(f"/api/projects/{pid}/validation", headers=users["viewer"]).json()["evaluation"]
    assert ev["ok"] is True, ev
    # muhandis imzolay olmaydi — bu muhandislik qarori (tasdiqlovchi)
    assert (
        client.post(f"/api/projects/{pid}/validation", json={"days": 7}, headers=users["engineer"]).status_code
        == 403
    )
    rec = client.post(
        f"/api/projects/{pid}/validation",
        json={"days": 7, "note": "Kalibrovkadan keyin tekshirildi"},
        headers=users["approver"],
    )
    assert rec.status_code == 201, rec.text
    body = rec.json()
    assert body["verdict"] == "pass" and body["valid_until"] is not None
    assert body["validated_by"] == "approver" and body["metrics"]["calibrated"] is True
    assert all(c["ok"] for c in body["checks"])
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["validation"]["status"] == "validated" and st["validation"]["note"] == ""
    assert st["validation"]["validated_by"] == "approver"


def test_expired_and_failed_and_version_change(client, users):
    """Muddat o'tishi, mos kelmagan verdikt va model versiyasi o'zgarishi holatlari."""
    pid = users["project_id"]
    sens = _setup(client, users)
    _write_history(pid, sens)
    client.post(
        f"/api/projects/{pid}/calibration/run", json={"days": 7, "apply": True}, headers=users["engineer"]
    )
    rec = client.post(f"/api/projects/{pid}/validation", json={"days": 7}, headers=users["approver"]).json()
    # 1) muddat o'tdi → expired + bildirishnoma (bir marta)
    with SessionLocal() as db:
        row = db.get(ValidationRecord, rec["id"])
        row.valid_until = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
        project = db.get(Project, pid)
        assert validation.status(db, project)["status"] == "expired"
        assert validation.tick_expiry(db) == 1
        assert validation.tick_expiry(db) == 0
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["validation"]["status"] == "expired" and "muddati" in st["validation"]["note"]
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    items = n if isinstance(n, list) else n.get("items", [])
    assert any(x["kind"] == "twin" and "validatsiyasi muddati" in x["title"] for x in items)
    # 2) qattiqroq mezon bilan yangi yozuv → fail
    strict = client.post(
        f"/api/projects/{pid}/validation",
        json={"days": 7, "criteria": {"rmse_pct_of_rated": 0.0001}},
        headers=users["approver"],
    ).json()
    assert strict["verdict"] == "fail" and strict["valid_until"] is None
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["validation"]["status"] == "failed" and "mos emas" in st["validation"]["note"]
    # 3) model versiyasi o'zgarsa — o'tgan yozuv amal qilmaydi
    ok = client.post(f"/api/projects/{pid}/validation", json={"days": 7}, headers=users["approver"]).json()
    assert ok["verdict"] == "pass"
    with SessionLocal() as db:
        db.get(ValidationRecord, ok["id"]).version_id = 9999
        db.commit()
        project = db.get(Project, pid)
        stt = validation.status(db, project)
        assert stt["status"] == "expired" and "versiyasi o'zgargan" in stt["note"]
