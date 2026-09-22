"""I1: model kalibrovkasi — sintetik ma'lumotda ma'lum parametr tiklanadi, qoldiq kuzatiladi,
drift aniqlanadi va kalibrovkalanmagan model natijasi shunday belgilanadi."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import upload
from ges_server.db import SessionLocal
from ges_server.monitoring import calibration, twin
from ges_server.orm import Project, ReadingHourly, Sensor

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"

TRUE_ROUGHNESS = 0.9  # mm (pasportda 0.1 — eskirgan quvur)
TRUE_EFF = 0.885  # pasportda odatda 0.92


def _sensor(client, users, key, name, kind, unit, **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": name, "kind": kind, "unit": unit, **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _setup(client, users):
    """Model (Pset_GES_*) + byef sathlari, sarf va agregat quvvati sensorlari."""
    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]
    ).json()["id"]
    upload(client, users["engineer"], mid, SAMPLE, "v1")
    return {
        "up": _sensor(client, users, "RES.LEVEL", "Yuqori byef", "level", "m"),
        "dn": _sensor(client, users, "TW.LEVEL", "Quyi byef", "level", "m"),
        "q": _sensor(client, users, "PEN.Q", "Quvur sarfi", "flow", "m3/s"),
        "p1": _sensor(client, users, "AGG1.P", "Agregat 1 quvvati", "power", "MW", high_alarm=200),
    }


def _write_history(pid: int, sens: dict, hours: int = 72, bias_factor: float = 1.0) -> float:
    """Sintetik soatlik tarix: ma'lum parametrlar bilan hisoblangan quvvat (+ ixtiyoriy siljish).
    Qaytaradi: yozilgan namunalar soni."""
    with SessionLocal() as db:
        project = db.get(Project, pid)
        params = twin.model_params(db, pid)
        assert params is not None
        theta = {"penstock_roughness_mm": TRUE_ROUGHNESS, "eff": {1: TRUE_EFF}}
        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=hours
        )
        rows = []
        for i in range(hours):
            hour = base + timedelta(hours=i)
            up = 900 + (i % 7) * 0.8  # sath va sarf o'zgarib turadi — parametr ajratilsin
            down = 800.0
            q = 35 + (i % 11) * 2.5
            sample = {"up": up, "down": down, "flow": q, "powers": {1: 1.0}}
            p = calibration.predict(sample, params, theta)[1] * bias_factor
            for s, v in ((sens["up"], up), (sens["dn"], down), (sens["q"], q), (sens["p1"], p)):
                rows.append(
                    ReadingHourly(sensor_id=s["id"], hour=hour, n=60, avg=v, min=v, max=v)
                )
        db.add_all(rows)
        # so'nggi qiymatlar ham (twin.compute jonli qiymatdan o'qiydi)
        for s, v in (
            (sens["up"], 903.0),
            (sens["dn"], 800.0),
            (sens["q"], 45.0),
            (sens["p1"], 30.0),
        ):
            row = db.get(Sensor, s["id"])
            row.last_value, row.last_ts, row.stale = v, datetime.now(timezone.utc), False
        db.commit()
        _ = project
    return hours


def test_calibration_recovers_known_parameters(client, users):
    """Qabul mezoni: sintetik ma'lumotda kalibrovka ma'lum parametrni tiklaydi."""
    pid = users["project_id"]
    sens = _setup(client, users)
    _write_history(pid, sens)
    with SessionLocal() as db:
        project = db.get(Project, pid)
        rec = calibration.run(db, project, user_id=None, days=7, apply=True)
        db.commit()
        assert rec.status == "ok" and rec.n_points >= 72
        after = rec.params_after
        # FIK quvvat o'lchovidan aniqlanadi va tiklanadi
        assert abs(after["eff"][1] - TRUE_EFF) < 0.01, after
        # Qisqa quvurda g'adir-budurlik FIK bilan kollinear — u aniqlanmaydi va pasport qiymatida qoladi
        diag = rec.diagnostics
        assert diag["max_efficiency"]["identifiable"] is True
        assert diag["penstock_roughness_mm"]["identifiable"] is False
        assert "ajratilmaydi" in diag["penstock_roughness_mm"]["note"]
        assert after["penstock_roughness_mm"] == rec.params_before["penstock_roughness_mm"]
        assert "aniqlanmadi" in rec.note
        assert rec.rmse_after < 0.15 and rec.rmse_after < rec.rmse_before
        assert rec.improvement_pct > 50 and rec.applied
        # qo'llangandan keyin loyiha parametrlari yangilanadi
        db.refresh(project)
        assert project.calibration["run_id"] == rec.id
        res = calibration.residuals(db, project, days=7)
        assert res["status"] == "ok" and abs(res["bias_mw"]) < 0.05


def test_uncalibrated_model_is_marked_and_api_flow(client, users):
    """Kalibrovkalanmagan natija belgilanadi; API orqali kalibrovka, qo'llash va bekor qilish."""
    pid = users["project_id"]
    sens = _setup(client, users)
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "insufficient"
    _write_history(pid, sens)
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "ok" and st["calibrated"] is False
    assert "kalibrovkalanmagan" in st["model_note"]
    state = client.get(f"/api/projects/{pid}/calibration", headers=users["viewer"]).json()
    assert state["current"] == {} and state["residuals"]["status"] == "uncalibrated"
    # ko'ruvchi kalibrovka qila olmaydi
    assert (
        client.post(
            f"/api/projects/{pid}/calibration/run", json={"days": 7}, headers=users["viewer"]
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/projects/{pid}/calibration/run",
        json={"days": 7, "apply": False},
        headers=users["engineer"],
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "ok" and run["applied"] is False and run["improvement_pct"] > 50
    # hali qo'llanmagan — egizak eski parametrlar bilan
    assert client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()["calibrated"] is False
    ap = client.post(f"/api/calibration/{run['id']}/apply", headers=users["engineer"])
    assert ap.status_code == 200 and ap.json()["current"]["run_id"] == run["id"]
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["calibrated"] and st["model_note"] == ""
    assert st["calibration"]["eff"]["1"] < 0.92  # pasportdagi 0.92 emas — kalibrovkalangan FIK
    assert run["diagnostics"]["max_efficiency"]["identifiable"] is True
    # kalibrovkalangan model bilan og'ish kamayadi (jonli nuqta ham modelga yaqin)
    hist = client.get(f"/api/projects/{pid}/calibration", headers=users["viewer"]).json()
    assert len(hist["runs"]) == 1 and hist["runs"][0]["applied"] is True
    # bekor qilish
    assert client.delete(f"/api/projects/{pid}/calibration", headers=users["engineer"]).status_code == 200
    assert client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()["calibrated"] is False


def test_insufficient_data_and_drift_detection(client, users):
    """Ma'lumot kam bo'lsa kalibrovka bajarilmaydi; keyin qoldiq siljisa drift aniqlanadi."""
    pid = users["project_id"]
    sens = _setup(client, users)
    with SessionLocal() as db:
        project = db.get(Project, pid)
        rec = calibration.run(db, project, user_id=None, days=7)
        db.commit()
        assert rec.status == "insufficient" and "yetarli emas" in rec.note
    _write_history(pid, sens)
    with SessionLocal() as db:
        project = db.get(Project, pid)
        calibration.run(db, project, user_id=None, days=7, apply=True)
        db.commit()
    # endi o'lchov 6 % ga pasayadi (degradatsiya yoki sensor siljishi) → drift
    with SessionLocal() as db:
        for row in db.query(ReadingHourly).filter_by(sensor_id=sens["p1"]["id"]).all():
            row.avg *= 0.94
        db.commit()
    with SessionLocal() as db:
        project = db.get(Project, pid)
        res = calibration.residuals(db, project, days=7)
        assert res["status"] == "drifted" and res["bias_mw"] < 0
        assert "Qayta kalibrovka" in res["advice"]
        assert calibration.tick_drift(db) == 1
        db.refresh(project)
        assert project.calibration.get("drift_notified_at")
        assert calibration.tick_drift(db) == 0  # takroriy bildirishnoma yo'q
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    items = n if isinstance(n, list) else n.get("items", [])
    assert any(x["kind"] == "twin" and "siljidi" in x["title"] for x in items)
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["calibration"]["drifted"] is True and "siljigan" in st["model_note"]


def test_roughness_is_identifiable_on_long_penstock():
    """Uzun/tor quvurda napor yo'qotishi sezilarli — g'adir-budurlik o'lchovdan ajraladi va tiklanadi
    (qisqa quvurda esa FIK bilan kollinear bo'lib aniqlanmaydi — yuqoridagi testga qarang)."""
    params = {
        "penstocks": [{"length_m": 2200.0, "diameter_m": 2.0, "roughness_mm": 0.1}],
        "units": [
            {
                "name": "Agregat 1",
                "type": "Francis",
                "rated_power_mw": 20.0,
                "rated_head_m": 60.0,
                "rated_flow_m3s": 38.0,
                "max_efficiency": 0.92,
            }
        ],
    }
    true_theta = {"penstock_roughness_mm": 1.2, "eff": {1: 0.89}}
    rows = []
    for i in range(48):
        sample = {
            "up": 900 + (i % 5) * 1.5,
            "down": 800.0,
            "flow": 12 + (i % 9) * 2.0,  # sarf keng oraliqda — yo'qotish v² bilan ajraladi
            "powers": {1: 1.0},
        }
        sample["powers"] = {1: calibration.predict(sample, params, true_theta)[1]}
        rows.append(sample)
    prior = {"penstock_roughness_mm": 0.1, "eff": {1: 0.92}}
    theta, diag = calibration.fit(rows, params, prior, ("penstock_roughness_mm", "max_efficiency"))
    assert diag["penstock_roughness_mm"]["identifiable"] is True, diag
    assert abs(theta["penstock_roughness_mm"] - 1.2) < 0.2, theta
    assert abs(theta["eff"][1] - 0.89) < 0.01, theta
    assert calibration.rmse(rows, params, theta) < 0.05
