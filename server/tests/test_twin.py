"""Raqamli egizak, boshqaruv buyruqlari, smena jurnali, aktivlar, vaqt mashinasi, operator roli."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import make_user, upload
from ges_server.db import SessionLocal
from ges_server.monitoring import twin
from ges_server.orm import Project

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


@pytest.fixture
def operator(client, admin, users):
    uid = make_user(client, admin, "operator")
    r = client.put(
        f"/api/projects/{users['project_id']}/members",
        json={"user_id": uid, "role": "operator"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    from conftest import login

    return login(client, "operator", "pass1234")


def _sensor(client, users, key, name, kind, unit, **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": name, "kind": kind, "unit": unit, **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_operator_role_permissions(client, users, operator):
    pid = users["project_id"]
    s = _sensor(client, users, "AGG1.P", "Agregat 1", "power", "MW", high_alarm=30)
    # operator o'lchov yubora olmaydi (muhandis+), lekin alarmni kvitlaydi va jurnal yozadi
    assert (
        client.post(
            f"/api/projects/{pid}/readings", json=[{"key": "AGG1.P", "value": 1}], headers=operator
        ).status_code
        == 401
    )
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 40}],
        headers=users["engineer"],
    )
    ev = client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=operator).json()
    assert ev and ev[0]["priority"] == "medium"
    assert (
        client.post(
            f"/api/alarm-events/{ev[0]['id']}/ack", json={"comment": "ok"}, headers=operator
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{pid}/journal",
            json={"text": "Smena qabul qilindi", "kind": "shift_start"},
            headers=operator,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/projects/{pid}/journal", json={"text": "x"}, headers=users["viewer"]
        ).status_code
        == 403
    )
    j = client.get(f"/api/projects/{pid}/journal", headers=users["viewer"]).json()
    assert j[0]["kind"] == "shift_start" and j[0]["author_username"] == "operator"
    # operator model tahrirlamaydi
    assert (
        client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=operator).status_code
        == 403
    )
    # ustuvorlik
    r = client.patch(
        f"/api/sensors/{s['id']}", json={"priority": "critical"}, headers=users["engineer"]
    )
    assert r.json()["priority"] == "critical"


def test_commands_gateway_flow(client, users, operator, admin):
    pid = users["project_id"]
    sp = _sensor(
        client,
        users,
        "GATE1.SP",
        "Zadvijka 1 ochilishi",
        "value",
        "%",
        writable=True,
        protocol="modbus",
        address={"register": 10},
    )
    ro = _sensor(client, users, "RES.H", "Sath", "level", "m")
    # writable emas → 400; viewer → 403
    assert (
        client.post(
            f"/api/projects/{pid}/commands",
            json={"sensor_id": ro["id"], "value": 1},
            headers=operator,
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/projects/{pid}/commands",
            json={"sensor_id": sp["id"], "value": 50},
            headers=users["viewer"],
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/projects/{pid}/commands",
        json={"sensor_id": sp["id"], "value": 50, "note": "50 % ga"},
        headers=operator,
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["status"] == "pending" and c["author_username"] == "operator"
    # ikkinchisi — 409 (bittasi bajarilmagan)
    assert (
        client.post(
            f"/api/projects/{pid}/commands",
            json={"sensor_id": sp["id"], "value": 60},
            headers=operator,
        ).status_code
        == 409
    )
    # gateway: kalit bilan oladi → sent
    key = client.get(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()[
        "ingest_key"
    ]
    assert client.get(f"/api/projects/{pid}/commands/pending").status_code == 401
    pend = client.get(f"/api/projects/{pid}/commands/pending", headers={"X-Ingest-Key": key}).json()
    assert (
        len(pend) == 1 and pend[0]["key"] == "GATE1.SP" and pend[0]["address"] == {"register": 10}
    )
    assert (
        client.get(f"/api/projects/{pid}/commands/pending", headers={"X-Ingest-Key": key}).json()
        == []
    )
    assert (
        client.get(f"/api/projects/{pid}/commands", headers=users["viewer"]).json()[0]["status"]
        == "sent"
    )
    # bekor qilib bo'lmaydi (sent)
    assert client.post(f"/api/commands/{c['id']}/cancel", headers=operator).status_code == 409
    r = client.post(
        f"/api/commands/{c['id']}/ack",
        json={"status": "acked", "result": "yozildi"},
        headers={"X-Ingest-Key": key},
    )
    assert r.status_code == 200 and r.json()["status"] == "acked"
    # tasdiqlovchiga bildirishnoma ketgan
    n = client.get("/api/notifications?unread=true", headers=users["approver"]).json()
    assert any("Buyruq" in x["title"] for x in n)
    # failed → muallifga bildirishnoma
    c2 = client.post(
        f"/api/projects/{pid}/commands", json={"sensor_id": sp["id"], "value": 20}, headers=operator
    ).json()
    client.get(f"/api/projects/{pid}/commands/pending", headers={"X-Ingest-Key": key})
    client.post(
        f"/api/commands/{c2['id']}/ack",
        json={"status": "failed", "result": "timeout"},
        headers={"X-Ingest-Key": key},
    )
    n = client.get("/api/notifications?unread=true", headers=operator).json()
    assert any("bajarilmadi" in x["title"] for x in n)
    # audit
    acts = [
        a["action"]
        for a in client.get(f"/api/audit?project_id={pid}&action=command.", headers=admin).json()
    ]
    assert "command.create" in acts and "command.acked" in acts and "command.failed" in acts


def test_twin_expected_power_and_deviation(client, users):
    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]
    ).json()["id"]
    upload(client, users["engineer"], mid, SAMPLE, "v1")
    up = _sensor(client, users, "RES.LEVEL", "Yuqori byef sathi", "level", "m")
    dn = _sensor(client, users, "TW.LEVEL", "Quyi byef sathi", "level", "m")
    q = _sensor(client, users, "PEN.Q", "Quvur sarfi", "flow", "m3/s")
    u1 = _sensor(client, users, "AGG1.P", "Agregat 1 quvvati", "power", "MW", high_alarm=200)
    # ma'lumot yo'q → insufficient
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "insufficient"
    # Namuna: Pset_GES_Turbine (namunada 3 ta agregat); napor ~ 100 m, sarf 62 → model quvvati
    client.post(
        f"/api/projects/{pid}/readings",
        json=[
            {"key": "RES.LEVEL", "value": 900},
            {"key": "TW.LEVEL", "value": 800},
            {"key": "PEN.Q", "value": 60},
            {"key": "AGG1.P", "value": 50},
        ],
        headers=users["engineer"],
    )
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "ok" and st["head_gross_m"] == 100 and len(st["units"]) == 1
    u = st["units"][0]
    assert u["running"] and u["expected_mw"] > 0 and u["flow_m3s"] == 60 and u["head_net_m"] < 100
    assert u["deviation_pct"] == pytest.approx(
        (50 - u["expected_mw"]) / u["expected_mw"] * 100, rel=1e-3
    )
    assert 0 < u["efficiency"] < 1.2
    # publish → virtual sensorlar (twin), og'ish alarmi (chegara ±10 %)
    r = client.post(f"/api/projects/{pid}/twin/run", headers=users["engineer"])
    assert r.status_code == 200
    sensors = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
    tw = {s["key"]: s for s in sensors if s["protocol"] == "twin"}
    assert f"TWIN.{u1['id']}.P_EXP" in tw and f"TWIN.{u1['id']}.DEV" in tw
    assert tw[f"TWIN.{u1['id']}.P_EXP"]["last_value"] == pytest.approx(u["expected_mw"], abs=0.01)
    dev = tw[f"TWIN.{u1['id']}.DEV"]
    assert (dev["alarm"] != "ok") == (abs(u["deviation_pct"]) > 10)
    # fon vazifa ham ishlaydi
    assert twin.tick_all() >= 1
    # «Nima bo'lsa»: sath 20 m pastroq → napor kam → kutilgan quvvat kam; hech narsa yozilmaydi
    base = client.post(
        f"/api/projects/{pid}/twin/what-if",
        json={"penstock_flow": 25},
        headers=users["viewer"],
    ).json()
    wi = client.post(
        f"/api/projects/{pid}/twin/what-if",
        json={"upstream_level": 880, "penstock_flow": 25},
        headers=users["viewer"],
    ).json()
    assert wi["what_if"] and wi["head_gross_m"] == 80
    assert wi["units"][0]["expected_mw"] < base["units"][0]["expected_mw"]
    assert wi["dispatch"]["status"] in ("ok", "infeasible", "idle")
    st2 = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st2["head_gross_m"] == 100  # jonli o'zgarmagan
    # Optimal rejim: joriy 50 MW uchun taqsimot (modelda 3 agregat)
    d = client.get(f"/api/projects/{pid}/twin/dispatch", headers=users["viewer"]).json()
    assert d["status"] == "ok" and abs(sum(x["power_mw"] for x in d["units"]) - 50) < 0.3
    d2 = client.get(
        f"/api/projects/{pid}/twin/dispatch", params={"target_mw": 60}, headers=users["viewer"]
    ).json()
    assert d2["status"] == "ok" and d2["units_on"] >= 1
    _ = (up, dn, q)


def test_assets_and_snapshot(client, users, operator):
    pid = users["project_id"]
    u1 = _sensor(client, users, "AGG1.P", "Agregat 1 quvvati", "power", "MW", high_alarm=200)
    now = datetime.now(timezone.utc)
    # 3 kun: 1-kun ishlamagan, 2-kun 12 soat ishlagan (2 marta ishga tushgan), bugun ishlayapti
    items = []
    d2 = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    for h in range(24):
        items.append(
            {
                "key": "AGG1.P",
                "value": 0,
                "ts": (d2 - timedelta(days=1) + timedelta(hours=h)).isoformat(),
            }
        )
    for h in range(24):
        on = (2 <= h < 8) or (12 <= h < 18)
        items.append(
            {"key": "AGG1.P", "value": 50 if on else 0, "ts": (d2 + timedelta(hours=h)).isoformat()}
        )
    items.append({"key": "AGG1.P", "value": 48})
    client.post(f"/api/projects/{pid}/readings", json=items, headers=users["engineer"])
    a = client.post(
        f"/api/projects/{pid}/assets",
        json={
            "name": "Agregat 1",
            "power_sensor_id": u1["id"],
            "maintenance_interval_hours": 8000,
            "base_run_hours": 7990,
        },
        headers=users["engineer"],
    )
    assert a.status_code == 201, a.text
    with SessionLocal() as db:
        assert twin.rollup_units(db) >= 2
        proj = db.get(Project, pid)
        st = twin.asset_status(db, proj)[0]
    assert st["starts_total"] == 2 and 11.9 <= st["run_hours_total"] - 7990 <= 12.5
    assert st["status"] in ("due", "overdue") and st["running"]
    # texnik xizmat → hisoblagich nol, holat ok
    r = client.post(
        f"/api/assets/{a.json()['id']}/maintenance?note=Moy%20almashtirildi", headers=operator
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "ok"
        and r.json()["hours_since_maintenance"] < 0.5
    )
    assert "Moy" in r.json()["notes"]
    # vaqt mashinasi: 2 kun oldin 15:00 → ishlagan (50), 10:00 → 0
    snap = client.get(
        f"/api/projects/{pid}/snapshot",
        params={"at": (d2 + timedelta(hours=15)).isoformat()},
        headers=users["viewer"],
    ).json()
    v = next(s for s in snap["sensors"] if s["key"] == "AGG1.P")
    assert v["value"] == 50 and v["alarm"] == "ok"
    snap = client.get(
        f"/api/projects/{pid}/snapshot",
        params={"at": (d2 + timedelta(hours=10)).isoformat()},
        headers=users["viewer"],
    ).json()
    assert next(s for s in snap["sensors"] if s["key"] == "AGG1.P")["value"] == 0
    # ma'lumot bo'lmagan davr → stale
    snap = client.get(
        f"/api/projects/{pid}/snapshot",
        params={"at": (d2 - timedelta(days=30)).isoformat()},
        headers=users["viewer"],
    ).json()
    assert next(s for s in snap["sensors"] if s["key"] == "AGG1.P")["alarm"] == "stale"


def test_asset_patch_rejects_foreign_sensor(client, users, admin):
    """IDOR: aktivga boshqa loyihaning sensori bog'lanmaydi."""
    pid = users["project_id"]
    a = client.post(
        f"/api/projects/{pid}/assets", json={"name": "A1"}, headers=users["engineer"]
    ).json()
    other = client.post("/api/projects", json={"name": "Boshqa GES"}, headers=admin).json()["id"]
    foreign = client.post(
        f"/api/projects/{other}/sensors",
        json={"key": "X.P", "name": "x", "kind": "power", "unit": "MW"},
        headers=admin,
    ).json()
    r = client.patch(
        f"/api/assets/{a['id']}", json={"power_sensor_id": foreign["id"]}, headers=users["engineer"]
    )
    assert r.status_code == 400
    mine = _sensor(client, users, "AGG1.P", "Agregat 1", "power", "MW")
    assert (
        client.patch(
            f"/api/assets/{a['id']}",
            json={"power_sensor_id": mine["id"]},
            headers=users["engineer"],
        ).status_code
        == 200
    )


def test_health_index_vibration_temperature_trend(client, users):
    """Holat monitoringi: ISO 10816-5 zonalari, harorat chegarasi, trend (RUL), anomaliya, sog'liq indeksi."""
    from ges_server.monitoring import health, historian

    pid = users["project_id"]
    vib = _sensor(client, users, "AGG1.VIB", "Agregat 1 tebranish", "vibration", "mm/s")
    tmp = _sensor(client, users, "AGG1.T", "Agregat 1 podshipnik", "temperature", "°C")
    now = datetime.now(timezone.utc)
    items = []
    # 20 kun: tebranish 2.0 → 3.8 mm/s (o'sib boradi), harorat 60 → 66 °C
    for d in range(20, 0, -1):
        for h in (0, 6, 12, 18):
            ts = (now - timedelta(days=d, hours=h)).isoformat()
            items.append({"key": "AGG1.VIB", "value": 2.0 + (20 - d) * 0.09, "ts": ts})
            items.append({"key": "AGG1.T", "value": 60 + (20 - d) * 0.3, "ts": ts})
    items.append({"key": "AGG1.VIB", "value": 3.9})
    items.append({"key": "AGG1.T", "value": 66})
    r = client.post(f"/api/projects/{pid}/readings", json=items, headers=users["engineer"])
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        historian.rollup(db, now)
    a = client.post(
        f"/api/projects/{pid}/assets",
        json={
            "name": "Agregat 1",
            "config": {
                "vibration_sensor_id": vib["id"],
                "bearing_temp_sensor_id": tmp["id"],
                "machine_group": 3,
                "temp_warn": 70,
                "temp_alarm": 80,
            },
        },
        headers=users["engineer"],
    )
    assert a.status_code == 201, a.text
    # begona sensor bilan config → 400 (IDOR)
    r = client.post("/api/projects", json={"name": "Begona2"}, headers=users["admin"])
    other = client.post(
        f"/api/projects/{r.json()['id']}/sensors",
        json={"key": "X", "name": "X", "kind": "vibration", "unit": "mm/s"},
        headers=users["admin"],
    ).json()
    assert (
        client.patch(
            f"/api/assets/{a.json()['id']}",
            json={"config": {"vibration_sensor_id": other["id"]}},
            headers=users["engineer"],
        ).status_code
        == 400
    )
    h = client.get(f"/api/projects/{pid}/health", headers=users["viewer"]).json()
    assert h["plant_score"] is not None and len(h["assets"]) == 1
    it = h["assets"][0]
    assert it["vibration"]["zone"] == "C"  # 3-guruh: 2.5–4.0 → C
    assert it["vibration"]["slope_per_day"] > 0 and it["vibration"]["days_to_d"] is not None
    assert it["bearing_temp"]["value"] == 66 and it["bearing_temp"]["days_to_alarm"] is not None
    assert it["score"] < 80 and any("C zona" in p for p in it["problems"])
    assert health.vib_zone(1.0, 1) == "A" and health.vib_zone(6.5, 2) == "D"
    assert 0.06 < health.thoma_critical("Francis", 380) < 0.07
    # publish → HEALTH.<id> virtual sensor
    r = client.post(f"/api/projects/{pid}/health/run", headers=users["engineer"])
    assert r.status_code == 200
    keys = [
        s["key"] for s in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
    ]
    assert f"HEALTH.{a.json()['id']}" in keys
    # Avto ish buyrug'i: harorat alarm → «yomon» → health-buyruq, ikkinchi marta takrorlanmaydi
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.T", "value": 85}],
        headers=users["engineer"],
    )
    with SessionLocal() as db:
        proj = db.get(Project, pid)
        created = health.auto_work_orders(db, proj, health.compute(db, proj))
        again = health.auto_work_orders(db, proj, health.compute(db, proj))
    assert created == 1 and again == 0
    wos = client.get(f"/api/projects/{pid}/work-orders", headers=users["viewer"]).json()
    assert (
        len(wos) == 1
        and wos[0]["source"] == "health"
        and wos[0]["priority"] in ("high", "critical")
    )


def test_work_orders_crud_kpi_permissions(client, users, operator):
    """Ish buyruqlari: yaratish (dispetcher), tayinlash (muhandis), holat, KPI, bildirishnoma."""
    pid = users["project_id"]
    a = client.post(
        f"/api/projects/{pid}/assets", json={"name": "Agregat 2"}, headers=users["engineer"]
    ).json()
    body = {
        "title": "Podshipnik tekshiruvi",
        "asset_id": a["id"],
        "priority": "high",
        "source": "health",
    }
    assert (
        client.post(
            f"/api/projects/{pid}/work-orders", json=body, headers=users["viewer"]
        ).status_code
        == 403
    )
    r = client.post(f"/api/projects/{pid}/work-orders", json=body, headers=operator)
    assert r.status_code == 201, r.text
    w = r.json()
    assert (
        w["status"] == "open"
        and w["asset_name"] == "Agregat 2"
        and w["author_username"] == "operator"
    )
    # begona aktiv → 400
    assert (
        client.post(
            f"/api/projects/{pid}/work-orders", json={**body, "asset_id": 9999}, headers=operator
        ).status_code
        == 400
    )
    # tayinlash: dispetcher qila olmaydi, muhandis qiladi; ijrochiga bildirishnoma
    eng_id = users["ids"]["engineer"]
    assert (
        client.patch(
            f"/api/work-orders/{w['id']}", json={"assignee_id": eng_id}, headers=operator
        ).status_code
        == 403
    )
    r = client.patch(
        f"/api/work-orders/{w['id']}", json={"assignee_id": eng_id}, headers=users["approver"]
    )
    assert r.status_code == 200 and r.json()["assignee_username"] == "engineer"
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    assert any(x["kind"] == "workorder" for x in (n if isinstance(n, list) else n.get("items", [])))
    # holat: bajarilmoqda → bajarildi (to'xtab turish, xarajat)
    r = client.patch(
        f"/api/work-orders/{w['id']}", json={"status": "in_progress"}, headers=operator
    )
    assert r.json()["started_at"] is not None
    r = client.patch(
        f"/api/work-orders/{w['id']}",
        json={
            "status": "done",
            "resolution": "Moy almashtirildi",
            "downtime_hours": 6,
            "cost": 1200,
        },
        headers=operator,
    )
    assert r.json()["closed_at"] is not None and r.json()["status"] == "done"
    lst = client.get(f"/api/projects/{pid}/work-orders", headers=users["viewer"]).json()
    assert len(lst) == 1 and lst[0]["resolution"] == "Moy almashtirildi"
    assert (
        client.get(
            f"/api/projects/{pid}/work-orders", params={"status": "open"}, headers=users["viewer"]
        ).json()
        == []
    )
    k = client.get(f"/api/projects/{pid}/work-orders/kpi", headers=users["viewer"]).json()
    assert k["done_90d"] == 1 and k["mttr_hours"] is not None and k["downtime_90d_hours"] == 6
    assert client.delete(f"/api/work-orders/{w['id']}", headers=operator).status_code == 403
    assert (
        client.delete(f"/api/work-orders/{w['id']}", headers=users["engineer"]).status_code == 204
    )


def test_flood_forecast_from_live_and_site(client, users):
    """Toshqin prognozi: pasport + jonli sath + yog'in → sath, gerbdan oshish, sath tushirish tavsiyasi."""
    pid = users["project_id"]
    up = _sensor(client, users, "RES.LEVEL", "Yuqori byef sathi", "level", "m")
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "RES.LEVEL", "value": 909}],
        headers=users["engineer"],
    )
    r = client.post(
        f"/api/projects/{pid}/twin/forecast", json={"rain_mm": 40}, headers=users["viewer"]
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["live"]["upstream_level"] == 909 and d["summary"]["max_level_m"] > 905
    assert d["recommendation"] is None or d["recommendation"]["action"] in ("watch", "pre_release")
    # Jadal jala (nam tuproq, darvozalar yopiq) → gerbdan oshish, oldindan tushirish tavsiyasi
    big = client.post(
        f"/api/projects/{pid}/twin/forecast",
        json={"rain_mm": 350, "amc": "III", "gate_opening": 0.0},
        headers=users["viewer"],
    ).json()
    assert big["summary"]["overtopped"] and big["recommendation"]["action"] == "pre_release"
    assert big["recommendation"]["hours_to_overtop"] is not None
    assert (
        client.post(
            f"/api/projects/{pid}/twin/forecast", json={"rain_mm": -1}, headers=users["viewer"]
        ).status_code
        == 422
    )
    _ = up


def test_spare_parts_and_ml_predictions(client, users, operator):
    """Ehtiyot qismlar: kirim/sarf, ish buyrug'i xarajati, minimal zaxira bildirishnomasi; ML bashoratlari → ML.* sensorlar."""
    pid = users["project_id"]
    body = {
        "name": "Podshipnik moyi",
        "code": "OIL-46",
        "unit": "l",
        "qty": 100,
        "min_qty": 40,
        "unit_cost": 5.5,
    }
    assert client.post(f"/api/projects/{pid}/parts", json=body, headers=operator).status_code == 403
    p = client.post(f"/api/projects/{pid}/parts", json=body, headers=users["engineer"]).json()
    assert p["qty"] == 100 and not p["low"]
    wo = client.post(
        f"/api/projects/{pid}/work-orders", json={"title": "Moy almashtirish"}, headers=operator
    ).json()
    # sarf (dispetcher) — buyruq xarajati oshadi; minimal zaxiradan tushsa bildirishnoma
    r = client.post(
        f"/api/parts/{p['id']}/move",
        json={"qty": -70, "work_order_id": wo["id"], "note": "almashtirish"},
        headers=operator,
    )
    assert r.status_code == 200 and r.json()["qty"] == 30 and r.json()["low"]
    assert (
        client.get(f"/api/projects/{pid}/work-orders", headers=operator).json()[0]["cost"]
        == 70 * 5.5
    )
    assert (
        client.post(f"/api/parts/{p['id']}/move", json={"qty": -50}, headers=operator).status_code
        == 400
    )
    assert (
        client.post(f"/api/parts/{p['id']}/move", json={"qty": 20}, headers=operator).status_code
        == 403
    )  # kirim — muhandis
    assert (
        client.post(
            f"/api/parts/{p['id']}/move", json={"qty": 20}, headers=users["engineer"]
        ).json()["qty"]
        == 50
    )
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    items = n if isinstance(n, list) else n.get("items", [])
    assert any(x["kind"] == "parts" for x in items)
    mv = client.get(f"/api/parts/{p['id']}/movements", headers=users["viewer"]).json()
    assert [m["qty"] for m in mv] == [20, -70, 100]
    # ML integratsiya nuqtasi
    r = client.post(
        f"/api/projects/{pid}/ml/predictions",
        json={
            "model": "rul-v1",
            "predictions": [
                {
                    "key": "AGG1.RUL",
                    "name": "Agregat 1 qolgan resurs",
                    "value": 42,
                    "unit": "kun",
                    "low_alarm": 30,
                }
            ],
        },
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["accepted"] == 1
    s = next(
        x
        for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
        if x["key"] == "ML.AGG1.RUL"
    )
    assert s["protocol"] == "ml" and s["last_value"] == 42 and s["alarm"] == "ok"
    client.post(
        f"/api/projects/{pid}/ml/predictions",
        json={"predictions": [{"key": "ML.AGG1.RUL", "value": 12}]},
        headers=users["engineer"],
    )
    s = next(
        x
        for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
        if x["key"] == "ML.AGG1.RUL"
    )
    assert s["alarm"] == "low"
