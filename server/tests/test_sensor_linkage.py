"""SCADA-13: sensor ↔ IFC element bog'lanishi — GUID tekshiruvi, bog'lanmagan sensorlar, nashr hook."""

import ifcopenshell
import pytest
from conftest import make_ifc, upload


@pytest.fixture
def setup(client, users, tmp_path):
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "Zal"}, headers=users["engineer"]).json()["id"]
    p1 = make_ifc(tmp_path / "v1.ifc", wall_names=("Wall 1", "Wall 2"))
    f = ifcopenshell.open(str(p1))
    guids = {w.Name: w.GlobalId for w in f.by_type("IfcWall")}
    v1 = upload(client, users["engineer"], mid, p1, "v1").json()
    # v2: Wall 2 o'chirilgan (qolgan GUID lar o'zgarmaydi)
    f.remove(f.by_guid(guids["Wall 2"]))
    p2 = tmp_path / "v2.ifc"
    f.write(str(p2))
    return {"pid": pid, "mid": mid, "guids": guids, "v1": v1, "p2": p2}


def _sensor(client, users, pid, key, guid, mid=None, force=None):
    url = f"/api/projects/{pid}/sensors" + ("?force=true" if force else "")
    return client.post(
        url, json={"key": key, "name": key, "element_guid": guid, "model_id": mid}, headers=users["engineer"]
    )


def test_guid_validated_on_create_and_update(client, users, setup):
    pid, g = setup["pid"], setup["guids"]
    assert _sensor(client, users, pid, "W1.T", g["Wall 1"], setup["mid"]).status_code == 201
    r = _sensor(client, users, pid, "BAD.T", "0000000000000000000000")
    assert r.status_code == 422 and "force=true" in r.json()["detail"]
    r = _sensor(client, users, pid, "FUT.T", "0000000000000000000000", force=True)  # qurilishdan oldin
    assert r.status_code == 201
    sid = r.json()["id"]
    r = client.patch(f"/api/sensors/{sid}", json={"element_guid": "1111111111111111111111"}, headers=users["engineer"])
    assert r.status_code == 422
    r = client.patch(f"/api/sensors/{sid}", json={"element_guid": g["Wall 2"]}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["element_guid"] == g["Wall 2"]
    r = client.patch(
        f"/api/sensors/{sid}?force=true", json={"element_guid": "1111111111111111111111"}, headers=users["engineer"]
    )
    assert r.status_code == 200
    # GUID ga tegmaydigan tahrir tekshirilmaydi
    assert client.patch(f"/api/sensors/{sid}", json={"name": "yangi"}, headers=users["engineer"]).status_code == 200


def test_unlinked_report_and_publish_notification(client, users, setup):
    pid, mid, g = setup["pid"], setup["mid"], setup["guids"]
    _sensor(client, users, pid, "W1.T", g["Wall 1"], mid)
    _sensor(client, users, pid, "W2.T", g["Wall 2"], mid)
    r = client.get(f"/api/projects/{pid}/sensors/unlinked", headers=users["viewer"])
    assert r.status_code == 200 and r.json()["count"] == 0 and r.json()["checked"] == 2
    v2 = upload(client, users["engineer"], mid, setup["p2"], "v2", parent_id=setup["v1"]["id"]).json()
    r = client.get(f"/api/projects/{pid}/sensors/unlinked?version_id={v2['id']}", headers=users["viewer"]).json()
    assert r["count"] == 1 and r["sensors"][0]["key"] == "W2.T"
    # joriy (head) versiya bo'yicha ham
    assert client.get(f"/api/projects/{pid}/sensors/unlinked", headers=users["viewer"]).json()["count"] == 1
    assert client.get(f"/api/projects/{pid}/sensors/unlinked", headers=users["outsider"]).status_code == 403
    # nashr (CR merge) → muhandislarga bildirishnoma
    cr = client.post(
        f"/api/models/{mid}/change-requests", json={"version_id": v2["id"], "title": "v2"}, headers=users["engineer"]
    ).json()
    client.post(f"/api/change-requests/{cr['id']}/reviews", json={"decision": "approve"}, headers=users["approver"])
    assert client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"]).status_code == 200
    notes = client.get("/api/notifications", headers=users["engineer"]).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    hit = [n for n in items if n["title"].startswith("Bog'lanmagan sensorlar: 1")]
    assert hit and "W2.T" in hit[0]["body"]
    viewer_notes = client.get("/api/notifications", headers=users["viewer"]).json()
    viewer_items = viewer_notes["items"] if isinstance(viewer_notes, dict) else viewer_notes
    assert not any(n["title"].startswith("Bog'lanmagan") for n in viewer_items)


def test_no_versions_skips_validation(client, users):
    r = _sensor(client, users, users["project_id"], "ANY.T", "whatever")
    assert r.status_code == 201
