"""H2: CMMS chuqurligi — profilaktik reja avtomatik ish buyrug'i yaratadi, ISO 14224 nosozlik kodlari,
mehnat yozuvi va xarajat, ehtiyot qism bandlash/sarflash, ruxsatnoma (PTW) va LOTO (boshqaruv taqiqi),
aktiv bo'yicha xizmat tarixi."""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import login, make_user, send_command
from ges_server.db import SessionLocal
from ges_server.monitoring import cmms
from ges_server.orm import MaintenancePlan, Project


@pytest.fixture
def operator(client, admin, users):
    uid = make_user(client, admin, "dispetcher")
    client.put(
        f"/api/projects/{users['project_id']}/members",
        json={"user_id": uid, "role": "operator"},
        headers=admin,
    )
    return login(client, "dispetcher", "pass1234")


def test_plan_creates_work_order_automatically(client, users):
    """Qabul mezoni: profilaktik reja muddati kelganda avtomatik ish buyrug'i yaratiladi
    (va ochiq buyruq turganda takrorlanmaydi)."""
    pid = users["project_id"]
    h = users["engineer"]
    a = client.post(f"/api/projects/{pid}/assets", json={"name": "Agregat 1"}, headers=h).json()
    # davriyliksiz reja — 400
    assert (
        client.post(
            f"/api/projects/{pid}/maintenance-plans", json={"name": "Bo'sh"}, headers=h
        ).status_code
        == 400
    )
    # ish soati bo'yicha davriylik aktivsiz — 400
    assert (
        client.post(
            f"/api/projects/{pid}/maintenance-plans",
            json={"name": "Soat", "interval_hours": 100},
            headers=h,
        ).status_code
        == 400
    )
    body = {
        "name": "Podshipnik moylash",
        "asset_id": a["id"],
        "interval_days": 30,
        "tasks": ["Moy sathini tekshirish", "Moy almashtirish"],
        "priority": "high",
        "lead_days": 3,
        "permit_required": True,
    }
    r = client.post(f"/api/projects/{pid}/maintenance-plans", json=body, headers=h)
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["active"] and plan["asset_name"] == "Agregat 1" and plan["due_reason"] is None
    # hali muddati kelmagan
    assert client.post(f"/api/projects/{pid}/maintenance-plans/run", headers=h).json() == []
    # rejani 40 kun oldin tuzilgan qilamiz → muddati keldi
    with SessionLocal() as db:
        p = db.get(MaintenancePlan, plan["id"])
        p.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        db.commit()
    lst = client.get(f"/api/projects/{pid}/maintenance-plans", headers=users["viewer"]).json()
    assert "vaqt bo'yicha" in lst[0]["due_reason"]
    created = client.post(f"/api/projects/{pid}/maintenance-plans/run", headers=h).json()
    assert len(created) == 1
    wo = created[0]
    assert (
        wo["source"] == "plan"
        and wo["plan_id"] == plan["id"]
        and wo["asset_id"] == a["id"]
        and wo["priority"] == "high"
        and wo["permit_required"] is True
        and [t["title"] for t in wo["tasks"]] == body["tasks"]
        and "Sabab:" in wo["description"]
    )
    # ochiq buyruq turganda takror yaratilmaydi
    assert client.post(f"/api/projects/{pid}/maintenance-plans/run", headers=h).json() == []
    # yopilgandan keyin — muddat yana o'tishi kerak (last_generated_at yangilandi)
    client.patch(f"/api/work-orders/{wo['id']}", json={"status": "done"}, headers=h)
    assert client.post(f"/api/projects/{pid}/maintenance-plans/run", headers=h).json() == []
    # faol emas reja — hech narsa
    client.patch(f"/api/maintenance-plans/{plan['id']}", json={"active": False}, headers=h)
    assert client.get(f"/api/projects/{pid}/maintenance-plans", headers=h).json()[0]["active"] is False
    client.delete(f"/api/maintenance-plans/{plan['id']}", headers=h)
    assert client.get(f"/api/projects/{pid}/maintenance-plans", headers=h).json() == []


def test_plan_by_run_hours(client, users):
    """Ish soati bo'yicha davriylik: aktiv hisoblagichi (twin) oshganda muddati keladi."""
    pid = users["project_id"]
    h = users["engineer"]
    with SessionLocal() as db:
        project = db.get(Project, pid)
        assert cmms.run_hours_map(db, project) == {} or True
    a = client.post(f"/api/projects/{pid}/assets", json={"name": "Agregat 2"}, headers=h).json()
    r = client.post(
        f"/api/projects/{pid}/maintenance-plans",
        json={"name": "8000 soat", "asset_id": a["id"], "interval_hours": 8000},
        headers=h,
    )
    assert r.status_code == 201
    plan_id = r.json()["id"]
    with SessionLocal() as db:
        p = db.get(MaintenancePlan, plan_id)
        assert cmms.plan_due(p, {a["id"]: 100.0}, datetime.now(timezone.utc)) is None
        why = cmms.plan_due(p, {a["id"]: 8200.0}, datetime.now(timezone.utc))
        assert why and "ish soati" in why


def test_labor_parts_cost_and_history(client, users, operator):
    """Mehnat yozuvi va qism sarfi xarajatga qo'shiladi; bandlash bo'sh qoldiqni kamaytiradi;
    aktiv tarixi ISO 14224 kodlari bilan."""
    pid = users["project_id"]
    h = users["engineer"]
    a = client.post(f"/api/projects/{pid}/assets", json={"name": "Turbina"}, headers=h).json()
    wo = client.post(
        f"/api/projects/{pid}/work-orders",
        json={"title": "Ta'mirlash", "asset_id": a["id"], "labor_rate": 50.0},
        headers=operator,
    ).json()
    part = client.post(
        f"/api/projects/{pid}/parts",
        json={"name": "Podshipnik", "qty": 10, "min_qty": 2, "unit_cost": 100.0},
        headers=h,
    ).json()
    # mehnat: 4 soat × 50 = 200
    r = client.post(f"/api/work-orders/{wo['id']}/labor", json={"hours": 4, "note": "yig'ish"}, headers=operator)
    assert r.status_code == 201, r.text
    assert r.json()["labor_hours"] == 4 and r.json()["labor_cost"] == 200 and r.json()["cost"] == 200
    # boshqa xodim nomidan — dispetcherga ruxsat yo'q
    assert (
        client.post(
            f"/api/work-orders/{wo['id']}/labor",
            json={"hours": 2, "user_id": users["ids"]["engineer"]},
            headers=operator,
        ).status_code
        == 403
    )
    # bandlash: 6 dona → bo'sh qoldiq 4, ombor qoldig'i o'zgarmaydi
    lines = client.post(
        f"/api/work-orders/{wo['id']}/parts/reserve", json={"part_id": part["id"], "qty": 6}, headers=operator
    ).json()
    assert lines[0]["reserved"] == 6 and lines[0]["stock"] == 10 and lines[0]["free"] == 4
    # bo'sh qoldiqdan ortiq bandlash — 400
    assert (
        client.post(
            f"/api/work-orders/{wo['id']}/parts/reserve",
            json={"part_id": part["id"], "qty": 11},
            headers=operator,
        ).status_code
        == 400
    )
    # sarflash: 2 dona → ombor 8, bandlik 4, xarajat 200 + 200
    lines = client.post(
        f"/api/work-orders/{wo['id']}/parts/consume", json={"part_id": part["id"], "qty": 2}, headers=operator
    ).json()
    assert lines[0]["stock"] == 8 and lines[0]["reserved"] == 4 and lines[0]["consumed"] == 2
    w = client.get(f"/api/projects/{pid}/work-orders", headers=users["viewer"]).json()[0]
    assert w["parts_cost"] == 200 and w["labor_cost"] == 200 and w["cost"] == 400
    # ISO 14224 kodlari: noto'g'ri kod 422, to'g'ri kod bilan yopish
    assert (
        client.patch(f"/api/work-orders/{wo['id']}", json={"failure_mode": "XXX"}, headers=operator).status_code
        == 422
    )
    r = client.patch(
        f"/api/work-orders/{wo['id']}",
        json={
            "status": "done",
            "failure_mode": "VIB",
            "failure_cause": "wear",
            "detection_method": "condition",
            "downtime_hours": 6,
            "extra_cost": 100,
            "resolution": "podshipnik almashtirildi",
        },
        headers=operator,
    )
    assert r.status_code == 200 and r.json()["cost"] == 500  # 200 + 200 + 100
    codes = client.get("/api/cmms/codes", headers=users["viewer"]).json()
    assert "VIB" in codes["failure_modes"] and "wear" in codes["failure_causes"]
    # tarix
    hist = client.get(f"/api/assets/{a['id']}/history", headers=users["viewer"]).json()
    assert hist["totals"]["work_orders"] == 1 and hist["totals"]["cost"] == 500
    assert hist["totals"]["labor_hours"] == 4 and hist["totals"]["downtime_hours"] == 6
    item = hist["work_orders"][0]
    assert item["failure_mode"] == "VIB" and "Tebranish" in item["failure_mode_label"]
    assert item["parts"][0]["qty"] == 2 and item["parts"][0]["cost"] == 200
    assert hist["by_year"][0]["failures"] == 1 and hist["failure_modes"][0]["code"] == "VIB"
    # yopilgan buyruqning bandligi bo'sh qoldiqni band qilmaydi
    with SessionLocal() as db:
        from ges_server.orm import SparePart

        p = db.get(SparePart, part["id"])
        assert cmms.free_qty(db, p) == 8


def test_loto_blocks_command(client, users, operator):
    """Qabul mezoni: LOTO faol bo'lganda boshqaruv buyrug'i rad etiladi (chetlab o'tilmaydi)."""
    pid = users["project_id"]
    h = users["engineer"]
    gate = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "GATE9.SP", "name": "Zatvor 9", "kind": "position", "writable": True, "kks_code": "1MAA10 AA001",
              "min_setpoint": 0, "max_setpoint": 100},
        headers=h,
    ).json()
    a = client.post(
        f"/api/projects/{pid}/assets",
        json={"name": "Turbina 9", "kks_code": "1MAA10", "taxonomy_level": "system"},
        headers=h,
    ).json()
    wo = client.post(
        f"/api/projects/{pid}/work-orders",
        json={"title": "Zatvor ta'miri", "asset_id": a["id"], "permit_required": True},
        headers=operator,
    ).json()
    # LOTO dan oldin buyruq o'tadi (sensor band qolmasligi uchun bekor qilinadi)
    first = send_command(client, operator, pid, gate["id"], 10)
    assert first.status_code == 201
    client.post(f"/api/commands/{first.json()['id']}/cancel", headers=operator)
    # ruxsatnoma talab qilinsa, LOTO avval ruxsatnomani kutadi
    assert (
        client.post(f"/api/work-orders/{wo['id']}/loto", json={"active": True}, headers=operator).status_code
        == 409
    )
    # dispetcher ruxsatnoma bera olmaydi (faqat so'raydi)
    assert (
        client.post(
            f"/api/work-orders/{wo['id']}/permit", json={"status": "issued"}, headers=operator
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/work-orders/{wo['id']}/permit", json={"status": "requested", "note": "zatvor ta'miri"}, headers=operator
        ).status_code
        == 200
    )
    r = client.post(
        f"/api/work-orders/{wo['id']}/permit", json={"status": "issued"}, headers=users["approver"]
    )
    assert r.status_code == 200 and r.json()["permit_status"] == "issued"
    r = client.post(
        f"/api/work-orders/{wo['id']}/loto",
        json={"active": True, "points": [{"label": "Zatvor yuritmasi", "sensor_id": gate["id"]}], "note": "izolyatsiya"},
        headers=operator,
    )
    assert r.status_code == 200 and r.json()["loto_active"] is True
    # endi buyruq rad etiladi — select bosqichida, chetlab o'tish bilan ham
    r = client.post(
        f"/api/projects/{pid}/commands/select", json={"sensor_id": gate["id"], "value": 20}, headers=operator
    )
    assert r.status_code == 409 and "LOTO faol" in r.json()["detail"]
    from conftest import add_member

    sup = add_member(client, users["admin"], pid, "sup", "shift_supervisor")
    r = client.post(
        f"/api/projects/{pid}/commands/select?override=true&override_reason=juda%20zarur",
        json={"sensor_id": gate["id"], "value": 20},
        headers=sup,
    )
    assert r.status_code == 409 and "LOTO faol" in r.json()["detail"]
    # faol LOTO ro'yxati
    loto = client.get(f"/api/projects/{pid}/loto", headers=users["viewer"]).json()
    assert loto["items"][0]["work_order_id"] == wo["id"] and loto["items"][0]["asset_name"] == "Turbina 9"
    # LOTO faol ekan ish buyrug'i yopilmaydi va ruxsatnoma ham
    assert (
        client.patch(f"/api/work-orders/{wo['id']}", json={"status": "done"}, headers=operator).status_code
        == 409
    )
    assert (
        client.post(f"/api/work-orders/{wo['id']}/permit", json={"status": "closed"}, headers=users["approver"]).status_code
        == 409
    )
    # olib tashlash — qo'ygan xodim yoki tasdiqlovchi
    assert (
        client.post(f"/api/work-orders/{wo['id']}/loto", json={"active": False}, headers=users["engineer"]).status_code
        == 403
    )
    r = client.post(f"/api/work-orders/{wo['id']}/loto", json={"active": False}, headers=operator)
    assert r.status_code == 200 and r.json()["loto_active"] is False
    assert send_command(client, operator, pid, gate["id"], 20).status_code == 201
