"""C3: ISA-18.2 §10 ratsionalizatsiya maydonlari, tasdiqlash, chegara o'zgarsa bekor, hisobot."""

from conftest import ingest_headers


def _sensor(client, users, key, **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": key, "kind": "level", "unit": "m", **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


RAT = {
    "cause": "Kiruvchi sarf ko'paydi / zatvor yopiq",
    "consequence": "Suv tashlagichdan nazoratsiz oqim, quyi byef toshqini",
    "corrective_action": "Zatvorni oching, dispetcherga xabar bering",
    "response_time_s": 600,
    "priority_basis": "ISA-18.2 oqibat jadvali: xavfsizlik — yuqori",
}


def test_rationalization_report_and_confirm(client, users):
    pid = users["project_id"]
    a = _sensor(client, users, "RES.H", high_alarm=905.0, priority="critical")
    b = _sensor(client, users, "AGG1.P", roc_limit_per_min=5.0)
    _sensor(client, users, "TW.H")  # chegarasiz — hisobotga kirmaydi
    r = client.get(f"/api/projects/{pid}/alarms/rationalization", headers=users["viewer"])
    assert r.status_code == 200
    rep = r.json()
    assert rep["total"] == 2 and rep["rationalized"] == 0
    assert [x["key"] for x in rep["unrationalized"]] == ["RES.H", "AGG1.P"]  # critical birinchi
    assert "cause" in rep["unrationalized"][0]["missing"] and "rationalized" in rep["unrationalized"][0]["missing"]
    # matnlar PATCH bilan to'ldirilsa ham tasdiqlanmaguncha "rationalized" yetishmaydi
    r = client.patch(f"/api/sensors/{a['id']}", json={"cause": RAT["cause"]}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["cause"] == RAT["cause"] and r.json()["rationalized_at"] is None
    # tasdiqlash: viewer yo'q, to'liq bo'lmagan 422, muhandis OK
    assert client.post(f"/api/sensors/{a['id']}/rationalize", json=RAT, headers=users["viewer"]).status_code == 403
    assert client.post(f"/api/sensors/{a['id']}/rationalize", json={**RAT, "consequence": ""}, headers=users["engineer"]).status_code == 422
    r = client.post(f"/api/sensors/{a['id']}/rationalize", json=RAT, headers=users["engineer"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["rationalized_by"] == users["ids"]["engineer"] and j["rationalized_at"] and j["response_time_s"] == 600
    rep = client.get(f"/api/projects/{pid}/alarms/rationalization", headers=users["viewer"]).json()
    assert rep["rationalized"] == 1 and [x["key"] for x in rep["unrationalized"]] == ["AGG1.P"]
    # alarm hodisasi ratsionalizatsiya matnlarini olib yuradi
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 906}], headers=ingest_headers(client, users))
    ev = client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
    assert ev[0]["corrective_action"] == RAT["corrective_action"] and ev[0]["response_time_s"] == 600
    # chegara o'zgarsa tasdiq bekor (qayta ko'rib chiqish), matnlar qoladi
    r = client.patch(f"/api/sensors/{a['id']}", json={"high_alarm": 907}, headers=users["engineer"])
    assert r.json()["rationalized_at"] is None and r.json()["cause"] == RAT["cause"]
    rep = client.get(f"/api/projects/{pid}/alarms/rationalization", headers=users["viewer"]).json()
    assert [x["key"] for x in rep["unrationalized"]] == ["RES.H", "AGG1.P"]
    assert rep["unrationalized"][0]["missing"] == ["rationalized"]
    # nom o'zgarishi tasdiqni buzmaydi
    client.post(f"/api/sensors/{a['id']}/rationalize", json=RAT, headers=users["engineer"])
    r = client.patch(f"/api/sensors/{a['id']}", json={"name": "Yuqori byef"}, headers=users["engineer"])
    assert r.json()["rationalized_at"] is not None
    # admin hisoboti — barcha loyihalar; admin bo'lmagan 403
    assert client.get("/api/admin/alarms/rationalization", headers=users["engineer"]).status_code == 403
    rep = client.get("/api/admin/alarms/rationalization", headers=users["admin"]).json()
    assert rep["total"] == 2 and [x["key"] for x in rep["unrationalized"]] == ["AGG1.P"]
    assert b["id"] == rep["unrationalized"][0]["id"]
