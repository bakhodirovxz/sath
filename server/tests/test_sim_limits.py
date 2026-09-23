"""J12: hisob byudjeti (400), foydalanuvchi kvotasi (429), alohida jarayonda vaqt chegarasi."""

import time

import pytest
from ges_server import config
from ges_server.sim import compute


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models", json={"name": "M"}, headers=users["engineer"]
    )
    return r.json()["id"]


def test_budget_exceeded_is_400_with_advice(client, users, model_id):
    # Roadmap holati: water_hammer(length_m=20, reaches=200, sim_s=120) — 120 s CPU da tugamasdi
    r = client.post(
        f"/api/models/{model_id}/sim",
        json={"kind": "water_hammer", "params": {"length_m": 20, "reaches": 200, "sim_s": 120}},
        headers=users["engineer"],
    )
    assert r.status_code == 400, r.text
    assert "chegara" in r.json()["detail"] and "reaches" in r.json()["detail"]
    for kind, params in (
        ("surge_tank", {"sim_s": 600}),
        ("governor", {"sim_s": 600}),
        ("flood", {"duration_h": 96}),
        ("transformer", {"days": 3}),
    ):
        r = client.post(
            f"/api/models/{model_id}/sim", json={"kind": kind, "params": params}, headers=users["engineer"]
        )
        assert r.status_code == 202, (kind, r.text)  # oddiy diapazon byudjetga sig'adi


def test_per_user_active_quota_429(client, users, model_id, monkeypatch):
    from ges_server import jobs

    monkeypatch.setattr(config.get_settings(), "sim_max_active_per_user", 2)
    # Ishchi bajarmaydi (L3 navbat) — ishlar queued/running holatda qoladi
    monkeypatch.setattr(jobs.runner, "_run_sim", lambda job_id: None)
    for _ in range(2):
        r = client.post(
            f"/api/models/{model_id}/sim", json={"kind": "seismic", "params": {}}, headers=users["engineer"]
        )
        assert r.status_code == 202, r.text
    r = client.post(
        f"/api/models/{model_id}/sim", json={"kind": "seismic", "params": {}}, headers=users["engineer"]
    )
    assert r.status_code == 429
    # boshqa foydalanuvchi kvotasi alohida
    r = client.post(
        f"/api/models/{model_id}/sim", json={"kind": "seismic", "params": {}}, headers=users["approver"]
    )
    assert r.status_code == 202


def test_isolated_run_returns_result_and_times_out():
    out = compute.run_isolated("seismic", {"intensity": "8"}, timeout_s=120)
    assert out["summary"]["kh"] > 0
    t = time.time()
    with pytest.raises(compute.SimTimeout):
        compute.run_isolated("_sleep", {"seconds": 30}, timeout_s=2)
    assert time.time() - t < 20  # jarayon o'ldirildi, 30 s kutilmadi
    with pytest.raises(RuntimeError, match="ValueError"):
        compute.run_isolated("seismic", {"ground": "Z"}, timeout_s=60)


def test_viewer_cannot_start_sim_403(client, users, model_id):
    """SIM-02: ishga tushirish (analitik, maxsus, CFD) — muhandis+; ko'ruvchi faqat natijani ko'radi."""
    for kind, params in (
        ("seismic", {}),
        ("custom", {"template": {"steps": 1, "step": [{"target": "x", "expr": "1"}]}}),
    ):
        r = client.post(
            f"/api/models/{model_id}/sim", json={"kind": kind, "params": params}, headers=users["viewer"]
        )
        assert r.status_code == 403, (kind, r.text)
    # OpenAPI tavsifi ham shuni aytadi (ilgari «analitik turlar — ko'ruvchi ham» deb yozilgan edi)
    desc = client.get("/openapi.json").json()["paths"]["/api/models/{model_id}/sim"]["post"]["description"]
    assert "muhandis+" in desc and "ko'ruvchi ham" not in desc and "ko'ruvchi 403" in desc


def test_isolated_child_memory_limit():
    """SIM-02: bola jarayonga xotira chegarasi (POSIX RLIMIT_AS / Windows Job Object)."""
    out = compute.run_isolated("_alloc", {"mb": 16}, timeout_s=120, mem_mb=512)
    assert out["summary"]["bytes"] == 16 * 1024 * 1024
    with pytest.raises(RuntimeError, match="MemoryError|xotira"):
        compute.run_isolated("_alloc", {"mb": 2048}, timeout_s=120, mem_mb=512)
