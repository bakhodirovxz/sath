"""G5: klassifikatsiya (IfcClassificationReference) va model federatsiyasi (ikki modeldagi to'qnashuv),
keng bosqich panjara indeksi (katta modellarda ham aniq tekshiruv)."""

import time
from pathlib import Path

import ifcopenshell
import numpy as np
from conftest import upload
from ges_server.models import classification, geometry

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def test_candidate_pairs_matches_brute_force():
    rng = np.random.default_rng(7)
    n = 900
    lo = rng.uniform(0, 500, (n, 3))
    hi = lo + rng.uniform(0.5, 12, (n, 3))
    hi[:3] = lo[:3] + 300  # bir nechta juda katta element
    boxes = [(lo[i], hi[i]) for i in range(n)]
    t = time.time()
    pairs = geometry.candidate_pairs(boxes, 0.1)
    dt = time.time() - t
    got = {tuple(p) for p in pairs.tolist()}
    exp = set()
    for i in range(n):
        for j in range(i + 1, n):
            if (lo[i] - 0.1 <= hi[j] + 0.1).all() and (lo[j] - 0.1 <= hi[i] + 0.1).all():
                exp.add((i, j))
    assert got == exp and len(exp) > 30
    assert dt < 5.0


def test_clashes_exact_on_large_model_count():
    """1500 dan ko'p element — ilgari faqat bbox; endi panjara bilan aniq (uchburchak) tekshiruv."""
    cube = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]])
    meshes = []
    for i in range(1600):
        off = np.array([(i % 40) * 3.0, (i // 40) * 3.0, 0.0])
        meshes.append(geometry.Mesh(f"g{i}", "IfcWall", f"k{i}", "", cube + off, faces))
    # bitta haqiqiy to'qnashuv: 0-kub ustiga yarim siljigan kub
    meshes.append(geometry.Mesh("x", "IfcSlab", "x", "", cube + np.array([0.5, 0.5, 0.5]), faces))
    rep = geometry.clashes_of(meshes)
    assert rep["exact"] is True and rep["hard"] == 1 and rep["element_count"] == 1601
    assert rep["clashes"][0]["kind"] == "hard" and {rep["clashes"][0]["a"]["guid"], rep["clashes"][0]["b"]["guid"]} == {"g0", "x"}


def test_classification_write_read(tmp_path):
    f = ifcopenshell.open(str(SAMPLE))
    assert classification.summary(f)["classified"] == 0
    info = classification.classify_file(f)
    assert info["assigned"] == 11 and info["by_code"]["GTS.01"] == 1 and info["by_code"]["USK.01"] == 3
    info2 = classification.classify_file(f, "Uniclass2015")
    assert info2["assigned"] == 11
    out = tmp_path / "c.ifc"
    f.write(str(out))
    g = ifcopenshell.open(str(out))
    dam = next(w for w in g.by_type("IfcWall") if w.Name == "To'g'on")
    refs = classification.references(dam)
    assert {(r["system"], r["code"]) for r in refs} == {("SATH-KSI", "GTS.01"), ("Uniclass2015", "Ss_20_05_15_25")}
    s = classification.summary(g)
    assert set(s["systems"]) == {"SATH-KSI", "Uniclass2015"} and s["classified"] == 11
    # takror — qo'shilmaydi
    assert classification.classify_file(g)["assigned"] == 0


def test_classify_endpoint_and_draft_classification(client, users):
    pid = users["project_id"]
    assert "SATH-KSI" in client.get("/api/classification/systems", headers=users["viewer"]).json()
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE, "v1").json()
    assert v["meta"]["classification"]["classified"] == 0
    r = client.post(f"/api/versions/{v['id']}/classify", json={"system": "SATH-KSI"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["number"] == 2 and v2["meta"]["classification"]["classified"] == 11 and v2["meta"]["classification"]["by_code"]["SATH-KSI:USK.01"] == 3
    assert client.post(f"/api/versions/{v['id']}/classify", json={}, headers=users["engineer"]).status_code == 409  # oxirgi emas
    # qoralama obyekt — GES turidan avtomatik SATH-KSI kodi
    obj = {"kind": "dam", "name": "Yangi to'g'on", "params": {}, "transform": {"x": 100, "y": 0, "z": 0, "rz": 0}, "psets": {"Pset_GES_Dam": {"Turi": "Gravitatsion", "Balandlik_m": 3.0, "Uzunlik_m": 1.0}}, "mesh": {"vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], "faces": [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]]}}
    assert client.post(f"/api/models/{mid}/drafts", json=obj, headers=users["engineer"]).status_code == 201
    r = client.post(f"/api/models/{mid}/drafts/commit", json={"message": "dam"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    vs = client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()
    assert vs[0]["meta"]["classification"]["by_code"].get("SATH-KSI:GTS.01", 0) >= 2


def test_federation_two_models_clash(client, users):
    """Qabul mezoni: ikki modeldagi to'qnashuv aniqlanadi."""
    pid = users["project_id"]
    ma = client.post(f"/api/projects/{pid}/models", json={"name": "Togon"}, headers=users["engineer"]).json()["id"]
    mb = client.post(f"/api/projects/{pid}/models", json={"name": "Zal"}, headers=users["engineer"]).json()["id"]
    va = upload(client, users["engineer"], ma, SAMPLE, "a").json()
    vb = upload(client, users["engineer"], mb, SAMPLE, "b").json()
    # B ni 5 m siljitamiz — A ning devorlari bilan kesishadi; 1000 m siljitsak — to'qnashuv yo'q
    body = {"name": "Stansiya", "members": [{"model_id": ma}, {"model_id": mb, "dx": 5.0}]}
    assert client.post(f"/api/projects/{pid}/federations", json=body, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/federations", json=body, headers=users["engineer"])
    assert r.status_code == 201, r.text
    fed = r.json()
    assert [m["version_id"] for m in fed["members"]] == [va["id"], vb["id"]] and fed["members"][1]["dx"] == 5.0
    rep = client.get(f"/api/federations/{fed['id']}/clashes", headers=users["viewer"]).json()
    assert rep["hard"] > 0 and rep["cross_only"] is True and rep["exact"] is True
    c = rep["clashes"][0]
    assert {c["a"]["model"], c["b"]["model"]} == {"Togon v1", "Zal v1"}
    # ichki juftliklar hisobga olinmagan
    assert all(x["a"]["model"] != x["b"]["model"] for x in rep["clashes"])
    # uzoqqa siljitilsa — yo'q
    body2 = {**body, "members": [{"model_id": ma}, {"model_id": mb, "dx": 1000.0}]}
    r = client.put(f"/api/federations/{fed['id']}", json=body2, headers=users["engineer"])
    assert r.status_code == 200
    rep2 = client.get(f"/api/federations/{fed['id']}/clashes", headers=users["viewer"]).json()
    assert rep2["hard"] == 0 and rep2["possible"] == 0
    # birlashtirilgan IFC: ikki model elementlari, siljitilgan
    r = client.get(f"/api/federations/{fed['id']}/ifc", headers=users["viewer"])
    assert r.status_code == 200 and len(r.content) > 10_000
    assert client.get(f"/api/projects/{pid}/federations", headers=users["viewer"]).json()[0]["name"] == "Stansiya"
    # boshqa loyiha modeli — rad
    p2 = client.post("/api/projects", json={"name": "Begona"}, headers=users["admin"]).json()["id"]
    m2 = client.post(f"/api/projects/{p2}/models", json={"name": "X"}, headers=users["admin"]).json()["id"]
    assert client.post(f"/api/projects/{pid}/federations", json={"name": "F", "members": [{"model_id": m2}]}, headers=users["engineer"]).status_code == 400
    assert client.delete(f"/api/federations/{fed['id']}", headers=users["engineer"]).status_code == 204
