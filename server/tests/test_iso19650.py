"""G4: ISO 19650 — yaroqlilik/reviziya kodlari holat bilan mos, avtomatik reviziya, konteyner nomlash qoidasi,
EIR/BEP hujjatlari."""

import io
from pathlib import Path

import pytest
from conftest import upload
from ges_server.models import iso19650
from ges_server.orm import VersionState

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def test_codes_and_state_rules():
    iso19650.check_suitability("S0", VersionState.wip)
    iso19650.check_suitability("S3", VersionState.shared)
    iso19650.check_suitability("A2", VersionState.published)
    iso19650.check_suitability("CR", VersionState.published)
    for code, state in [("S0", VersionState.published), ("A1", VersionState.wip), ("S2", VersionState.wip), ("X9", VersionState.wip), ("S9", VersionState.shared)]:
        with pytest.raises(ValueError):
            iso19650.check_suitability(code, state)
    iso19650.check_revision("P01", VersionState.wip)
    iso19650.check_revision("C03", VersionState.published)
    with pytest.raises(ValueError):
        iso19650.check_revision("P01", VersionState.published)
    with pytest.raises(ValueError):
        iso19650.check_revision("C01", VersionState.shared)
    assert iso19650.next_revision(["P01", "P03", None, "C01"], "P") == "P04"
    assert iso19650.next_revision([], "C") == "C01"
    assert iso19650.label("A1").startswith("avtorizatsiya") and iso19650.label(None) == ""


def test_naming_template():
    t = "{project}-{originator}-{volume}-{level}-{type}-{role}-{number}"
    assert iso19650.check_name("CHR-SATH-ZZ-XX-M3-C-0001.ifc", t) is None
    assert "mos emas" in iso19650.check_name("togon_v2.ifc", t)
    assert iso19650.check_name("anything.ifc", "") is None


def test_version_codes_api_rejects_mismatch(client, users):
    """Qabul mezoni: noto'g'ri yaroqlilik kodi bilan holat o'tishi rad etiladi."""
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE, "v1").json()
    assert v["suitability_code"] == "S0" and v["revision_code"] == "P01"
    v2 = upload(client, users["engineer"], mid, SAMPLE, "v2").json()
    assert v2["revision_code"] == "P02"
    # muhandis kod qo'ya olmaydi; tasdiqlovchi — holatga mos bo'lsa
    assert client.patch(f"/api/versions/{v['id']}", json={"suitability_code": "S0"}, headers=users["engineer"]).status_code == 403
    r = client.patch(f"/api/versions/{v['id']}", json={"suitability_code": "A1"}, headers=users["approver"])
    assert r.status_code == 422 and "mos emas" in r.json()["detail"]
    r = client.patch(f"/api/versions/{v['id']}", json={"revision_code": "C01"}, headers=users["approver"])
    assert r.status_code == 422
    r = client.patch(f"/api/versions/{v['id']}", json={"suitability_code": "s0", "revision_code": "p05"}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["suitability_code"] == "S0" and r.json()["revision_code"] == "P05"
    # CR: shared → S3; merge → A1 + C01; keyingi upload P06
    cr = client.post(f"/api/models/{mid}/change-requests", json={"version_id": v2["id"], "title": "T"}, headers=users["engineer"]).json()
    vs = {x["id"]: x for x in client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()}
    assert vs[v2["id"]]["suitability_code"] == "S3" and vs[v2["id"]]["state"] == "shared"
    r = client.patch(f"/api/versions/{v2['id']}", json={"suitability_code": "S4"}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["suitability_label"]
    client.post(f"/api/change-requests/{cr['id']}/reviews", json={"decision": "approve", "comment": ""}, headers=users["approver"])
    r = client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"])
    assert r.status_code == 200
    vs = {x["id"]: x for x in client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()}
    assert vs[v2["id"]]["suitability_code"] == "A1" and vs[v2["id"]]["revision_code"] == "C01"
    v3 = upload(client, users["engineer"], mid, SAMPLE, "v3").json()
    assert v3["revision_code"] == "P06"
    # published holatda S kod rad, B2 qabul
    assert client.patch(f"/api/versions/{v2['id']}", json={"suitability_code": "S1"}, headers=users["approver"]).status_code == 422
    assert client.patch(f"/api/versions/{v2['id']}", json={"suitability_code": "B2"}, headers=users["approver"]).json()["suitability_code"] == "B2"


def test_naming_rule_warns_then_blocks(client, users):
    pid = users["project_id"]
    r = client.patch(f"/api/projects/{pid}", json={"naming_template": "{project}-{originator}-{type}-{number}"}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["naming_template"].startswith("{project}")
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE, "x").json()  # fayl nomi namuna.ifc — mos emas → ogohlantirish
    assert any("Konteyner nomi" in w for w in v["meta"].get("warnings", []))
    client.patch(f"/api/projects/{pid}", json={"naming_required": True}, headers=users["approver"])
    r = upload(client, users["engineer"], mid, SAMPLE, "y")
    assert r.status_code == 422 and "Konteyner nomi" in r.json()["detail"]
    # mos nom bilan — o'tadi
    with open(SAMPLE, "rb") as fh:
        r = client.post(f"/api/models/{mid}/versions", files={"file": ("CHR-SATH-M3-0002.ifc", fh, "application/octet-stream")}, data={"message": "ok"}, headers=users["engineer"])
    assert r.status_code == 201 and not r.json()["meta"].get("warnings")


def test_project_documents(client, users):
    pid = users["project_id"]
    r = client.post(f"/api/projects/{pid}/documents", files={"file": ("EIR.pdf", io.BytesIO(b"%PDF-1.4 eir"), "application/pdf")}, data={"kind": "eir", "title": "Buyurtmachi axborot talablari"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["kind"] == "eir" and d["uploader_username"] == "engineer"
    assert client.post(f"/api/projects/{pid}/documents", files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")}, data={"kind": "bep"}, headers=users["engineer"]).status_code == 400
    assert client.post(f"/api/projects/{pid}/documents", files={"file": ("bep.docx", io.BytesIO(b"x"), "application/octet-stream")}, data={"kind": "nomalum"}, headers=users["engineer"]).status_code == 400
    assert client.post(f"/api/projects/{pid}/documents", files={"file": ("bep.docx", io.BytesIO(b"x"), "application/octet-stream")}, data={"kind": "bep"}, headers=users["viewer"]).status_code == 403
    lst = client.get(f"/api/projects/{pid}/documents", headers=users["viewer"]).json()
    assert [x["title"] for x in lst] == ["Buyurtmachi axborot talablari"]
    r = client.get(f"/api/projects/{pid}/documents/{d['id']}/file", headers=users["viewer"])
    assert r.status_code == 200 and r.content == b"%PDF-1.4 eir"
    assert client.delete(f"/api/projects/{pid}/documents/{d['id']}", headers=users["engineer"]).status_code == 403
    assert client.delete(f"/api/projects/{pid}/documents/{d['id']}", headers=users["approver"]).status_code == 204
    assert client.get(f"/api/projects/{pid}/documents", headers=users["viewer"]).json() == []
