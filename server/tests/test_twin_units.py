"""SCADA-14: egizak agregatlari — barqaror raqamlash (1…12), sarfni taqsimlash, flow_source."""

from pathlib import Path

import pytest
from conftest import ingest_headers, upload
from ges_server.db import SessionLocal
from ges_server.monitoring import twin
from ges_server.orm import Project, Sensor

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def _sensor(client, users, key, name, kind, unit):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": name, "kind": kind, "unit": unit},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _read(client, users, **vals):
    client.post(
        f"/api/projects/{users['project_id']}/readings",
        json=[{"key": k.replace("_", "."), "value": v} for k, v in vals.items()],
        headers=ingest_headers(client, users),
    )


@pytest.fixture
def plant(client, users):
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]).json()["id"]
    upload(client, users["engineer"], mid, SAMPLE, "v1")  # 3 ta Turbina (25 MW, 62 m³/s)
    ids = {
        "up": _sensor(client, users, "RES.LEVEL", "Yuqori byef sathi", "level", "m"),
        "dn": _sensor(client, users, "TW.LEVEL", "Quyi byef sathi", "level", "m"),
        "q": _sensor(client, users, "PEN.Q", "Quvur sarfi", "flow", "m3/s"),
        "u1": _sensor(client, users, "AGG1.P", "Agregat 1 quvvati", "power", "MW"),
        "u3": _sensor(client, users, "AGG3.P", "Agregat 3 quvvati", "power", "MW"),  # 2-agregat yo'q
    }
    _read(client, users, RES_LEVEL=900, TW_LEVEL=800, PEN_Q=60, AGG1_P=40, AGG3_P=20)
    return pid, ids


def _state(client, users, pid):
    st = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert st["status"] == "ok", st
    return {u["unit"]: u for u in st["units"]}


def test_stable_unit_index_spec_and_calibration(client, users, plant):
    pid, _ids = plant
    with SessionLocal() as db:
        db.get(Project, pid).calibration = {"eff": {"2": 0.95, "3": 0.80}, "penstock_roughness_mm": 0.1}
        db.commit()
    u = _state(client, users, pid)
    assert sorted(u) == [1, 3]
    # eski xato: bo'sh slot tashlanib, 3-agregat specs[1] va eff[2] ni olardi
    assert u[3]["model_unit"] == "Turbina 3" and u[1]["model_unit"] == "Turbina 1"
    assert u[3]["expected_efficiency"] < u[1]["expected_efficiency"]  # eff[3] = 0.80 qo'llandi


def test_flow_split_proportional_and_sources(client, users, plant):
    pid, ids = plant
    u = _state(client, users, pid)
    # bir xil agregatlar: q_i ∝ P_i → 40 va 20 m³/s (eski: teng 30/30)
    assert u[1]["flow_source"] == "split" and u[1]["flow_m3s"] == pytest.approx(40.0)
    assert u[3]["flow_m3s"] == pytest.approx(20.0)
    assert u[1]["deviation_pct"] is not None and u[1]["efficiency"] is not None
    # agregat sarf sensori (mimika slot unit1_flow) — measured, qolgani 3-agregatga
    qf = _sensor(client, users, "AGG1.Q", "Agregat 1 sarfi", "flow", "m3/s")
    _read(client, users, AGG1_Q=35)
    with SessionLocal() as db:
        p = db.get(Project, pid)
        p.dashboard = {**(p.dashboard or {}), "mimic": {"unit1_flow": qf, "penstock_flow": ids["q"]}}
        db.commit()
    u = _state(client, users, pid)
    assert u[1]["flow_source"] == "measured" and u[1]["flow_m3s"] == pytest.approx(35.0)
    assert u[3]["flow_source"] == "split" and u[3]["flow_m3s"] == pytest.approx(25.0)
    # quvur sarfi ham yo'q (stale) → estimated: og'ish va FIK aylanma → None
    with SessionLocal() as db:
        for sid in (ids["q"], qf):
            db.get(Sensor, sid).stale = True
        db.commit()
    u = _state(client, users, pid)
    for n in (1, 3):
        assert u[n]["flow_source"] == "estimated"
        assert u[n]["deviation_pct"] is None and u[n]["efficiency"] is None
        assert u[n]["flow_m3s"] > 0  # quvvatdan nominal FIK bilan


def test_scheme_units_beyond_four(client, users, plant):
    pid, _ids = plant
    u7 = _sensor(client, users, "G7.MW", "Yettinchi agregat", "power", "MW")
    _read(client, users, G7_MW=10)
    with SessionLocal() as db:
        p = db.get(Project, pid)
        p.dashboard = {
            **(p.dashboard or {}),
            "scheme": {
                "version": 1,
                "units": 1,
                "elements": [{"id": "unit7", "type": "unit", "x": 1, "y": 1, "unit": 7, "sensor_id": u7}],
            },
        }
        db.commit()
    u = _state(client, users, pid)
    assert sorted(u) == [1, 3, 7] and u[7]["running"] and u[7]["measured_mw"] == 10
    # what-if: istalgan agregat raqami
    wi = client.post(
        f"/api/projects/{pid}/twin/what-if", json={"unit_power": {"7": 22}}, headers=users["viewer"]
    ).json()
    assert {x["unit"]: x for x in wi["units"]}[7]["measured_mw"] == 22
    with SessionLocal() as db:
        sensors = db.query(Sensor).filter_by(project_id=pid).all()
        p = db.get(Project, pid)
        rows = twin.unit_sensors(p, twin._slots(db, p, sensors), sensors)
        assert [n for n, _ps, _fs in rows] == [1, 3, 7]


def test_split_flow_weights_by_rating():
    from ges_sim.turbine import TurbineSpec

    big = TurbineSpec(rated_power_mw=50, rated_flow_m3s=100)
    small = TurbineSpec(rated_power_mw=10, rated_flow_m3s=25)  # Q/P kattaroq (past napor)
    s = twin.split_flow(90.0, {1: (25.0, big), 2: (5.0, small)}, {})
    # w1 = 25·100/50 = 50, w2 = 5·25/10 = 12.5 → 72 va 18
    assert s[1] == pytest.approx(72.0) and s[2] == pytest.approx(18.0)
    assert twin.split_flow(None, {1: (1.0, big)}, {}) == {}
    assert twin.split_flow(10.0, {1: (1.0, big), 2: (1.0, small)}, {1: 12.0}) == {}


def test_soft_deleted_model_excluded_from_twin(client, users):
    """VCS-06: o'chirilgan (soft delete) model versiyasi egizak parametrlariga kirmaydi."""
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]).json()["id"]
    upload(client, users["engineer"], mid, SAMPLE, "v1")
    with SessionLocal() as db:
        assert twin.model_params(db, pid) is not None
    r = client.delete(f"/api/models/{mid}", headers=users["approver"])
    assert r.status_code in (200, 204), r.text
    with SessionLocal() as db:
        assert twin.model_params(db, pid) is None
