"""G2: IDS validatsiya — namuna o'tadi, majburiy maydonsiz model o'tmaydi, natija versiyada,
loyihada IDS majburiy bo'lsa tasdiqlash/merge bloklanadi."""

import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.pset
import pytest
from conftest import upload
from ges_server.models import ids_check

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def test_ids_file_resolves():
    p = ids_check.ids_path()
    assert p.exists() and p.name == "sath-ges.ids"


def test_sample_passes_ids():
    r = ids_check.validate(SAMPLE)
    assert r["status"] == "pass", [s["name"] for s in r["specifications"] if not s["status"]]
    assert r["total_specifications"] == 7 and r["total_specifications_pass"] == 7
    names = {s["identifier"] for s in r["specifications"]}
    assert {"SATH-01", "SATH-02", "SATH-03", "SATH-10", "SATH-11", "SATH-12", "SATH-13"} <= names


def test_model_without_required_fields_fails(tmp_path):
    """Qabul mezoni: majburiy maydonsiz model IDS tekshiruvidan o'tmaydi — to'g'on balandligi 0, turbina turi
    noto'g'ri, maydon georeferensiyasiz, nomsiz devor."""
    f = ifcopenshell.open(str(SAMPLE))
    site = f.by_type("IfcSite")[0]
    site.RefLatitude = None
    site.RefLongitude = None
    dam = next(w for w in f.by_type("IfcWall") if w.Name == "To'g'on")
    pset = next(r.RelatingPropertyDefinition for r in dam.IsDefinedBy if r.is_a("IfcRelDefinesByProperties") and r.RelatingPropertyDefinition.Name == "Pset_GES_Dam")
    ifcopenshell.api.pset.edit_pset(f, pset=pset, properties={"Balandlik_m": 0.0})
    turb = f.by_type("IfcFlowMovingDevice")[0]
    tp = next(r.RelatingPropertyDefinition for r in turb.IsDefinedBy if r.is_a("IfcRelDefinesByProperties") and r.RelatingPropertyDefinition.Name == "Pset_GES_Turbine")
    ifcopenshell.api.pset.edit_pset(f, pset=tp, properties={"Turi": "Nomalum"})
    f.by_type("IfcWall")[1].Name = None
    bad = tmp_path / "bad.ifc"
    f.write(str(bad))
    r = ids_check.validate(bad)
    assert r["status"] == "fail"
    failed = {s["identifier"]: s for s in r["specifications"] if not s["status"]}
    assert {"SATH-02", "SATH-03", "SATH-10", "SATH-11"} <= set(failed)
    reasons = [x for req in failed["SATH-10"]["requirements"] for x in req["failed"]]
    assert any(x["guid"] == dam.GlobalId for x in reasons)
    assert failed["SATH-03"]["failed"] == 1


def test_missing_ids_file_is_error(tmp_path):
    r = ids_check.validate(SAMPLE, ids_file=tmp_path / "yoq.ids")
    assert r["status"] == "error" and "topilmadi" in r["error"]


def _wait_ids(client, headers, vid, timeout=30):
    for _ in range(int(timeout * 10)):
        r = client.get(f"/api/versions/{vid}/ids", headers=headers)
        if r.status_code == 200:
            return r.json()
        time.sleep(0.1)
    pytest.fail("IDS natijasi kelmadi")


def test_upload_attaches_ids_result_and_run_endpoint(client, users):
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE, "v1").json()
    res = _wait_ids(client, users["viewer"], v["id"])
    assert res["status"] == "pass"
    vs = client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()
    assert vs[0]["ids_status"] == "pass"
    # qayta tekshirish (muhandis+) — natija qaytadi; ko'ruvchi 403
    assert client.post(f"/api/versions/{v['id']}/ids", headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/versions/{v['id']}/ids", headers=users["engineer"])
    assert r.status_code == 200 and r.json()["status"] == "pass"


def test_ids_required_blocks_approval(client, users, tmp_path):
    """Loyihada ids_required: yiqilgan versiya bilan CR tasdiqlanmaydi (409), o'tgan versiya — tasdiqlanadi."""
    pid = users["project_id"]
    r = client.patch(f"/api/projects/{pid}", json={"ids_required": True}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["ids_required"] is True
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    f = ifcopenshell.open(str(SAMPLE))
    f.by_type("IfcSite")[0].RefLatitude = None
    bad = tmp_path / "bad.ifc"
    f.write(str(bad))
    v_bad = upload(client, users["engineer"], mid, bad, "georef yo'q").json()
    cr = client.post(f"/api/models/{mid}/change-requests", json={"version_id": v_bad["id"], "title": "T"}, headers=users["engineer"])
    assert cr.status_code == 201, cr.text
    r = client.post(f"/api/change-requests/{cr.json()['id']}/reviews", json={"decision": "approve", "comment": ""}, headers=users["approver"])
    assert r.status_code == 409 and "IDS" in r.json()["detail"] and "Georeferensiya" in r.json()["detail"]
    # izoh mumkin
    assert client.post(f"/api/change-requests/{cr.json()['id']}/reviews", json={"decision": "comment", "comment": "x"}, headers=users["approver"]).status_code == 201
    # ids_required o'chirilsa — tasdiqlanadi (ogohlantirish rejimi)
    client.patch(f"/api/projects/{pid}", json={"ids_required": False}, headers=users["approver"])
    r = client.post(f"/api/change-requests/{cr.json()['id']}/reviews", json={"decision": "approve", "comment": ""}, headers=users["approver"])
    assert r.status_code == 201
    # yana majburiy: merge ham bloklanadi
    client.patch(f"/api/projects/{pid}", json={"ids_required": True}, headers=users["approver"])
    assert client.post(f"/api/change-requests/{cr.json()['id']}/merge", headers=users["approver"]).status_code == 409
    # o'tgan versiya bilan yangi CR — tasdiq va merge ishlaydi
    v_ok = upload(client, users["engineer"], mid, SAMPLE, "to'liq").json()
    client.post(f"/api/change-requests/{cr.json()['id']}/reject", headers=users["approver"])
    cr2 = client.post(f"/api/models/{mid}/change-requests", json={"version_id": v_ok["id"], "title": "T2"}, headers=users["engineer"]).json()
    assert client.post(f"/api/change-requests/{cr2['id']}/reviews", json={"decision": "approve", "comment": ""}, headers=users["approver"]).status_code == 201
    assert client.post(f"/api/change-requests/{cr2['id']}/merge", headers=users["approver"]).status_code == 200
