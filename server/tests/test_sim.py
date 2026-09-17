import time

import pytest
from conftest import upload


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "GES"},
        headers=users["engineer"],
    )
    return r.json()["id"]


def wait_done(client, headers, job_id, timeout=20):
    for _ in range(timeout * 10):
        j = client.get(f"/api/sim/{job_id}", headers=headers).json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("simulyatsiya tugamadi")


def test_example_params_and_run(client, users, model_id):
    params = client.get("/api/sim/example", headers=users["viewer"]).json()
    params["inflow_m3s"] = {"constant": 120, "steps": 30}
    # ko'ruvchi ham ishga tushira oladi
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"name": "Sinov", "params": params},
        headers=users["viewer"],
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in ("queued", "running", "done")
    assert job["params"]["dt_hours"] == 24

    j = wait_done(client, users["viewer"], job["id"])
    assert j["status"] == "done", j["error"]
    assert j["summary"]["steps"] == 30
    assert j["summary"]["energy_mwh"] > 0
    assert j["finished_at"] is not None

    res = client.get(f"/api/sim/{job['id']}/result", headers=users["viewer"]).json()
    assert len(res["series"]["level"]) == 30
    assert len(res["units"]) == 2

    lst = client.get(f"/api/models/{model_id}/sim", headers=users["viewer"]).json()
    assert [x["id"] for x in lst] == [job["id"]]
    assert lst[0]["params"] is None  # ro'yxatda parametrlar yo'q (yengil)


def test_invalid_params_rejected_immediately(client, users, model_id):
    params = client.get("/api/sim/example", headers=users["viewer"]).json()
    params["units"] = []
    r = client.post(f"/api/models/{model_id}/sim", json={"params": params}, headers=users["viewer"])
    assert r.status_code == 400
    assert "agregat" in r.json()["detail"].lower()
    r = client.post(f"/api/models/{model_id}/sim", json={"params": {}}, headers=users["viewer"])
    assert r.status_code == 400


def test_result_before_done_and_permissions(client, users, model_id):
    params = client.get("/api/sim/example", headers=users["viewer"]).json()
    params["inflow_m3s"] = {"constant": 100, "steps": 3}
    job = client.post(
        f"/api/models/{model_id}/sim", json={"params": params}, headers=users["engineer"]
    ).json()
    assert client.get(f"/api/sim/{job['id']}", headers=users["outsider"]).status_code == 403
    wait_done(client, users["engineer"], job["id"])
    # o'chirish: muallif yoki tasdiqlovchi
    assert client.delete(f"/api/sim/{job['id']}", headers=users["viewer"]).status_code == 403
    assert client.delete(f"/api/sim/{job['id']}", headers=users["engineer"]).status_code == 204
    assert client.get(f"/api/sim/{job['id']}", headers=users["engineer"]).status_code == 404


def test_ges_params_from_ifc(client, users, model_id):
    from pathlib import Path

    sample = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v1.ifc"
    v = upload(client, users["engineer"], model_id, sample, "namuna").json()
    r = client.get(f"/api/versions/{v['id']}/ges-params", headers=users["viewer"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["units"]) == 3
    assert p["units"][0]["type"] == "Francis" and p["units"][0]["rated_power_mw"] == 25.0
    assert len(p["penstocks"]) == 3 and p["penstocks"][0]["diameter_m"] == 2.4
    assert p["dams"][0]["height_m"] == 20.0


# ---------- CFD ----------


def test_cfd_status_and_validation(client, users, model_id):
    r = client.get("/api/sim/cfd-status", headers=users["viewer"])
    assert r.status_code == 200 and r.json()["mode"] in ("docker", "local", "worker", "off")
    bad = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "cfd", "params": {"kind": "penstock", "diameter_m": -2}},
        headers=users["viewer"],
    )
    assert bad.status_code == 400 and "musbat" in bad.json()["detail"]
    bad = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "boshqa", "params": {}},
        headers=users["viewer"],
    )
    assert bad.status_code == 400


def test_cfd_worker_mode_leaves_job_queued(client, users, model_id, monkeypatch):
    from ges_server import config

    monkeypatch.setattr(config.get_settings(), "cfd_mode", "worker")
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "cfd", "name": "Quvur", "params": {"kind": "penstock", "length_m": 10}},
        headers=users["engineer"],
    )
    assert r.status_code == 202, r.text
    job = client.get(f"/api/sim/{r.json()['id']}", headers=users["engineer"]).json()
    assert job["status"] == "queued" and job["kind"] == "cfd" and job["name"] == "Quvur"
    # worker navbatdan oladi
    from ges_server.sim.worker import next_job

    assert next_job() == job["id"]
    assert client.get(f"/api/sim/{job['id']}/log", headers=users["viewer"]).json() == {}


def test_cfd_off_mode(client, users, model_id, monkeypatch):
    from ges_server import config

    monkeypatch.setattr(config.get_settings(), "cfd_mode", "off")
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "cfd", "params": {"kind": "penstock"}},
        headers=users["engineer"],
    )
    assert r.status_code == 503


@pytest.mark.skipif(
    __import__("os").environ.get("GES_TEST_CFD") != "1", reason="GES_TEST_CFD=1 va docker kerak"
)
def test_cfd_real_run_via_api(client, users, model_id, monkeypatch):
    from ges_server import config

    monkeypatch.setattr(config.get_settings(), "cfd_mode", "docker")
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={
            "kind": "cfd",
            "params": {
                "kind": "penstock",
                "length_m": 8,
                "diameter_m": 2,
                "flow_m3s": 10,
                "resolution": 0.5,
                "max_iterations": 80,
            },
        },
        headers=users["engineer"],
    )
    assert r.status_code == 202, r.text
    j = wait_done(client, users["engineer"], r.json()["id"], timeout=600)
    assert j["status"] == "done", j["error"]
    assert j["summary"]["head_loss_m"] > 0 and j["summary"]["cells"]
    res = client.get(f"/api/sim/{j['id']}/result", headers=users["viewer"]).json()
    assert res["kind"] == "penstock" and len(res["axis"]["x"]) == 100 and len(res["plane"]) > 100
    logs = client.get(f"/api/sim/{j['id']}/log", headers=users["viewer"]).json()
    assert "log.simpleFoam" in logs
    assert client.delete(f"/api/sim/{j['id']}", headers=users["engineer"]).status_code == 204


def test_cfd_geometry_job_writes_stl(client, users, monkeypatch):
    """Model geometriyasi CFD: tanlangan elementlar → STL, bbox parametrlarga, case papkasida STL."""
    from pathlib import Path

    from conftest import upload
    from ges_server import config

    monkeypatch.setattr(config.get_settings(), "cfd_mode", "worker")
    sample = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"
    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]
    ).json()["id"]
    v = upload(client, users["engineer"], mid, sample, "namuna").json()
    q = client.get(f"/api/versions/{v['id']}/qto", headers=users["viewer"]).json()
    guid = next(e["guid"] for e in q["elements"] if e["name"] == "Suv tashlagich")
    # element tanlanmagan — 400
    bad = client.post(
        f"/api/models/{mid}/sim",
        json={"kind": "cfd", "version_id": v["id"], "params": {"kind": "geometry"}},
        headers=users["viewer"],
    )
    assert bad.status_code == 400 and "element_guids" in bad.json()["detail"]
    r = client.post(
        f"/api/models/{mid}/sim",
        json={
            "kind": "cfd",
            "version_id": v["id"],
            "name": "Tashlagich atrofida",
            "params": {"kind": "geometry", "element_guids": [guid], "velocity_ms": 1.5},
        },
        headers=users["viewer"],
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert (
        job["params"]["bbox"] == [[10.0, -17.0, 12.0], [22.0, -7.0, 13.0]]
        and job["params"]["stl_triangles"] == 12
    )
    stl = (
        config.get_settings().data_dir
        / "cfd"
        / str(job["id"])
        / "constant"
        / "triSurface"
        / "body.stl"
    )
    assert (
        stl.exists()
        and stl.read_text().startswith("solid body")
        and stl.read_text().count("facet normal") == 12
    )
