from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def sensor(client, users):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={
            "key": "AGG1.P",
            "name": "Agregat 1 quvvat",
            "kind": "power",
            "unit": "MW",
            "high_alarm": 30,
            "low_alarm": 5,
            "element_guid": "abc",
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_sensor_crud_and_permissions(client, users, sensor):
    pid = users["project_id"]
    assert sensor["alarm"] == "stale" and sensor["last_value"] is None
    # viewer yarata olmaydi, ko'ra oladi
    r = client.post(
        f"/api/projects/{pid}/sensors", json={"key": "X", "name": "x"}, headers=users["viewer"]
    )
    assert r.status_code == 403
    assert [
        s["key"] for s in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
    ] == ["AGG1.P"]
    assert client.get(f"/api/projects/{pid}/sensors", headers=users["outsider"]).status_code == 403
    # takror kalit
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "AGG1.P", "name": "dup"},
        headers=users["engineer"],
    )
    assert r.status_code == 409
    # yangilash / o'chirish
    r = client.patch(
        f"/api/sensors/{sensor['id']}",
        json={"name": "Yangi", "high_alarm": 50},
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["name"] == "Yangi" and r.json()["high_alarm"] == 50
    assert (
        client.delete(f"/api/sensors/{sensor['id']}", headers=users["engineer"]).status_code == 403
    )
    assert (
        client.delete(f"/api/sensors/{sensor['id']}", headers=users["approver"]).status_code == 204
    )


def test_ingest_with_key_and_alarms(client, users, sensor):
    pid = users["project_id"]
    # kalit faqat tasdiqlovchi oladi
    assert (
        client.get(f"/api/projects/{pid}/ingest-key", headers=users["engineer"]).status_code == 403
    )
    key = client.get(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()[
        "ingest_key"
    ]
    assert (
        client.get(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()[
            "ingest_key"
        ]
        == key
    )

    # kalitsiz → 401; noto'g'ri kalit → 401
    assert (
        client.post(
            f"/api/projects/{pid}/readings", json=[{"key": "AGG1.P", "value": 20}]
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/projects/{pid}/readings",
            json=[{"key": "AGG1.P", "value": 20}],
            headers={"X-Ingest-Key": "yolg'on"},
        ).status_code
        == 401
    )

    r = client.post(
        f"/api/projects/{pid}/readings",
        json=[
            {"key": "AGG1.P", "value": 20},
            {"key": "NOMALUM", "value": 1},
            {"key": "AGG1.P", "value": "xato"},
        ],
        headers={"X-Ingest-Key": key},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": 1, "unknown": ["NOMALUM", "AGG1.P"]}
    s = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()[0]
    assert s["last_value"] == 20 and s["alarm"] == "ok" and s["last_ts"]

    # yuqori alarm
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 35}],
        headers={"X-Ingest-Key": key},
    )
    alarms = client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json()
    assert [a["alarm"] for a in alarms] == ["high"]
    # past alarm, keyin normal
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 2}],
        headers={"X-Ingest-Key": key},
    )
    assert (
        client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json()[0]["alarm"]
        == "low"
    )
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 10}],
        headers={"X-Ingest-Key": key},
    )
    assert client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json() == []

    # kalitni almashtirish → eski ishlamaydi
    new_key = client.post(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()[
        "ingest_key"
    ]
    assert new_key != key
    assert (
        client.post(
            f"/api/projects/{pid}/readings",
            json=[{"key": "AGG1.P", "value": 1}],
            headers={"X-Ingest-Key": key},
        ).status_code
        == 401
    )


def test_ingest_with_user_token(client, users, sensor):
    pid = users["project_id"]
    # muhandis tokeni bilan ham yuborsa bo'ladi, ko'ruvchi — yo'q
    r = client.post(
        f"/api/projects/{pid}/readings",
        json=[{"sensor_id": sensor["id"], "value": 12.5, "ts": "2026-01-01T10:00:00Z"}],
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["accepted"] == 1
    assert (
        client.post(
            f"/api/projects/{pid}/readings",
            json=[{"key": "AGG1.P", "value": 1}],
            headers=users["viewer"],
        ).status_code
        == 401
    )
    # eski vaqtli o'lchov last_value ni o'zgartirmaydi
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 99, "ts": "2020-01-01T00:00:00Z"}],
        headers=users["engineer"],
    )
    s = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()[0]
    assert s["last_value"] == 12.5


def test_csv_import_and_history_downsampling(client, users, sensor):
    now = datetime.now(timezone.utc)
    lines = ["ts,value"] + [
        f"{(now - timedelta(minutes=600 - i)).isoformat()},{i % 50}" for i in range(600)
    ]
    r = client.post(
        f"/api/sensors/{sensor['id']}/import",
        files={"file": ("data.csv", "\n".join(lines).encode(), "text/csv")},
        headers=users["engineer"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 600
    # to'liq
    r = client.get(
        f"/api/sensors/{sensor['id']}/readings?hours=24&limit=2000", headers=users["viewer"]
    ).json()
    assert r["total"] == 600 and len(r["points"]) == 600 and r["unit"] == "MW"
    # siyraklashtirilgan: 600 nuqta → ≤100 bo'lak, min/max saqlanadi
    r = client.get(
        f"/api/sensors/{sensor['id']}/readings?hours=24&limit=100", headers=users["viewer"]
    ).json()
    assert r["total"] == 600 and 90 <= len(r["points"]) <= 100
    assert all(p["min"] <= p["v"] <= p["max"] for p in r["points"])
    # vaqt oynasi tashqarisi
    r = client.get(f"/api/sensors/{sensor['id']}/readings?hours=1", headers=users["viewer"]).json()
    assert r["total"] in (59, 60)  # chegaradagi nuqta so'rov vaqtiga qarab
    # bo'sh CSV
    r = client.post(
        f"/api/sensors/{sensor['id']}/import",
        files={"file": ("x.csv", b"a,b\n", "text/csv")},
        headers=users["engineer"],
    )
    assert r.status_code == 400


def test_stale_detection(client, users, sensor):
    pid = users["project_id"]
    client.patch(
        f"/api/sensors/{sensor['id']}", json={"stale_after_s": 60}, headers=users["engineer"]
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    client.post(
        f"/api/projects/{pid}/readings",
        json=[{"key": "AGG1.P", "value": 10, "ts": old}],
        headers=users["engineer"],
    )
    alarms = client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json()
    assert [a["alarm"] for a in alarms] == ["stale"]


def test_websocket_snapshot_and_live(client, users, sensor):
    pid = users["project_id"]
    token = users["viewer"]["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"/api/projects/{pid}/live?token={token}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["sensors"][0]["key"] == "AGG1.P"
        r = client.post(
            f"/api/projects/{pid}/readings",
            json=[{"key": "AGG1.P", "value": 21.5}],
            headers=users["engineer"],
        )
        assert r.status_code == 200
        msg = ws.receive_json()
        assert (
            msg["type"] == "reading"
            and msg["value"] == 21.5
            and msg["alarm"] == "ok"
            and msg["element_guid"] == "abc"
        )
    # noto'g'ri token → yopiladi
    with pytest.raises(Exception):  # noqa: B017 — WebSocketDisconnect yoki ulanish rad
        with client.websocket_connect(f"/api/projects/{pid}/live?token=bad") as ws:
            ws.receive_json()


def test_sensor_csv_import_binds_elements(client, users):
    """CSV teglar importi: yaratish/yangilash, element nomi → GUID bog'lash (maket egizagi), xato qatorlar."""
    project_id = users["project_id"]
    r = client.post(
        f"/api/projects/{project_id}/twin", headers=users["engineer"], json={"preset": "maket"}
    )
    mid = r.json()["model_id"]
    csv = (
        "key;name;kind;unit;protocol;address;element;low;high\n"
        "GATE1.POS;Darvoza 1 ochilishi;position;%;mqtt;ges/gate1/pos;Darvoza 1;;\n"
        'AGG1.P;Agregat quvvati;power;MW;opcua;"ns=2;s=AGG1.P";5 Generator;0;22\n'
        "RES.LVL;Yuqori byef sathi;level;m;http;;To'g'on (beton og'irlik);218;243\n"
        ";nomsiz;value;;;;;;\n"
    )
    r = client.post(
        f"/api/projects/{project_id}/sensors/import",
        headers=users["engineer"],
        json={"csv": csv, "model_id": mid},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 3 and d["bound"] == 3 and len(d["errors"]) == 1, d
    sensors = {
        s["key"]: s
        for s in client.get(f"/api/projects/{project_id}/sensors", headers=users["viewer"]).json()
    }
    assert sensors["GATE1.POS"]["element_guid"] and sensors["GATE1.POS"]["kind"] == "position"
    assert sensors["GATE1.POS"]["address"] == {"topic": "ges/gate1/pos"}
    assert sensors["RES.LVL"]["high_alarm"] == 243.0
    # qayta import — yangilanadi, dublikat yo'q
    r = client.post(
        f"/api/projects/{project_id}/sensors/import",
        headers=users["engineer"],
        json={"csv": csv, "model_id": mid},
    )
    assert r.json()["updated"] == 3 and r.json()["created"] == 0
    assert (
        client.post(
            f"/api/projects/{project_id}/sensors/import", headers=users["viewer"], json={"csv": csv}
        ).status_code
        == 403
    )
