"""H1: KKS/RDS-PP grammatikasi, aktiv ierarxiyasi (parent, taksonomiya), daraxt + agregatsiya, sensor KKS,
CSV import."""

import io

import pytest
from ges_server.monitoring import kks


def test_kks_grammar_and_levels():
    p = kks.parse("1mka10 ah001 ma01")
    assert p["normalized"] == "1MKA10 AH001 MA01" and p["level"] == "component" and p["system_name"] == "Generator"
    assert kks.parse("MKA10")["level"] == "system" and kks.parse("1MAA10 AH001")["level"] == "equipment"
    assert kks.parent_code("1MKA10 AH001 MA01") == "1MKA10 AH001" and kks.parent_code("1MKA10 AH001") == "1MKA10" and kks.parent_code("MKA10") is None
    r = kks.parse("=G001 MKA10.AH001 -AP001")
    assert r["scheme"] == "RDS-PP" and r["normalized"] == "=MKA10 AH001"
    for bad in ["1MKA1", "MKA10 AH01", "ABCD10", "=X", "MKA10AH001MA1"]:
        with pytest.raises(ValueError):
            kks.parse(bad)
    assert kks.validate("  ") is None and kks.validate("mka10") == "MKA10"
    assert kks.level_for("1MKA10 AH001", None) == "equipment" and kks.level_for(None, "plant") == "plant"
    with pytest.raises(ValueError):
        kks.level_for(None, "bunday")


def test_asset_hierarchy_api_and_tree(client, users):
    """Qabul mezoni: ierarxiya bo'yicha aktiv daraxti ko'rinadi; noto'g'ri KKS kodi rad etiladi."""
    pid = users["project_id"]
    h = users["engineer"]
    r = client.post(f"/api/projects/{pid}/assets", json={"name": "Generator tizimi", "kks_code": "1MKA10", "taxonomy_level": "system"}, headers=h)
    assert r.status_code == 201, r.text
    sys_a = r.json()
    assert sys_a["kks_code"] == "1MKA10" and sys_a["taxonomy_level"] == "system"
    r = client.post(f"/api/projects/{pid}/assets", json={"name": "Agregat 1", "kks_code": "1mka10 ah001", "parent_id": sys_a["id"]}, headers=h)
    assert r.status_code == 201
    eq = r.json()
    assert eq["kks_code"] == "1MKA10 AH001" and eq["taxonomy_level"] == "equipment" and eq["parent_id"] == sys_a["id"]
    r = client.post(f"/api/projects/{pid}/assets", json={"name": "Podshipnik", "kks_code": "1MKA10 AH001 MA01", "parent_id": eq["id"], "maintenance_interval_hours": 10}, headers=h)
    comp = r.json()
    assert comp["taxonomy_level"] == "component"
    # noto'g'ri kod, band kod, halqa, boshqa loyiha otasi
    assert client.post(f"/api/projects/{pid}/assets", json={"name": "X", "kks_code": "1MKA1"}, headers=h).status_code == 422
    assert client.post(f"/api/projects/{pid}/assets", json={"name": "X", "kks_code": "1MKA10"}, headers=h).status_code == 409
    assert client.patch(f"/api/assets/{sys_a['id']}", json={"parent_id": comp["id"]}, headers=h).status_code == 400
    assert client.post(f"/api/projects/{pid}/assets", json={"name": "X", "taxonomy_level": "nomalum"}, headers=h).status_code == 422
    p2 = client.post("/api/projects", json={"name": "Begona"}, headers=users["admin"]).json()["id"]
    other = client.post(f"/api/projects/{p2}/assets", json={"name": "Y"}, headers=users["admin"]).json()
    assert client.patch(f"/api/assets/{eq['id']}", json={"parent_id": other["id"]}, headers=h).status_code == 400
    # daraxt: ildiz → uskuna → komponent; komponent texnik xizmati kechikkan bo'lsa agregatsiya yuqoriga chiqadi
    client.post(f"/api/assets/{comp['id']}/maintenance?note=x", headers=h)
    tree = client.get(f"/api/projects/{pid}/assets/tree", headers=users["viewer"]).json()
    assert tree["count"] == 3 and len(tree["roots"]) == 1
    root = tree["roots"][0]
    assert root["kks_code"] == "1MKA10" and root["children"][0]["kks_code"] == "1MKA10 AH001" and root["children"][0]["children"][0]["name"] == "Podshipnik"
    assert root["kks"]["system_name"] == "Generator" and root["agg_status"] in ("ok", "due", "overdue")
    # ota o'chirilsa (0) — ildizga
    assert client.patch(f"/api/assets/{eq['id']}", json={"parent_id": 0}, headers=h).json()["parent_id"] is None
    assert len(client.get(f"/api/projects/{pid}/assets/tree", headers=users["viewer"]).json()["roots"]) == 2
    assert "MKA" in client.get("/api/kks/systems", headers=users["viewer"]).json()["systems"]


def test_sensor_kks_and_csv_import(client, users):
    pid = users["project_id"]
    h = users["engineer"]
    assert client.post(f"/api/projects/{pid}/sensors", json={"key": "AGG1.P", "name": "P", "kind": "power", "kks_code": "1MKA1"}, headers=h).status_code == 422
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "AGG1.P", "name": "P", "kind": "power", "kks_code": "1mka10 ce001"}, headers=h)
    assert r.status_code == 201 and r.json()["kks_code"] == "1MKA10 CE001"
    sid = r.json()["id"]
    assert client.patch(f"/api/sensors/{sid}", json={"kks_code": ""}, headers=h).json()["kks_code"] is None
    csv = "kks_code,name,parent_kks,taxonomy_level,sensor_key\n1MKA10,Generator tizimi,,system,\n1MKA10 AH001,Agregat 1,,,AGG1.P\n1MKA10 AH001 MA01,Podshipnik,1MKA10 AH001,,\nXXX,Yaroqsiz,,,\n"
    r = client.post(f"/api/projects/{pid}/assets/import-kks", files={"file": ("kks.csv", io.BytesIO(csv.encode()), "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["created"] == 3 and j["updated"] == 0 and len(j["errors"]) == 1 and "5-qator" in j["errors"][0]
    tree = client.get(f"/api/projects/{pid}/assets/tree", headers=users["viewer"]).json()
    root = tree["roots"][0]
    assert root["kks_code"] == "1MKA10" and root["children"][0]["kks_code"] == "1MKA10 AH001" and root["children"][0]["children"][0]["kks_code"] == "1MKA10 AH001 MA01"
    assert root["children"][0]["taxonomy_level"] == "equipment"
    # sensor KKS kodi CSV dan
    s = next(x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json() if x["key"] == "AGG1.P")
    assert s["kks_code"] == "1MKA10 AH001"
    # takror import — yangilanadi, yaratilmaydi
    r = client.post(f"/api/projects/{pid}/assets/import-kks", files={"file": ("kks.csv", io.BytesIO(csv.encode()), "text/csv")}, headers=h).json()
    assert r["created"] == 0 and r["updated"] == 3
    assert client.post(f"/api/projects/{pid}/assets/import-kks", files={"file": ("k.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}, headers=h).status_code == 400
