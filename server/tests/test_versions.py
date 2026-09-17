import pytest
from conftest import make_ifc, upload


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "To'g'on"},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_viewer_cannot_create_model(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "X"},
        headers=users["viewer"],
    )
    assert r.status_code == 403


def test_duplicate_model_name(client, users, model_id):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "To'g'on"},
        headers=users["engineer"],
    )
    assert r.status_code == 409


def test_upload_and_download(client, users, model_id, ifc_file):
    r = upload(client, users["engineer"], model_id, ifc_file, message="Birinchi versiya")
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["number"] == 1
    assert v["parent_id"] is None
    assert v["state"] == "wip"
    assert v["author_username"] == "engineer"
    assert v["meta"]["schema"] == "IFC4"
    assert v["meta"]["element_count"] == 3  # site, storey, wall
    assert v["meta"]["type_counts"]["IfcWall"] == 1
    assert v["meta"]["storeys"][0]["name"] == "L0"

    r = client.get(f"/api/versions/{v['id']}/file", headers=users["viewer"])
    assert r.status_code == 200
    assert r.content == ifc_file.read_bytes()
    assert "attachment" in r.headers["content-disposition"]

    r = client.get(f"/api/models/{model_id}", headers=users["viewer"])
    assert r.json()["version_count"] == 1
    assert r.json()["latest_version_id"] == v["id"]
    assert r.json()["published_version_id"] is None


def test_version_chain_and_dedup(client, users, model_id, ifc_file, tmp_path):
    v1 = upload(client, users["engineer"], model_id, ifc_file, "v1").json()
    other = make_ifc(tmp_path / "other.ifc", wall_names=("A", "B"))
    v2 = upload(client, users["engineer"], model_id, other, "v2").json()
    assert v2["number"] == 2 and v2["parent_id"] == v1["id"]
    # aniq parent ko'rsatish (v1 dan tarmoq)
    v3 = upload(client, users["engineer"], model_id, ifc_file, "v3", parent_id=v1["id"]).json()
    assert v3["number"] == 3 and v3["parent_id"] == v1["id"]
    # bir xil fayl — bir xil sha, dedup
    assert v3["file_sha256"] == v1["file_sha256"]
    assert v3["file_sha256"] != v2["file_sha256"]

    r = client.get(f"/api/models/{model_id}/versions", headers=users["viewer"])
    assert [v["number"] for v in r.json()] == [3, 2, 1]


def test_bad_parent(client, users, model_id, ifc_file):
    r = upload(client, users["engineer"], model_id, ifc_file, parent_id=9999)
    assert r.status_code == 400


def test_viewer_cannot_upload(client, users, model_id, ifc_file):
    assert upload(client, users["viewer"], model_id, ifc_file).status_code == 403
    assert upload(client, users["outsider"], model_id, ifc_file).status_code == 403


def test_rejects_non_ifc(client, users, model_id, tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("hello")
    assert upload(client, users["engineer"], model_id, bad).status_code == 400
    bad_ifc = tmp_path / "x.ifc"
    bad_ifc.write_text("this is not ifc")
    assert upload(client, users["engineer"], model_id, bad_ifc).status_code == 400


def test_delete_model_requires_approver(client, users, model_id, ifc_file):
    upload(client, users["engineer"], model_id, ifc_file)
    assert client.delete(f"/api/models/{model_id}", headers=users["engineer"]).status_code == 403
    assert client.delete(f"/api/models/{model_id}", headers=users["approver"]).status_code == 204
    assert client.get(f"/api/models/{model_id}", headers=users["approver"]).status_code == 404


def test_qto_and_clashes(client, users):
    """BIM tekshiruvlar: namuna GES modeli (docs/samples) — hajmlar, turlar, to'qnashuvlar."""
    from pathlib import Path

    from conftest import upload

    sample = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"
    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "GES"}, headers=users["engineer"]
    ).json()["id"]
    v = upload(client, users["engineer"], mid, sample, "namuna").json()
    q = client.get(f"/api/versions/{v['id']}/qto", headers=users["viewer"]).json()
    assert q["element_count"] >= 10 and q["total_volume_m3"] > 1000
    dam = next(e for e in q["elements"] if e["name"] == "To'g'on")
    assert dam["type"] == "IfcWall" and abs(dam["volume_m3"] - 10560) < 1 and dam["height_m"] == 22
    assert "IfcWall" in q["by_type"] and q["by_type"]["IfcWall"]["count"] == 5
    csv = client.get(f"/api/versions/{v['id']}/qto?format=csv", headers=users["viewer"])
    assert csv.status_code == 200 and "To'g'on" in csv.text
    c = client.get(f"/api/versions/{v['id']}/clashes", headers=users["viewer"]).json()
    assert c["exact"] and c["hard"] >= 2 and c["touch"] >= 5
    hard = [x for x in c["clashes"] if x["kind"] == "hard"]
    # quvur devorni teshib o'tadi — haqiqiy to'qnashuv; pol devorga tegib turadi — touch
    assert any({x["a"]["type"], x["b"]["type"]} == {"IfcWall", "IfcPipeSegment"} for x in hard)
    assert all(len(x["point"]) == 3 and x["triangle_hits"] > 0 for x in hard)
    only = client.get(f"/api/versions/{v['id']}/clashes?kind=hard", headers=users["viewer"]).json()
    assert all(x["kind"] == "hard" for x in only["clashes"]) and len(only["clashes"]) == c["hard"]
    f = client.get(
        f"/api/versions/{v['id']}/clashes?types_a=IfcWall&types_b=IfcPipeSegment",
        headers=users["viewer"],
    ).json()
    assert f["clashes"] and all(
        {x["a"]["type"], x["b"]["type"]} == {"IfcWall", "IfcPipeSegment"} for x in f["clashes"]
    )
    assert client.get(f"/api/versions/{v['id']}/qto", headers=users["outsider"]).status_code == 403


def test_fragments_endpoint(client, users, ifc_file, monkeypatch):
    """Server tomonida .frag konvertatsiya (Node bo'lsa) — kesh; Node yo'q bo'lsa 404."""
    from conftest import upload
    from ges_server.models import fragments

    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]
    ).json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file, "v1").json()
    r = client.get(f"/api/versions/{v['id']}/fragments", headers=users["viewer"])
    if fragments.available():
        assert r.status_code == 200 and len(r.content) > 100
        assert fragments.frag_path(v["file_sha256"]).exists()
        # ikkinchi so'rov keshdan
        assert (
            client.get(f"/api/versions/{v['id']}/fragments", headers=users["viewer"]).content
            == r.content
        )
    else:
        assert r.status_code == 404
    monkeypatch.setattr(fragments, "tool_path", lambda: None)
    fragments.frag_path(v["file_sha256"]).unlink(missing_ok=True)
    assert (
        client.get(f"/api/versions/{v['id']}/fragments", headers=users["viewer"]).status_code == 404
    )
    assert (
        client.get(f"/api/versions/{v['id']}/fragments", headers=users["outsider"]).status_code
        == 403
    )


def test_version_tag_message_and_restore(client, users, ifc_file):
    """Yorliq (tasdiqlovchi), izoh (muallif/tasdiqlovchi), qayta tiklash (git revert kabi)."""
    from conftest import upload

    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]
    ).json()["id"]
    v1 = upload(client, users["engineer"], mid, ifc_file, "birinchi").json()
    v2 = upload(client, users["engineer"], mid, ifc_file, "ikkinchi").json()
    # izoh: muallif; yorliq: faqat tasdiqlovchi
    r = client.patch(
        f"/api/versions/{v1['id']}", json={"message": "yangilangan izoh"}, headers=users["engineer"]
    )
    assert r.status_code == 200 and r.json()["message"] == "yangilangan izoh"
    assert (
        client.patch(
            f"/api/versions/{v1['id']}", json={"tag": "X"}, headers=users["engineer"]
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/versions/{v1['id']}", json={"message": "x"}, headers=users["viewer"]
        ).status_code
        == 403
    )
    r = client.patch(
        f"/api/versions/{v1['id']}", json={"tag": "EKSPERTIZA-1"}, headers=users["approver"]
    )
    assert r.status_code == 200 and r.json()["tag"] == "EKSPERTIZA-1"
    # qayta tiklash: oxirgisini tiklab bo'lmaydi; v1 → v3 (fayl v1 niki, ota v2)
    assert (
        client.post(f"/api/versions/{v2['id']}/restore", headers=users["engineer"]).status_code
        == 409
    )
    assert (
        client.post(f"/api/versions/{v1['id']}/restore", headers=users["viewer"]).status_code == 403
    )
    r = client.post(f"/api/versions/{v1['id']}/restore", headers=users["engineer"])
    assert r.status_code == 201, r.text
    v3 = r.json()
    assert (
        v3["number"] == 3 and v3["parent_id"] == v2["id"] and v3["file_sha256"] == v1["file_sha256"]
    )
    assert v3["message"].startswith("v1 dan qayta tiklandi") and v3["state"] == "wip"
    assert len(client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()) == 3
