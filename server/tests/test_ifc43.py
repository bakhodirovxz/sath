"""G1: IFC4.3 — sxema sozlamadan, GES obyektlari IFC4.3 entitylariga xaritalanadi, IFC4 modellar o'qiladi,
noto'g'ri sinf nomi xato beradi (server va desktop ro'yxati)."""

import sys
from pathlib import Path

import ifcopenshell
import pytest
from conftest import upload
from ges_server.config import get_settings
from ges_server.models import classification, ids_check, ifc_schema

ROOT = Path(__file__).resolve().parents[2]
SAMPLE4 = ROOT / "docs" / "samples" / "namuna_ges_v2.ifc"
SAMPLE43 = ROOT / "docs" / "samples" / "namuna_ges_v2_ifc4x3.ifc"
BOX = {"vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], "faces": [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]]}


def test_schema_mapping_and_class_check():
    assert ifc_schema.normalize("ifc4x3") == "IFC4X3_ADD2" and ifc_schema.normalize("IFC4") == "IFC4"
    with pytest.raises(ValueError):
        ifc_schema.normalize("IFC2X3")
    assert ifc_schema.map_kind("spillway", "IFC4") == ("IfcSlab", None, "SPILLWAY")
    assert ifc_schema.map_kind("spillway", "IFC4X3_ADD2") == ("IfcFacilityPartCommon", "USERDEFINED", "SPILLWAY")
    assert ifc_schema.map_kind("dam", "IFC4X3_ADD2", "Tuproqli")[0] == "IfcEarthworksFill"
    assert ifc_schema.map_kind("dam", "IFC4X3_ADD2", "Gravitatsion")[0] == "IfcWall"
    assert ifc_schema.map_kind("site", "IFC4X3_ADD2") == ("IfcGeographicElement", "TERRAIN", None)
    assert ifc_schema.check_class("ifcpipesegment", "IFC4") == "IfcPipeSegment"
    for bad, sc in [("IfcNoSuch", "IFC4"), ("IfcFacilityPartCommon", "IFC4"), ("IfcProduct", "IFC4X3_ADD2"), ("IfcElement", "IFC4")]:
        with pytest.raises(ValueError):
            ifc_schema.check_class(bad, sc)
    assert ifc_schema.from_freecad_type("Pipe Segment") == "IfcPipeSegment"
    with pytest.raises(ValueError):
        ifc_schema.from_freecad_type("Bunday Yoq")


def test_desktop_class_list_matches_server():
    sys.path.insert(0, str(ROOT / "common"))
    from sath_common import ifc_classes

    assert ifc_classes.IFC4 == ifc_schema.element_classes("IFC4")
    assert ifc_classes.IFC4X3_ADD2 == ifc_schema.element_classes("IFC4X3_ADD2")
    assert ifc_classes.from_freecad_type("Transformer") == "IfcTransformer"
    with pytest.raises(ValueError):
        ifc_classes.from_freecad_type("Nonsense")


def test_ifc43_sample_loads_ids_and_classification(client, users):
    """Qabul mezoni: IFC4.3 model yuklanadi, tur xaritalash testi o'tadi."""
    f = ifcopenshell.open(str(SAMPLE43))
    assert f.schema.startswith("IFC4X3") and ifc_schema.for_file(f) == "IFC4X3_ADD2"
    sp = f.by_type("IfcFacilityPartCommon")[0]
    assert sp.Name == "Suv tashlagich" and sp.PredefinedType == "USERDEFINED" and sp.ObjectType == "SPILLWAY"
    assert f.by_type("IfcPipeSegment")[0].PredefinedType == "RIGIDSEGMENT"
    assert ids_check.validate(SAMPLE43)["status"] == "pass"
    assert classification.kind_of(sp) == "spillway" and classification.classify_file(f)["by_code"]["GTS.02"] == 1
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M43"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE43, "v1").json()
    assert v["meta"]["schema"].startswith("IFC4X3") and v["meta"]["type_counts"]["IfcPipeSegment"] == 2
    from conftest import get_ready

    assert get_ready(client, f"/api/versions/{v['id']}/qto", users["viewer"]).status_code == 200  # OPS-03
    # IFC4 model ham o'qilishda davom etadi
    v4 = upload(client, users["engineer"], mid, SAMPLE4, "v4").json()
    assert v4["meta"]["schema"] == "IFC4"
    sch = client.get("/api/ifc/schemas", headers=users["viewer"]).json()
    assert sch["default"] == "IFC4" and sch["map"]["IFC4X3_ADD2"]["spillway"]["class"] == "IfcFacilityPartCommon"


def test_drafts_in_ifc43_schema_and_invalid_class(client, users, monkeypatch):
    monkeypatch.setattr(get_settings(), "ifc_schema", "IFC4X3_ADD2")
    pid = users["project_id"]
    # loyiha CRS — IfcSite Ref* va IfcMapConversion (IDS SATH-02) qoralamalarda ham yoziladi
    assert client.patch(f"/api/projects/{pid}", json={"epsg_code": 32642, "origin_e": 520101.1, "origin_n": 4572033.07, "origin_h": 450, "crs_rotation_deg": 0}, headers=users["approver"]).status_code == 200
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    objs = [
        {"kind": "spillway", "name": "Suv tashlagich", "params": {}, "transform": {"x": 0, "y": 0, "z": 0, "rz": 0}, "psets": {}, "mesh": BOX},
        {"kind": "dam", "name": "Tuproq to'g'on", "params": {}, "transform": {"x": 10, "y": 0, "z": 0, "rz": 0}, "psets": {"Pset_GES_Dam": {"Turi": "Tuproqli", "Balandlik_m": 20.0, "Uzunlik_m": 100.0}}, "mesh": BOX},
        {"kind": "penstock", "name": "Quvur", "params": {}, "transform": {"x": 20, "y": 0, "z": 0, "rz": 0}, "psets": {"Pset_GES_Penstock": {"Diametr_m": 2.0, "Uzunlik_m": 10.0, "Material": "Po'lat"}}, "mesh": BOX},
    ]
    for o in objs:
        assert client.post(f"/api/models/{mid}/drafts", json=o, headers=users["engineer"]).status_code == 201
    r = client.post(f"/api/models/{mid}/drafts/commit", json={"message": "4.3"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    v = client.get(f"/api/models/{mid}/versions", headers=users["viewer"]).json()[0]
    assert v["meta"]["schema"].startswith("IFC4X3")
    from ges_server.models import storage

    f = ifcopenshell.open(str(storage.resolve(v["file_sha256"])))
    sp = f.by_type("IfcFacilityPartCommon")[0]
    assert sp.ObjectType == "SPILLWAY" and sp.Decomposes and sp.Decomposes[0].RelatingObject.is_a("IfcSite")
    assert sp.Representation is not None
    dam = f.by_type("IfcEarthworksFill")[0]
    assert dam.PredefinedType == "EMBANKMENT" and dam.Name == "Tuproq to'g'on"
    assert f.by_type("IfcPipeSegment")[0].PredefinedType == "RIGIDSEGMENT"
    ids = ids_check.validate(storage.resolve(v["file_sha256"]))
    assert ids["status"] == "pass", [(s["identifier"], [(x["name"], x["reason"]) for q in s["requirements"] for x in q["failed"]]) for s in ids["specifications"] if not s["status"]]
    # noto'g'ri sinf nomi — xato (jimgina proxy emas)
    bad = {"kind": "mesh", "name": "X", "ifc_class": "IfcBunday", "params": {}, "transform": {"x": 0, "y": 0, "z": 0, "rz": 0}, "psets": {}, "mesh": BOX}
    assert client.post(f"/api/models/{mid}/drafts", json=bad, headers=users["engineer"]).status_code == 201
    r = client.post(f"/api/models/{mid}/drafts/commit", json={"message": "bad"}, headers=users["engineer"])
    assert r.status_code == 400 and "sinfi" in r.json()["detail"]
