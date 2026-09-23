"""OPS-03: og'ir ishlar so'rovdan navbatga — /qto, /clashes, /fragments 202 {job_id,status} → 200;
yiqilgan hisob xatosi; katta IFC metadata si fonda; viewer yangi konvertatsiyalari rate limit."""

import time

import pytest
from conftest import get_ready, upload
from ges_server.config import get_settings
from ges_server.db import SessionLocal
from ges_server.models import fragments, geometry, ifc_meta
from ges_server.orm import Job


@pytest.fixture
def no_precompute(monkeypatch):
    monkeypatch.setattr(get_settings(), "precompute_geometry", False)


@pytest.fixture
def vid(client, users, ifc_file, no_precompute):
    mid = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "J"}, headers=users["engineer"]).json()["id"]
    return upload(client, users["engineer"], mid, ifc_file).json()["id"]


def test_qto_and_clash_go_through_queue(client, users, vid):
    r = client.get(f"/api/versions/{vid}/qto", headers=users["viewer"])
    assert r.status_code == 202 and r.headers["Retry-After"]
    job_id = r.json()["job_id"]
    assert r.json()["status"] in ("queued", "running")
    # takror so'rov — o'sha ish (yangi hisob yo'q)
    r2 = client.get(f"/api/versions/{vid}/qto", headers=users["viewer"])
    assert r2.status_code == 200 or r2.json()["job_id"] == job_id
    q = get_ready(client, f"/api/versions/{vid}/qto", users["viewer"])
    assert q.status_code == 200 and "elements" in q.json()
    c = get_ready(client, f"/api/versions/{vid}/clashes?types_a=IfcWall", users["viewer"])
    assert c.status_code == 200 and "clashes" in c.json()
    with SessionLocal() as db:
        kinds = {j.kind for j in db.query(Job).all()}
    assert {"qto", "clash"} <= kinds


def test_failed_computation_reports_error(client, users, vid, monkeypatch):
    def boom(path):
        raise RuntimeError("geometriya buzuq")

    monkeypatch.setattr(geometry, "compute_qto", boom)
    r = get_ready(client, f"/api/versions/{vid}/qto", users["viewer"])
    assert r.status_code == 422 and "geometriya buzuq" in r.json()["detail"]


def test_fragments_queued_not_in_request(client, users, vid, monkeypatch):
    import threading

    req_thread = threading.get_ident()
    seen = {}

    def fake_convert(ifc, sha, timeout_s=1800):
        seen["thread"] = threading.get_ident()
        out = fragments.frag_path(sha)
        out.write_bytes(b"FRAG" * 64)
        return out

    monkeypatch.setattr(fragments, "available", lambda: True)
    monkeypatch.setattr(fragments, "convert", fake_convert)
    sha = client.get(f"/api/versions/{vid}", headers=users["viewer"]).json()["file_sha256"]
    fragments.frag_path(sha).unlink(missing_ok=True)
    with SessionLocal() as db:  # yuklashda qo'yilgan ish (Node yo'q edi) — yangidan
        db.query(Job).filter(Job.kind == "fragments").delete()
        db.commit()
    r = client.get(f"/api/versions/{vid}/fragments", headers=users["viewer"])
    assert r.status_code == 202
    r = get_ready(client, f"/api/versions/{vid}/fragments", users["viewer"])
    assert r.status_code == 200 and r.content.startswith(b"FRAG")
    assert seen["thread"] != req_thread
    fragments.frag_path(sha).unlink(missing_ok=True)


def test_viewer_new_conversions_rate_limited(client, users, vid, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_derived_per_min", 1)
    monkeypatch.setattr(geometry, "compute_clashes", lambda *a, **k: time.sleep(0.5) or {"clashes": []})
    assert client.get(f"/api/versions/{vid}/clashes?types_a=IfcWall", headers=users["viewer"]).status_code in (200, 202)
    assert client.get(f"/api/versions/{vid}/clashes?types_a=IfcSlab", headers=users["viewer"]).status_code == 429


@pytest.fixture
def fed_id(client, users, ifc_file, no_precompute):
    pid = users["project_id"]
    mids = [client.post(f"/api/projects/{pid}/models", json={"name": n}, headers=users["engineer"]).json()["id"] for n in ("FA", "FB")]
    for m in mids:
        assert upload(client, users["engineer"], m, ifc_file).status_code == 201
    body = {"name": "F", "members": [{"model_id": mids[0]}, {"model_id": mids[1], "dx": 0.5}]}
    r = client.post(f"/api/projects/{pid}/federations", json=body, headers=users["engineer"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_federation_clashes_go_through_queue(client, users, fed_id, monkeypatch):
    """OPS-03: federatsiya to'qnashuvi so'rov ichida hisoblanmaydi — `fedclash` ishi, 202 → 200 (keshdan)."""
    import threading

    from ges_server.models import federation

    req_thread = threading.get_ident()
    seen = {}
    real = federation.clashes

    def spy(resolved, tolerance=0.0, cross_only=True):
        seen["thread"] = threading.get_ident()
        return real(resolved, tolerance, cross_only)

    monkeypatch.setattr(federation, "clashes", spy)
    url = f"/api/federations/{fed_id}/clashes"
    r = client.get(url, headers=users["viewer"])
    assert r.status_code == 202 and r.headers["Retry-After"] and set(r.json()) == {"job_id", "status"}, r.text
    rep = get_ready(client, url, users["viewer"])
    assert rep.status_code == 200 and "clashes" in rep.json() and rep.json()["cross_only"] is True
    assert seen["thread"] != req_thread
    with SessionLocal() as db:
        assert db.query(Job).filter(Job.kind == "fedclash").count() == 1
    assert client.get(url, headers=users["viewer"]).status_code == 200  # kesh — navbatsiz
    # chegaradan tashqari tolerance (juftlar portlashi) — 422
    assert client.get(f"{url}?tolerance=5", headers=users["viewer"]).status_code == 422


def test_federation_clashes_rate_limited_and_failure(client, users, fed_id, monkeypatch):
    from ges_server.models import federation

    monkeypatch.setattr(get_settings(), "rate_derived_per_min", 1)

    def boom(*a, **k):
        raise RuntimeError("federatsiya geometriyasi buzuq")

    monkeypatch.setattr(federation, "clashes", boom)
    url = f"/api/federations/{fed_id}/clashes"
    assert client.get(f"{url}?tolerance=0.01", headers=users["viewer"]).status_code == 202
    assert client.get(f"{url}?tolerance=0.02", headers=users["viewer"]).status_code == 429  # yangi hisob — cheklangan
    r = get_ready(client, f"{url}?tolerance=0.01", users["viewer"])  # kuzatish cheklanmaydi
    assert r.status_code == 409 and "buzuq" in r.json()["detail"]


def test_big_ifc_meta_deferred(client, users, ifc_file, monkeypatch, no_precompute):
    monkeypatch.setattr(ifc_meta, "META_SYNC_MAX_BYTES", 10)
    mid = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "Big"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file).json()
    assert v["meta"]["pending"] and v["meta"]["schema"] == "IFC4" and v["meta"]["element_count"] is None
    t0 = time.monotonic()
    while True:
        m = client.get(f"/api/versions/{v['id']}", headers=users["viewer"]).json()["meta"]
        if not m.get("pending"):
            break
        assert time.monotonic() - t0 < 60
        time.sleep(0.2)
    assert m["element_count"] == 3 and not any(w.startswith(ifc_meta.PENDING_WARNING) for w in m.get("warnings", []))


def test_big_non_ifc_rejected(client, users, tmp_path, monkeypatch):
    monkeypatch.setattr(ifc_meta, "META_SYNC_MAX_BYTES", 10)
    bad = tmp_path / "x.ifc"
    bad.write_bytes(b"not a step file" * 10)
    mid = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "Bad"}, headers=users["engineer"]).json()["id"]
    assert upload(client, users["engineer"], mid, bad).status_code == 400
