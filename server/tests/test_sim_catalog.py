"""Simulyatsiya katalogi, maydon pasporti, maxsus shablonlar, oldindan to'ldirish, egizak xavfsizlik."""

import pytest
from test_sim import wait_done


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "GES"},
        headers=users["engineer"],
    )
    return r.json()["id"]


def test_catalog_and_site_schema(client, users):
    r = client.get("/api/sim/catalog", headers=users["viewer"])
    assert r.status_code == 200
    d = r.json()
    ids = {k["id"] for k in d["kinds"]}
    assert {
        "water_hammer",
        "dam_stability",
        "flood",
        "landslide",
        "seismic",
        "custom",
        "hydro",
    } <= ids
    assert d["groups"]["favqulodda"]
    assert any(f["key"] == "intensity" for f in d["site_fields"])
    assert client.get("/api/sim/catalog").status_code == 401


def test_generic_kind_job_runs(client, users, model_id):
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "water_hammer", "params": {"close_s": 3, "sim_s": 10}},
        headers=users["viewer"],
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["name"] == "Gidravlik zarba (bosim oshishi)"
    assert job["params"]["length_m"] == 300  # defaultlar to'ldirilgan
    j = wait_done(client, users["viewer"], job["id"])
    assert j["status"] == "done", j["error"]
    assert j["summary"]["h_max_m"] > j["summary"]["h0_m"]
    res = client.get(f"/api/sim/{job['id']}/result", headers=users["viewer"]).json()
    assert "profile" in res and len(res["series"]["t"]) > 10
    # Xato parametr — darhol 400
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "water_hammer", "params": {"length_m": -5}},
        headers=users["viewer"],
    )
    assert r.status_code == 400 and "kamida" in r.json()["detail"]
    r = client.post(
        f"/api/models/{model_id}/sim", json={"kind": "nope", "params": {}}, headers=users["viewer"]
    )
    assert r.status_code == 400


def test_site_profile_roundtrip_and_prefill(client, users, model_id):
    pid = users["project_id"]
    r = client.get(f"/api/projects/{pid}/site", headers=users["viewer"])
    assert r.status_code == 200 and r.json()["filled"] is False
    vals = r.json()["values"]
    vals.update(
        {
            "intensity": "9",
            "dam_height_m": 100,
            "crest_elevation_m": 950,
            "base_elevation_m": 850,
            "normal_level_m": 940,
            "max_level_m": 947,
            "soil": "clay",
            "powerhouse_floor_m": 846,
            "tailwater_flood_m": 845,
        }
    )
    assert (
        client.put(f"/api/projects/{pid}/site", json=vals, headers=users["viewer"]).status_code
        == 403
    )
    r = client.put(f"/api/projects/{pid}/site", json=vals, headers=users["engineer"])
    assert r.status_code == 200, r.text
    assert r.json()["values"]["dam_height_m"] == 100
    risks = r.json()["risks"]
    assert any("Seysmiklik" in x["name"] and x["ok"] is False for x in risks)
    assert any("Mashina zali" in x["name"] for x in risks)
    # Validatsiya
    bad = dict(vals, dam_height_m=-1)
    assert (
        client.put(f"/api/projects/{pid}/site", json=bad, headers=users["engineer"]).status_code
        == 400
    )
    # Oldindan to'ldirish: pasport → dam_stability maydonlari
    r = client.get(
        f"/api/models/{model_id}/sim/prefill",
        params={"kind": "dam_stability"},
        headers=users["viewer"],
    )
    assert r.status_code == 200
    d = r.json()
    assert d["site_filled"] and d["site"]["height_m"] == 100 and d["site"]["headwater_m"] == 940
    r = client.get(
        f"/api/models/{model_id}/sim/prefill", params={"kind": "seismic"}, headers=users["viewer"]
    )
    assert r.json()["site"]["intensity"] == "9" and r.json()["site"]["water_depth_m"] == 90
    # Egizak xavfsizlik ko'rsatkichlari (sensor yo'q — faqat pasport)
    tw = client.get(f"/api/projects/{pid}/twin", headers=users["viewer"]).json()
    assert any("Gerb zaxirasi" in s["name"] for s in tw["safety"])


def test_custom_template_crud_and_job(client, users, model_id):
    pid = users["project_id"]
    ex = client.get("/api/sim/custom-example", headers=users["viewer"]).json()
    # Sinov (saqlamasdan)
    r = client.post(
        "/api/sim/custom-preview",
        json={"template": ex, "inputs": {"Q_in": 50}},
        headers=users["viewer"],
    )
    assert r.status_code == 200 and r.json()["summary"]["H_min"] < 900
    bad = dict(ex, step=[{"target": "x", "expr": "__import__('os')"}])
    assert (
        client.post(
            "/api/sim/custom-preview", json={"template": bad}, headers=users["viewer"]
        ).status_code
        == 400
    )
    # CRUD
    assert (
        client.post(
            f"/api/projects/{pid}/sim-templates",
            json={"name": "T", "template": ex},
            headers=users["viewer"],
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{pid}/sim-templates",
            json={"name": "T", "template": bad},
            headers=users["engineer"],
        ).status_code
        == 400
    )
    r = client.post(
        f"/api/projects/{pid}/sim-templates",
        json={"name": "Ombor balansi", "template": ex},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    lst = client.get(f"/api/projects/{pid}/sim-templates", headers=users["viewer"]).json()
    assert [t["id"] for t in lst] == [tid]
    r = client.put(
        f"/api/sim-templates/{tid}",
        json={"name": "Ombor balansi 2", "template": ex},
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["name"] == "Ombor balansi 2"
    # Ish: template_id bilan
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "custom", "params": {"template_id": tid, "inputs": {"Q_in": 200}}},
        headers=users["viewer"],
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["name"] == "Ombor balansi 2" and "template" in job["params"]
    j = wait_done(client, users["viewer"], job["id"])
    assert j["status"] == "done", j["error"]
    assert j["summary"]["H_max"] > 905
    # inline shablon
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "custom", "params": {"template": ex}},
        headers=users["viewer"],
    )
    assert r.status_code == 202
    assert (
        client.post(
            f"/api/models/{model_id}/sim",
            json={"kind": "custom", "params": {}},
            headers=users["viewer"],
        ).status_code
        == 400
    )
    # O'chirish: boshqa muhandis emas, muallif yoki tasdiqlovchi
    assert client.delete(f"/api/sim-templates/{tid}", headers=users["viewer"]).status_code == 403
    assert client.delete(f"/api/sim-templates/{tid}", headers=users["approver"]).status_code == 204
    assert client.get(f"/api/sim-templates/{tid}", headers=users["viewer"]).status_code == 404


def test_prefill_rejects_foreign_version(client, users, model_id, ifc_file):
    """IDOR: boshqa loyiha versiyasi orqali Pset parametrlarini olib bo'lmasin."""
    from conftest import upload

    r = client.post("/api/projects", json={"name": "Begona"}, headers=users["admin"])
    other_pid = r.json()["id"]
    client.put(
        f"/api/projects/{other_pid}/members",
        json={"user_id": users["ids"]["outsider"], "role": "engineer"},
        headers=users["admin"],
    )
    mid = client.post(
        f"/api/projects/{other_pid}/models", json={"name": "M"}, headers=users["outsider"]
    ).json()["id"]
    v = upload(client, users["outsider"], mid, ifc_file, "x").json()
    r = client.get(
        f"/api/models/{model_id}/sim/prefill",
        params={"kind": "dam_stability", "version_id": v["id"]},
        headers=users["viewer"],
    )
    assert r.status_code == 400


def test_prefill_uses_draft_objects_and_materials(client, users, model_id):
    """Web 3D da yaratilgan to'g'on qoralamasi simulyatsiya formasiga uzatiladi; materiallar katalogi."""
    r = client.post(
        f"/api/models/{model_id}/drafts",
        json={
            "kind": "dam",
            "name": "T",
            "params": {"length": 90, "height": 35, "crest": 5, "mu": 0.1, "md": 0.7},
            "transform": {"x": 0, "y": 0, "z": 850, "rz": 0},
            "psets": {"Pset_GES_Dam": {"BetonKlassi": "B30"}},
            "mesh": {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]]},
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    pf = client.get(
        f"/api/models/{model_id}/sim/prefill", params={"kind": "cracking"}, headers=users["viewer"]
    ).json()
    m = pf["model"]
    assert m["height_m"] == 35 and m["crest_width_m"] == 5 and m["upstream_slope"] == 0.1
    assert m["base_elev_m"] == 850 and m["concrete_class"] == "B30"
    cat = client.get("/api/sim/materials", headers=users["viewer"]).json()
    assert any(c["id"] == "B30" for c in cat["concrete"]) and cat["steel"] and cat["zones"]


def test_sim_sweep(client, users):
    r = client.post(
        "/api/sim/sweep",
        json={"kind": "dam_stability", "params": {}, "key": "headwater_m", "values": [10, 20, 30]},
        headers=users["viewer"],
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["key"] == "headwater_m" and len(d["rows"]) == 3
    assert all(r["error"] is None for r in d["rows"])
    fs = [r["summary"]["fs_overturning"] for r in d["rows"]]
    assert fs[0] >= fs[1] >= fs[2]  # sath oshsa — ag'darilish zaxirasi kamayadi
    assert (
        client.post(
            "/api/sim/sweep",
            json={"kind": "dam_stability", "params": {}, "key": "verdict_x", "values": [1, 2]},
            headers=users["viewer"],
        ).status_code
        == 400
    )


def test_safety_check_runs_all_scenarios(client, users):
    """Xavfsizlik tekshiruvi: pasport (Chorvoq preset) bilan barcha ssenariylar hisoblanadi, ishlar saqlanadi."""
    project_id = users["project_id"]
    r = client.post(
        f"/api/projects/{project_id}/twin", headers=users["engineer"], json={"preset": "maket"}
    )
    assert r.status_code == 201, r.text
    mid = r.json()["model_id"]
    r = client.post(f"/api/models/{mid}/sim/safety-check", headers=users["viewer"])
    assert r.status_code == 200, r.text
    d = r.json()
    ids = {row["id"] for row in d["rows"]}
    assert {
        "flood_design",
        "flood_check",
        "flood_n1",
        "seismic",
        "stab_static",
        "stab_seismic",
        "seepage",
        "water_hammer",
    } <= ids
    assert all(row["status"] in ("ok", "warn", "fail", "skip") for row in d["rows"])
    assert sum(1 for row in d["rows"] if row["status"] == "skip") <= 2, [
        r for r in d["rows"] if r["status"] == "skip"
    ]
    assert 0 <= d["score"] <= 100
    # maket: tekshiruv toshqinida gerbdan oshadi (30 m suv tashlagich) — fail
    fc = next(row for row in d["rows"] if row["id"] == "flood_check")
    assert fc["status"] == "fail" and fc["job_id"]
    jobs = client.get(f"/api/models/{mid}/sim", headers=users["viewer"]).json()
    assert sum(1 for j in jobs if j["name"].startswith("Xavfsizlik:")) == len(
        [x for x in d["rows"] if x["job_id"]]
    )
    assert client.get(f"/api/sim/{fc['job_id']}/result", headers=users["viewer"]).status_code == 200
    assert len(client.get("/api/sim/safety-scenarios", headers=users["viewer"]).json()) == len(
        d["rows"]
    )
