"""G3: georeferensiya — TM proyeksiya, datum, loyiha CRS lokal↔global, IfcMapConversion yozish/o'qish,
yuklashda ogohlantirish, mavjud modelni georeferensiyalash, DEM ni CRS bo'yicha joylashtirish."""

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
import pytest
from conftest import upload
from ges_server.models import crs, georef

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "namuna_ges_v2.ifc"
# Toshkent (41.2995 N, 69.2401 E) — WGS 84 / UTM 42N
TOSHKENT = (41.2995, 69.2401)


def test_tm_forward_known_values():
    p = crs.from_epsg(32642)
    assert p.lon0_deg == 69 and p.name.endswith("42N")
    # markaziy meridianda: E = 500000; 45° da N = k0 · meridian yoyi(45°) = 0.9996 · 4984944.378 m (WGS84)
    e, n = crs.tm_forward(45.0, 69.0, p)
    assert abs(e - 500000) < 1e-6 and abs(n - 4982950.40) < 0.05
    e, n = crs.tm_forward(0.0, 69.0, p)
    assert abs(e - 500000) < 1e-6 and abs(n) < 1e-6
    # zona chegarasi yaqinida (±3°) ham teskari o'zgartirish mm dan aniq
    for lat, lon in [(41.3, 66.1), (38.0, 71.9), (45.0, 69.5), TOSHKENT]:
        e, n = crs.tm_forward(lat, lon, p)
        la, lo = crs.tm_inverse(e, n, p)
        assert abs(la - lat) < 1e-8 and abs(lo - lon) < 1e-8  # 1e-8° ≈ 1 mm
    # Toshkent: 42-zona, markazdan ~20 km sharqda
    e, n = crs.tm_forward(*TOSHKENT, p)
    assert 519_000 < e < 521_000 and 4_571_000 < n < 4_573_000


def test_utm_zone_and_suggest():
    assert crs.utm_zone(69.24) == 42 and crs.utm_zone(64.5) == 41
    assert crs.suggest_epsg(41.3, 69.2) == 32642 and crs.suggest_epsg(-33.9, 151.2) == 32756
    assert crs.suggest_epsg(41.3, 69.2, "gk") == 28412
    with pytest.raises(ValueError):
        crs.from_epsg(4326)


def test_pulkovo_datum_roundtrip_and_gk():
    la, lo = crs.wgs84_to_datum(*TOSHKENT, "Pulkovo1942")
    assert abs(la - TOSHKENT[0]) < 0.01 and abs(lo - TOSHKENT[1]) < 0.01  # datum farqi ~100 m (~0.001°)
    back = crs.datum_to_wgs84(la, lo, "Pulkovo1942")
    assert abs(back[0] - TOSHKENT[0]) < 1e-7 and abs(back[1] - TOSHKENT[1]) < 1e-7
    g = crs.from_epsg(28412)
    e, n = crs.tm_forward(la, lo, g)
    assert 12_500_000 < e < 12_540_000 and 4_570_000 < n < 4_580_000  # 12-zona: 12 000 000 + 500 000 ± 40 km


def test_project_crs_local_global_known_point():
    """Qabul mezoni: model ichidagi nuqta global koordinatada to'g'ri chiqadi."""
    p = crs.from_epsg(32642)
    e0, n0 = crs.tm_forward(*TOSHKENT, p)
    c = crs.ProjectCRS(32642, e0, n0, 450.0, 0.0)
    assert c.to_global(100, 0, 5) == pytest.approx((e0 + 100, n0, 455.0))
    lat, lon = c.to_latlon(0, 0)
    assert abs(lat - TOSHKENT[0]) < 1e-8 and abs(lon - TOSHKENT[1]) < 1e-8
    x, y = c.from_latlon(*TOSHKENT)
    assert abs(x) < 1e-3 and abs(y) < 1e-3
    # 1000 m shimolga: kenglik ≈ +0.009° (1° ≈ 111.1 km)
    lat2, _ = c.to_latlon(0, 1000)
    assert abs((lat2 - TOSHKENT[0]) * 111_100 - 1000) < 3
    # burilish 90°: lokal +X → global shimol
    r = crs.ProjectCRS(32642, e0, n0, 0.0, 90.0)
    assert r.to_global(100, 0) == pytest.approx((e0, n0 + 100, 0.0), abs=1e-6)
    lx, ly, _ = r.to_local(e0, n0 + 100)
    assert (lx, ly) == pytest.approx((100, 0), abs=1e-6)


def test_ifc_georef_write_read(tmp_path):
    f = ifcopenshell.open(str(SAMPLE))
    assert georef.read(f) == {"site_lat": 41.62, "site_lon": 69.98}  # namunada faqat IfcSite Ref*
    c = crs.ProjectCRS(32642, 520101.1, 4572033.07, 450.0, 30.0)
    info = georef.apply(f, c)
    assert info["epsg"] == 32642 and info["rotation_deg"] == pytest.approx(30.0) and info["supported"] is True
    assert abs(info["site_lat"] - TOSHKENT[0]) < 1e-4 and abs(info["site_lon"] - TOSHKENT[1]) < 1e-4
    out = tmp_path / "g.ifc"
    f.write(str(out))
    g = ifcopenshell.open(str(out))
    mc = g.by_type("IfcMapConversion")[0]
    assert mc.TargetCRS.Name == "EPSG:32642" and mc.Eastings == pytest.approx(520101.1)
    assert georef.read(g)["origin_n"] == pytest.approx(4572033.07)
    # ikkinchi apply — yangilaydi, ikkinchi IfcMapConversion yaratmaydi
    georef.apply(g, crs.ProjectCRS(32641, 1.0, 2.0))
    assert len(g.by_type("IfcMapConversion")) == 1 and georef.read(g)["epsg"] == 32641


def test_project_crs_api_and_upload_warning_and_georeference(client, users):
    pid = users["project_id"]
    assert client.get(f"/api/projects/{pid}/crs/convert", params={"x": 0, "y": 0}, headers=users["viewer"]).status_code == 409
    sug = client.get(f"/api/projects/{pid}/crs/suggest", params={"lat": TOSHKENT[0], "lon": TOSHKENT[1]}, headers=users["viewer"]).json()
    assert sug["epsg"] == 32642 and 519_000 < sug["origin_e"] < 521_000
    r = client.patch(f"/api/projects/{pid}", json={"epsg_code": 4326}, headers=users["approver"])
    assert r.status_code == 400
    r = client.patch(f"/api/projects/{pid}", json={"epsg_code": sug["epsg"], "origin_e": sug["origin_e"], "origin_n": sug["origin_n"], "origin_h": 450, "crs_rotation_deg": 0}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["crs"]["epsg"] == 32642
    conv = client.get(f"/api/projects/{pid}/crs/convert", params={"x": 100, "y": 0, "z": 5}, headers=users["viewer"]).json()
    assert conv["global"]["e"] == pytest.approx(sug["origin_e"] + 100, abs=0.01) and conv["global"]["h"] == 455
    assert abs(conv["latlon"]["lat"] - TOSHKENT[0]) < 1e-4
    conv2 = client.get(f"/api/projects/{pid}/crs/convert", params={"lat": TOSHKENT[0], "lon": TOSHKENT[1]}, headers=users["viewer"]).json()
    assert abs(conv2["local"]["x"]) < 0.01 and abs(conv2["local"]["y"]) < 0.01
    # yuklash: georeferensiyasiz fayl → ogohlantirish meta da
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, SAMPLE, "v1").json()
    assert any("Georeferensiya" in w for w in v["meta"].get("warnings", []))
    assert v["meta"]["georef"] == {"site_lat": 41.62, "site_lon": 69.98}
    # mavjud modelga qo'shish → yangi versiya IfcMapConversion bilan
    r = client.post(f"/api/models/{mid}/georeference", json={}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["number"] == 2 and v2["meta"]["georef"]["epsg"] == 32642 and not v2["meta"].get("warnings")
    assert abs(v2["meta"]["georef"]["site_lat"] - TOSHKENT[0]) < 1e-4
    # CRS o'chirish
    r = client.patch(f"/api/projects/{pid}", json={"epsg_code": 0}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["crs"] is None


def test_dem_placed_by_project_crs(client, users, monkeypatch):
    from ges_server.models import dem

    monkeypatch.setattr(dem, "_tile", lambda z, x, y: np.full((256, 256), 800.0))
    pid = users["project_id"]
    p = crs.from_epsg(32642)
    e0, n0 = crs.tm_forward(*TOSHKENT, p)
    client.patch(f"/api/projects/{pid}", json={"epsg_code": 32642, "origin_e": e0, "origin_n": n0, "origin_h": 400, "crs_rotation_deg": 0}, headers=users["approver"])
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    # markaz — origin dan ~1 km shimolda (kenglik +0.009°)
    r = client.post(f"/api/models/{mid}/versions/import-dem", json={"lat": TOSHKENT[0] + 0.009, "lon": TOSHKENT[1], "width_m": 500, "height_m": 500, "zoom": 12, "nx": 10}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    lc = r.json()["dem"]["local_center"]
    assert abs(lc[0]) < 5 and abs(lc[1] - 1000) < 5  # lokal y ≈ +1000 m
    f = ifcopenshell.open(str(__import__("ges_server.models.storage", fromlist=["resolve"]).resolve(r.json()["file_sha256"])))
    assert f.by_type("IfcMapConversion") and f.by_type("IfcMapConversion")[0].TargetCRS.Name == "EPSG:32642"
    terr = next(e for e in f.by_type("IfcGeographicElement"))
    scale = ifcopenshell.util.unit.calculate_unit_scale(f)  # loyiha birligi (mm) → m
    z = ifcopenshell.util.placement.get_local_placement(terr.ObjectPlacement)[2, 3] * scale
    assert abs(z - (800 - 400)) < 1  # global 800 m → lokal 400 m (origin_h)
