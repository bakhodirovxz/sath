"""I2: holat baholash (Kalman) va ortiqcha o'lchovlarni solishtirish — qotgan sensorni aniqlash va
o'rnini bosish, quvvat/sarf manbalari orasidagi kelishmovchilik."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import upload
from ges_server.db import SessionLocal
from ges_server.monitoring import estimator
from ges_server.orm import Project, Sensor

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def _sensor(client, users, key, name, kind, unit, **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": name, "kind": kind, "unit": unit, **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _push(client, users, items):
    r = client.post(
        f"/api/projects/{users['project_id']}/readings", json=items, headers=users["engineer"]
    )
    assert r.status_code == 200, r.text
    return r.json()


def _site(client, users):
    """Maydon pasporti: ombor ko'zgu yuzasi (baho uchun kerak)."""
    r = client.put(
        f"/api/projects/{users['project_id']}/site",
        json={
            "area_km2": 2.0,
            "normal_level_m": 900,
            "crest_level_m": 905,
            # sath–hajm: 890→10, 900→30, 910→50 mln m³ (bir xil nishab) → yuza 2.0 km²
            "curve_elev": [890, 900, 910],
            "curve_vol": [10, 30, 50],
        },
        headers=users["engineer"],
    )
    assert r.status_code in (200, 201), r.text


def _plant(client, users):
    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]
    ).json()["id"]
    upload(client, users["engineer"], mid, SAMPLE, "v1")
    return {
        "up": _sensor(client, users, "RES.LEVEL", "Yuqori byef", "level", "m"),
        "dn": _sensor(client, users, "TW.LEVEL", "Quyi byef", "level", "m"),
        "qin": _sensor(client, users, "RES.QIN", "Kiruvchi sarf", "flow", "m3/s"),
        "q": _sensor(client, users, "PEN.Q", "Quvur sarfi", "flow", "m3/s"),
        "p1": _sensor(client, users, "AGG1.P", "Agregat 1 quvvati", "power", "MW", high_alarm=200),
        "ptot": _sensor(client, users, "PLANT.P", "Umumiy quvvat", "power", "MW", high_alarm=500),
    }


def test_balance_and_redundancy_checks(client, users):
    """Suv balansi va ortiqchalik: umumiy quvvat ↔ agregatlar, sarf o'lchagichi ↔ model."""
    pid = users["project_id"]
    _site(client, users)
    _plant(client, users)
    # ma'lumot yo'q → baho yo'q, taxmin qilinmaydi
    st = client.get(f"/api/projects/{pid}/estimator", headers=users["viewer"]).json()
    assert st["estimate"]["status"] == "insufficient" and st["checks"] == []
    _push(
        client,
        users,
        [
            {"key": "RES.LEVEL", "value": 900.0},
            {"key": "TW.LEVEL", "value": 800.0},
            {"key": "RES.QIN", "value": 60.0},
            {"key": "PEN.Q", "value": 60.0},
            {"key": "AGG1.P", "value": 50.0},
            {"key": "PLANT.P", "value": 50.2},
        ],
    )
    st = client.get(f"/api/projects/{pid}/estimator", headers=users["viewer"]).json()
    est = st["estimate"]
    assert est["status"] == "ok" and est["source"] == "measured"
    assert est["balance"]["net_m3s"] == 0.0 and est["balance"]["area_m2"] == 2_000_000.0
    assert abs(est["level_estimate_m"] - 900.0) < 0.05
    by = {c["name"]: c for c in st["checks"]}
    assert by["power_total"]["status"] == "ok"  # 50.2 ≈ 50 (chidamlilik 0.5 MW)
    assert by["penstock_flow"]["sources"][0]["value"] == 60.0
    # umumiy quvvat sensori 3 MW ga chetlashsa — kelishmovchilik
    _push(client, users, [{"key": "PLANT.P", "value": 53.5}])
    by = {
        c["name"]: c
        for c in client.get(f"/api/projects/{pid}/estimator", headers=users["viewer"]).json()["checks"]
    }
    assert by["power_total"]["status"] in ("alert", "alarm") and by["power_total"]["diff"] == 3.5
    # yozish: virtual sensorlar (muhandis)
    assert client.post(f"/api/projects/{pid}/estimator/run", headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/estimator/run", headers=users["engineer"])
    assert r.status_code == 200
    sensors = {x["key"]: x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()}
    assert "TWIN.EST.LEVEL" in sensors and "TWIN.CHK.POWER_TOTAL" in sensors
    assert sensors["TWIN.EST.LEVEL"]["last_quality"] == "good"
    assert sensors["TWIN.CHK.POWER_TOTAL"]["alarm"] != "ok"  # chegara tashqarisida


def test_frozen_level_sensor_is_detected_and_substituted(client, users):
    """Qabul mezoni: sensor «qotganda» holat baholovchi uni aniqlaydi va o'rnini bosadi."""
    pid = users["project_id"]
    _site(client, users)
    s = _plant(client, users)
    now = datetime.now(timezone.utc)
    # sath bir xil qiymatda qotib qolgan (6 ta o'lchov), lekin kiruvchi sarf chiqimdan ancha katta
    for i in range(6):
        ts = (now - timedelta(minutes=5 * (6 - i))).isoformat()
        _push(client, users, [{"key": "RES.LEVEL", "value": 900.0, "ts": ts}])
    _push(
        client,
        users,
        [
            {"key": "TW.LEVEL", "value": 800.0},
            {"key": "RES.QIN", "value": 260.0},  # +200 m³/s zaxira → sath ko'tarilishi kerak
            {"key": "PEN.Q", "value": 60.0},
            {"key": "AGG1.P", "value": 50.0},
        ],
    )
    with SessionLocal() as db:
        project = db.get(Project, pid)
        # birinchi qadam: Δt yo'q (holat saqlanmagan) — hali qotgan deb belgilanmaydi
        first = estimator.run(db, project)
        assert first["estimate"]["status"] == "ok"
        # ikkinchi qadam: soat orqaga surilgan holat bilan — balans 0.36 m ko'tarilish kutadi
        cfg = dict(project.dashboard or {})
        cfg["estimator"] = {
            "level": 900.0,
            "P": 4e-4,
            "ts": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        project.dashboard = cfg
        db.commit()
        est = estimator.estimate(db, project)
        assert est["frozen"] is True and est["source"] == "model"
        assert est["expected_change_m"] > 0.3  # 200 m³/s × 3600 / 2e6 ≈ 0.36 m
        assert est["level_estimate_m"] > 900.3  # baho o'rnini bosdi (o'lchov 900.0 da qotgan)
        assert est["innovation_m"] < -0.3
        res = estimator.run(db, project)
        assert res["estimate"]["frozen"] is True
        db.commit()
    sensors = {x["key"]: x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()}
    assert sensors["TWIN.EST.LEVEL"]["last_quality"] == "substituted"
    assert sensors["TWIN.EST.LEVEL"]["last_value"] > 900.3
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    items = n if isinstance(n, list) else n.get("items", [])
    assert any(x["kind"] == "twin" and "qotgan" in x["title"] for x in items)
    _ = s


def test_frozen_not_flagged_when_balance_is_flat(client, users):
    """Sath o'zgarmasligi kerak bo'lgan holatda (balans nolga yaqin) qotgan deb belgilanmaydi."""
    pid = users["project_id"]
    _site(client, users)
    _plant(client, users)
    now = datetime.now(timezone.utc)
    for i in range(6):
        ts = (now - timedelta(minutes=5 * (6 - i))).isoformat()
        _push(client, users, [{"key": "RES.LEVEL", "value": 900.0, "ts": ts}])
    _push(
        client,
        users,
        [
            {"key": "TW.LEVEL", "value": 800.0},
            {"key": "RES.QIN", "value": 60.0},  # kiruvchi = chiqim → sath o'zgarmaydi
            {"key": "PEN.Q", "value": 60.0},
            {"key": "AGG1.P", "value": 50.0},
        ],
    )
    with SessionLocal() as db:
        project = db.get(Project, pid)
        cfg = dict(project.dashboard or {})
        cfg["estimator"] = {
            "level": 900.0,
            "P": 4e-4,
            "ts": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        project.dashboard = cfg
        db.commit()
        est = estimator.estimate(db, project)
        assert est["frozen"] is False and est["source"] == "measured"
        assert abs(est["expected_change_m"]) < 0.01
        # aloqa uzilgan sensor ham model qadamiga o'tadi
        db.query(Sensor).filter_by(project_id=pid, key="RES.LEVEL").one().stale = True
        db.commit()
        est2 = estimator.estimate(db, project)
        assert est2["source"] == "model" and est2["level_measured_m"] is None
