"""Version control (audit 2.1): optimistic concurrency (VCS-01), raqam poygasi (VCS-02), ISO 19650 kodlari
barcha versiya yaratish yo'llarida bir xil (yangi xato a)."""

import threading

import pytest
from conftest import make_ifc, upload
from ges_server.db import SessionLocal
from ges_server.models import router as models_router
from ges_server.orm import DraftObject

BOX = {
    "vertices": [[0, 0, 0], [4, 0, 0], [4, 2, 0], [0, 2, 0], [0, 0, 3], [4, 0, 3], [4, 2, 3], [0, 2, 3]],
    "faces": [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ],
}


@pytest.fixture
def mid(client, users):
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "M"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _two_versions(client, users, mid, tmp_path):
    v1 = upload(client, users["engineer"], mid, make_ifc(tmp_path / "a.ifc", wall_names=("A",)), "v1").json()
    v2 = upload(client, users["engineer"], mid, make_ifc(tmp_path / "b.ifc", wall_names=("B",)), "v2").json()
    return v1, v2


def _draft(client, users, mid, who="engineer"):
    r = client.post(f"/api/models/{mid}/drafts", json={"kind": "dam", "name": "D", "mesh": BOX}, headers=users[who])
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- VCS-01


def test_upload_stale_parent_409_with_head_id(client, users, mid, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    r = upload(client, users["engineer"], mid, make_ifc(tmp_path / "c.ifc", wall_names=("C",)), parent_id=v1["id"])
    assert r.status_code == 409
    assert r.json() == {"detail": models_router.HEAD_MOVED_MSG, "head_id": v2["id"]}
    assert r.headers["X-Head-Id"] == str(v2["id"])
    assert len(client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()) == 2


def test_commit_drafts_on_stale_base_409_keeps_drafts(client, users, mid, tmp_path):
    v1 = upload(client, users["engineer"], mid, make_ifc(tmp_path / "a.ifc"), "v1").json()
    did = _draft(client, users, mid)
    v2 = upload(client, users["approver"], mid, make_ifc(tmp_path / "b.ifc", wall_names=("B",)), "v2").json()
    r = client.post(f"/api/models/{mid}/drafts/commit", json={"base_version_id": v1["id"]}, headers=users["engineer"])
    assert r.status_code == 409 and r.json()["head_id"] == v2["id"]
    with SessionLocal() as db:
        assert db.get(DraftObject, did) is not None  # qoralama yo'qolmadi
    r = client.post(f"/api/models/{mid}/drafts/commit", json={"base_version_id": v2["id"]}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    assert r.json()["parent_id"] == v2["id"] and r.json()["number"] == 3


def test_commit_drafts_head_moves_during_build(client, users, mid, tmp_path, monkeypatch):
    """Qurish (og'ir) paytida boshqa commit keldi — yozishda 409, qoralamalar saqlanadi."""
    from ges_server.models import drafts as drafts_mod

    upload(client, users["engineer"], mid, make_ifc(tmp_path / "a.ifc"), "v1")
    did = _draft(client, users, mid)
    orig = drafts_mod.build_to_temp
    other = make_ifc(tmp_path / "b.ifc", wall_names=("B",))

    def slow_build(*a, **kw):
        res = orig(*a, **kw)
        assert upload(client, users["approver"], mid, other, "parallel").status_code == 201
        return res

    monkeypatch.setattr(drafts_mod, "build_to_temp", slow_build)
    r = client.post(f"/api/models/{mid}/drafts/commit", json={}, headers=users["engineer"])
    assert r.status_code == 409, r.text
    with SessionLocal() as db:
        assert db.get(DraftObject, did) is not None


def test_restore_with_expected_head(client, users, mid, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    r = client.post(f"/api/versions/{v1['id']}/restore?expected_head_id={v1['id']}", headers=users["engineer"])
    assert r.status_code == 409 and r.json()["head_id"] == v2["id"]
    r = client.post(f"/api/versions/{v1['id']}/restore?expected_head_id={v2['id']}", headers=users["engineer"])
    assert r.status_code == 201 and r.json()["parent_id"] == v2["id"]


def test_create_version_expected_head_mismatch_raises(users, mid, client, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    with SessionLocal() as db:
        from ges_server.orm import User

        u = db.get(User, users["ids"]["engineer"])
        with pytest.raises(models_router.HeadMoved) as ei:
            models_router.create_version(
                db, model_id=mid, user=u, parent_id=v1["id"], expected_head=v1["id"], file_sha256=v1["file_sha256"],
                file_name="x.ifc", file_size=1, meta={}, message="",
            )
        assert ei.value.head_id == v2["id"]


# ---------------------------------------------------------------- VCS-02


def test_ten_parallel_commits_no_500_contiguous_numbers(client, users, mid, tmp_path):
    files = [make_ifc(tmp_path / f"p{i}.ifc", wall_names=(f"W{i}",)) for i in range(10)]
    results: dict[int, object] = {}

    def run(i):
        results[i] = upload(client, users["engineer"], mid, files[i], message=f"c{i}")

    ts = [threading.Thread(target=run, args=(i,)) for i in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=120)
    codes = [r.status_code for r in results.values()]
    assert 500 not in codes and all(c in (201, 409) for c in codes), codes
    numbers = sorted(v["number"] for v in client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json())
    assert numbers == list(range(1, len(numbers) + 1))
    assert codes.count(201) == len(numbers) >= 8


@pytest.mark.parametrize("path", ["restore", "drafts"])
def test_retry_on_number_collision_other_paths(client, users, mid, tmp_path, monkeypatch, path):
    """restore / draft commit ham `_next_number` + qayta urinish orqali (ilgari max+1 → 500)."""
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    if path == "drafts":
        _draft(client, users, mid)
    orig = models_router._next_number
    calls = {"n": 0}

    def colliding(db, model_id):
        calls["n"] += 1
        return 1 if calls["n"] == 1 else orig(db, model_id)  # birinchi urinish — band raqam

    monkeypatch.setattr(models_router, "_next_number", colliding)
    if path == "restore":
        r = client.post(f"/api/versions/{v1['id']}/restore", headers=users["engineer"])
    else:
        r = client.post(f"/api/models/{mid}/drafts/commit", json={}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    assert r.json()["number"] == 3 and calls["n"] >= 2


def test_retry_exhausted_restore_gives_409(client, users, mid, tmp_path, monkeypatch):
    v1, _ = _two_versions(client, users, mid, tmp_path)
    monkeypatch.setattr(models_router, "_next_number", lambda db, model_id: 1)
    monkeypatch.setattr(models_router.time, "sleep", lambda s: None)
    r = client.post(f"/api/versions/{v1['id']}/restore", headers=users["engineer"])
    assert r.status_code == 409


# ---------------------------------------------------------------- yangi xato (a): ISO 19650 kodlari


def test_all_paths_set_suitability_and_revision(client, users, mid, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    assert (v1["suitability_code"], v1["revision_code"]) == ("S0", "P01")
    assert v2["revision_code"] == "P02"
    r = client.post(f"/api/versions/{v1['id']}/restore", headers=users["engineer"])
    assert (r.json()["suitability_code"], r.json()["revision_code"]) == ("S0", "P03")
    _draft(client, users, mid)
    r = client.post(f"/api/models/{mid}/drafts/commit", json={}, headers=users["engineer"])
    assert (r.json()["suitability_code"], r.json()["revision_code"]) == ("S0", "P04")
    import trimesh

    obj = tmp_path / "box.obj"
    trimesh.creation.box((1, 1, 1)).export(str(obj))
    with open(obj, "rb") as fh:
        r = client.post(
            f"/api/models/{mid}/versions/import-mesh",
            files={"file": ("box.obj", fh, "application/octet-stream")},
            headers=users["engineer"],
        )
    assert r.status_code == 201, r.text
    assert (r.json()["suitability_code"], r.json()["revision_code"]) == ("S0", "P05")


# ---------------------------------------------------------------- VCS-03


def _cr(client, users, mid, vid):
    r = client.post(f"/api/models/{mid}/change-requests", json={"version_id": vid, "title": "T"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    cr = r.json()
    r = client.post(f"/api/change-requests/{cr['id']}/reviews", json={"decision": "approve"}, headers=users["approver"])
    assert r.status_code == 201, r.text
    return cr


def test_merge_stale_cr_409(client, users, mid, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    cr1, cr2 = _cr(client, users, mid, v1["id"]), _cr(client, users, mid, v2["id"])
    assert client.post(f"/api/change-requests/{cr2['id']}/merge", headers=users["approver"]).status_code == 200
    r = client.post(f"/api/change-requests/{cr1['id']}/merge", headers=users["approver"])
    assert r.status_code == 409 and "eskirgan" in r.json()["detail"]
    assert client.get(f"/api/models/{mid}/published", headers=users["viewer"]).json()["id"] == v2["id"]
    assert client.get(f"/api/versions/{v1['id']}", headers=users["viewer"]).json()["state"] == "shared"


# ---------------------------------------------------------------- VCS-05


def test_published_and_archived_versions_immutable(client, users, mid, tmp_path):
    v1, v2 = _two_versions(client, users, mid, tmp_path)
    cr1 = _cr(client, users, mid, v1["id"])
    assert client.post(f"/api/change-requests/{cr1['id']}/merge", headers=users["approver"]).status_code == 200
    for body in ({"message": "boshqa"}, {"revision_code": "C05"}):
        r = client.patch(f"/api/versions/{v1['id']}", json=body, headers=users["approver"])
        assert r.status_code == 409, (body, r.text)
    # yorliq (tag) va yaroqlilik kodi o'zgaruvchan
    r = client.patch(f"/api/versions/{v1['id']}", json={"tag": "release-1", "suitability_code": "A2"}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["tag"] == "release-1" and r.json()["suitability_code"] == "A2"
    cr2 = _cr(client, users, mid, v2["id"])
    assert client.post(f"/api/change-requests/{cr2['id']}/merge", headers=users["approver"]).status_code == 200
    assert client.get(f"/api/versions/{v1['id']}", headers=users["viewer"]).json()["state"] == "archived"
    assert client.patch(f"/api/versions/{v1['id']}", json={"message": "x"}, headers=users["engineer"]).status_code == 409
    # wip versiya izohi hali o'zgaradi
    v3 = upload(client, users["engineer"], mid, make_ifc(tmp_path / "c.ifc", wall_names=("C",)), "v3").json()
    assert client.patch(f"/api/versions/{v3['id']}", json={"message": "tuzatildi"}, headers=users["engineer"]).status_code == 200


# ---------------------------------------------------------------- VCS-04 + yangi xato (c)


def test_drafts_owner_only_and_audited(client, users, mid, admin):
    from conftest import login, make_user

    uid = make_user(client, admin, "eng2")
    client.put(f"/api/projects/{users['project_id']}/members", json={"user_id": uid, "role": "engineer"}, headers=admin)
    eng2 = login(client, "eng2", "pass1234")
    did = _draft(client, users, mid)
    # boshqa muhandis o'zgartira/o'chira olmaydi
    assert client.patch(f"/api/drafts/{did}", json={"name": "x"}, headers=eng2).status_code == 403
    assert client.delete(f"/api/drafts/{did}", headers=eng2).status_code == 403
    # muallif — ha; tasdiqlovchi — ha
    assert client.patch(f"/api/drafts/{did}", json={"name": "A"}, headers=users["engineer"]).status_code == 200
    assert client.patch(f"/api/drafts/{did}", json={"name": "B"}, headers=users["approver"]).status_code == 200
    acts = client.get("/api/audit", params={"action": "draft.update"}, headers=admin).json()
    assert len(acts) == 2 and acts[0]["detail"]["fields"] == ["name"]
    assert client.delete(f"/api/drafts/{did}", headers=users["approver"]).status_code == 204


def test_commit_without_ids_commits_only_own_drafts(client, users, mid, tmp_path):
    upload(client, users["engineer"], mid, make_ifc(tmp_path / "a.ifc"), "v1")
    mine = _draft(client, users, mid, "engineer")
    theirs = _draft(client, users, mid, "approver")
    r = client.post(f"/api/models/{mid}/drafts/commit", json={}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    left = [d["id"] for d in client.get(f"/api/models/{mid}/drafts", headers=users["viewer"]).json()]
    assert left == [theirs] and mine not in left
    # boshqaning qoralamasini aniq id bilan — muhandis 403, tasdiqlovchi mumkin
    assert client.post(f"/api/models/{mid}/drafts/commit", json={"draft_ids": [theirs]}, headers=users["engineer"]).status_code == 403
    # muhandisda o'z qoralamasi yo'q — 400
    assert client.post(f"/api/models/{mid}/drafts/commit", json={}, headers=users["engineer"]).status_code == 400
    assert client.post(f"/api/models/{mid}/drafts/commit", json={"draft_ids": [theirs]}, headers=users["approver"]).status_code == 201
