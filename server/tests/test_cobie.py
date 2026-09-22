"""G6: IFC dan aktiv registri (COBie ga o'xshash), CSV zip eksport, Asset sinxronlash, aktiv hujjatlari."""

import csv
import io
import zipfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.pset
from conftest import upload
from ges_server.models import classification, cobie

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"


def _enriched(tmp_path) -> Path:
    """Namuna + ishlab chiqaruvchi/seriya/kafolat/TX davri (Pset_GES_Turbine va standart Pset lar)."""
    f = ifcopenshell.open(str(SAMPLE))
    classification.classify_file(f)
    for i, t in enumerate(f.by_type("IfcFlowMovingDevice")):
        p = next(r.RelatingPropertyDefinition for r in t.IsDefinedBy if r.is_a("IfcRelDefinesByProperties") and r.RelatingPropertyDefinition.Name == "Pset_GES_Turbine")
        ifcopenshell.api.pset.edit_pset(f, pset=p, properties={"Ishlab_chiqaruvchi": "Andritz", "Model": "F-25", "Seriya": f"SN-{i + 1:03d}", "Kafolat_oy": 24, "TX_davri_soat": 8000.0})
    g = f.by_type("IfcElectricGenerator")[0]
    mp = ifcopenshell.api.pset.add_pset(f, product=g, name="Pset_ManufacturerOccurrence")
    ifcopenshell.api.pset.edit_pset(f, pset=mp, properties={"SerialNumber": "GEN-001"})
    out = tmp_path / "rich.ifc"
    f.write(str(out))
    return out


def test_register_and_csv(tmp_path):
    reg = cobie.register_from_path(_enriched(tmp_path))
    assert reg["facility"]["ProjectName"] == "Namuna GES" and len(reg["floors"]) == 2
    turb = [c for c in reg["components"] if c["Kind"] == "turbine"]
    assert len(turb) == 3 and turb[0]["SerialNumber"] == "SN-001" and turb[0]["MaintenanceIntervalHours"] == 8000.0
    assert turb[0]["Category"].startswith("USK.01") and turb[0]["Floor"] == "Turbina qavati"
    t = next(x for x in reg["types"] if x["Name"] == turb[0]["TypeName"])
    assert t["Manufacturer"] == "Andritz" and t["ModelNumber"] == "F-25" and t["WarrantyDurationParts"] == 24
    gen = next(c for c in reg["components"] if c["Kind"] == "generator")
    assert gen["SerialNumber"] == "GEN-001"
    # oddiy devorlar (Pset_GES siz) registrda yo'q, to'g'on (Pset_GES_Dam) bor
    names = {c["Name"] for c in reg["components"]}
    assert "To'g'on" in names and "Zal devori 1" not in names
    z = zipfile.ZipFile(io.BytesIO(cobie.to_csv_zip(reg)))
    assert set(z.namelist()) == {"Facility.csv", "Floor.csv", "Type.csv", "Component.csv", "Attribute.csv"}
    rows = list(csv.DictReader(io.StringIO(z.read("Component.csv").decode("utf-8-sig"))))
    assert len(rows) == reg["counts"]["components"] and rows[0]["ExtIdentifier"]


def test_register_endpoint_sync_assets_and_documents(client, users, tmp_path):
    """Qabul mezoni: IFC dan aktiv registri generatsiya qilinadi va aktivlar bilan bog'lanadi."""
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, _enriched(tmp_path), "v1").json()
    r = client.get(f"/api/versions/{v['id']}/assets/register", headers=users["viewer"])
    assert r.status_code == 200 and r.json()["counts"]["components"] >= 10
    r = client.get(f"/api/versions/{v['id']}/assets/register", params={"format": "csv"}, headers=users["viewer"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/zip")
    # avval qo'lda yaratilgan aktiv (turbina 1 GUID bilan) — sinxronda yangilanadi
    reg = client.get(f"/api/versions/{v['id']}/assets/register", headers=users["viewer"]).json()
    t1 = next(c for c in reg["components"] if c["Name"] == "Turbina 1")
    a = client.post(f"/api/projects/{pid}/assets", json={"name": "Agregat 1", "element_guid": t1["ExtIdentifier"]}, headers=users["engineer"]).json()
    r = client.post(f"/api/projects/{pid}/assets/from-ifc", json={"version_id": v["id"]}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["updated"] == 1 and j["created"] == 6  # 2 turbina + 3 generator + 1 transformator (turbina 1 yangilandi)
    by_guid = {x["element_guid"]: x for x in j["assets"]}
    upd = by_guid[t1["ExtIdentifier"]]
    assert upd["id"] == a["id"] and upd["name"] == "Turbina 1" and upd["maintenance_interval_hours"] == 8000.0
    assert upd["config"]["manufacturer"] == "Andritz" and upd["config"]["serial"] == "SN-001" and upd["config"]["kind"] == "turbine"
    # takror sinxron — yangi yaratilmaydi
    assert client.post(f"/api/projects/{pid}/assets/from-ifc", json={"version_id": v["id"]}, headers=users["engineer"]).json()["created"] == 0
    # hujjatlar: operator yuklaydi, ko'ruvchi o'qiydi, muhandis o'chiradi
    aid = a["id"]
    assert client.post(f"/api/assets/{aid}/documents", files={"file": ("pasport.pdf", io.BytesIO(b"%PDF pasport"), "application/pdf")}, data={"kind": "passport", "title": "Turbina pasporti"}, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/assets/{aid}/documents", files={"file": ("pasport.pdf", io.BytesIO(b"%PDF pasport"), "application/pdf")}, data={"kind": "passport", "title": "Turbina pasporti"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert client.post(f"/api/assets/{aid}/documents", files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")}, data={"kind": "manual"}, headers=users["engineer"]).status_code == 400
    lst = client.get(f"/api/assets/{aid}/documents", headers=users["viewer"]).json()
    assert [x["title"] for x in lst] == ["Turbina pasporti"] and lst[0]["kind"] == "passport"
    r = client.get(f"/api/assets/{aid}/documents/{d['id']}/file", headers=users["viewer"])
    assert r.status_code == 200 and r.content == b"%PDF pasport"
    assert client.delete(f"/api/assets/{aid}/documents/{d['id']}", headers=users["engineer"]).status_code == 204
    assert client.get(f"/api/assets/{aid}/documents", headers=users["viewer"]).json() == []
    # boshqa loyiha versiyasi — rad
    p2 = client.post("/api/projects", json={"name": "Begona"}, headers=users["admin"]).json()["id"]
    assert client.post(f"/api/projects/{p2}/assets/from-ifc", json={"version_id": v["id"]}, headers=users["admin"]).status_code == 400
