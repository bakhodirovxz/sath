"""OPS-04: clash parametrlari — IFC klass whitelist (422), normallashtirilgan xesh kalit, rate limit."""

import pytest
from conftest import upload
from ges_server.config import get_settings
from ges_server.models import geometry


@pytest.fixture
def vid(client, users, ifc_file):
    mid = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "C"}, headers=users["engineer"]).json()["id"]
    return upload(client, users["engineer"], mid, ifc_file).json()["id"]


@pytest.mark.parametrize(
    "q",
    ["types_a=IfcWall/../x", "types_a=IfcWall%2F..%2F..%2Fetc", "types_b=NotIfc", "types_a=IfcNoSuchClass", "types_a=Ifc Wall", "kind=boom"],
)
def test_bad_params_422(client, users, vid, q):
    r = client.get(f"/api/versions/{vid}/clashes?{q}", headers=users["viewer"])
    assert r.status_code == 422, r.text


def test_normalized_key():
    assert geometry.normalize_types("IfcWall, IfcPipeSegment,IfcWall") == ["IfcPipeSegment", "IfcWall"]
    assert geometry.normalize_types("") is None
    k1 = geometry.clash_kind(geometry.normalize_types("IfcWall,IfcSlab"), None)
    assert geometry.normalize_types("IfcWALL") == ["IfcWall"]  # kanonik nom (by_type katta-kichik harfga befarq)
    k2 = geometry.clash_kind(geometry.normalize_types("IfcSlab,IfcWall"), None)
    assert k1 == k2 and k1.startswith("clash-") and "/" not in k1 and len(k1) == len("clash-") + 32
    assert geometry.clash_kind(None, None) == "clash"
    with pytest.raises(ValueError):
        geometry.normalize_types(",".join(["IfcWall"] * 31))


def test_new_computations_rate_limited(client, users, vid, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_derived_per_min", 2)
    calls = []
    monkeypatch.setattr(geometry, "compute_clashes", lambda *a, **k: calls.append(a) or {"clashes": [], "hard": 0})
    types = ["IfcWall", "IfcSlab", "IfcBeam"]
    codes = [client.get(f"/api/versions/{vid}/clashes?types_a={t}", headers=users["viewer"]).status_code for t in types]
    # yangi hisoblar 2 tadan keyin 429 (OPS-03 dan keyin navbatga qo'yish ham shu chegarada)
    assert codes[:2] != [429, 429] and codes[2] == 429
