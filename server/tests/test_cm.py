"""H3: ISO 13374 holat monitoringi arxitekturasi — DA/DM/SD/HA/PA/AG bloklari, spektr saqlash va
podshipnik nuqson chastotalari, tashqi tizim natijasi sog'liq indeksiga qo'shiladi, mashina guruhi
H1 ierarxiyasidan olinadi."""

import math
from datetime import datetime, timedelta, timezone

from ges_server.db import SessionLocal
from ges_server.monitoring import cm
from ges_server.monitoring.cm import da, dm, sd
from ges_server.orm import Asset, Project, Spectrum


def _asset(client, users, **kw):
    return client.post(
        f"/api/projects/{users['project_id']}/assets", json=kw, headers=users["engineer"]
    ).json()


def test_bearing_frequencies_and_spectrum_features():
    """Podshipnik nuqson chastotalari (Harris / ISO 13373-3) va spektr xususiyatlari."""
    bearing = {"n": 8, "d_mm": 20.0, "D_mm": 100.0, "alpha_deg": 0}
    f = dm.bearing_frequencies(bearing, 600)  # fr = 10 Gs, d/D = 0.2
    assert f["fr"] == 10.0
    assert abs(f["BPFO"] - 8 / 2 * 10 * (1 - 0.2)) < 1e-6  # 32 Gs
    assert abs(f["BPFI"] - 8 / 2 * 10 * (1 + 0.2)) < 1e-6  # 48 Gs
    assert abs(f["FTF"] - 10 / 2 * (1 - 0.2)) < 1e-6  # 4 Gs
    assert abs(f["BSF"] - 100 / (2 * 20) * 10 * (1 - 0.04)) < 1e-6  # 24 Gs
    assert dm.bearing_frequencies(None, 600) is None and dm.bearing_frequencies(bearing, 0) is None

    # 100 chiziqli spektr 0–100 Gs: 32 Gs da katta cho'qqi (BPFO)
    vals = [0.01] * 101
    vals[32] = 1.0
    sp = Spectrum(id=1, kind="envelope", unit="g", rpm=600, f_min=0, f_max=100, n_lines=101, values=vals)
    feats = dm.spectrum_features(sp, bearing, 600)
    assert feats["peaks"][0]["f"] == 32.0
    assert feats["bearing_matches"][0]["name"] == "BPFO" and feats["bearing_matches"][0]["share"] > 0.9
    assert abs(feats["overall"] - math.sqrt(1.0 + 100 * 0.0001)) < 1e-3


def test_machine_group_from_hierarchy(client, users):
    """Mashina guruhi: aktiv konfiguratsiyasi → ota aktiv (H1) → KKS tizimi → 4."""
    parent = _asset(client, users, name="Turbina tizimi", kks_code="1MAA10", taxonomy_level="system", config={"machine_group": 2})
    child = _asset(client, users, name="Turbina 1", kks_code="1MAA10 AH001", parent_id=parent["id"])
    gen = _asset(client, users, name="Generator", kks_code="1MKA10", taxonomy_level="system")
    plain = _asset(client, users, name="Nomsiz")
    with SessionLocal() as db:
        assert da.machine_group(db, db.get(Asset, child["id"])) == 2  # otadan meros
        assert da.machine_group(db, db.get(Asset, gen["id"])) == 4  # KKS: generator — vertikal
        assert da.machine_group(db, db.get(Asset, plain["id"])) == 4  # standart


def test_spectrum_api_and_features(client, users):
    pid = users["project_id"]
    h = users["engineer"]
    a = _asset(client, users, name="Agregat 1", config={"bearing": {"n": 8, "d_mm": 20, "D_mm": 100}, "rated_speed_rpm": 600})
    vals = [0.02] * 101
    vals[32] = 0.9
    body = {"asset_id": a["id"], "kind": "envelope", "unit": "g", "rpm": 600, "f_min": 0, "f_max": 100, "values": vals, "source": "CM gateway"}
    # ko'ruvchi yoza olmaydi
    assert client.post(f"/api/projects/{pid}/cm/spectra", json=body, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/cm/spectra", json=body, headers=h)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["n_lines"] == 101 and r.json()["values"] is None  # ro'yxatda massiv yuborilmaydi
    # noto'g'ri chastota o'qi
    assert client.post(f"/api/projects/{pid}/cm/spectra", json={**body, "f_max": 0}, headers=h).status_code == 400
    assert client.post(f"/api/projects/{pid}/cm/spectra", json={**body, "freqs": [1, 2]}, headers=h).status_code == 400
    one = client.get(f"/api/cm/spectra/{sid}", headers=users["viewer"]).json()
    assert len(one["values"]) == 101
    assert one["features"]["bearing_matches"][0]["name"] == "BPFO"
    assert one["features"]["bearing_frequencies"]["BPFO"] == 32.0
    lst = client.get(f"/api/projects/{pid}/cm/spectra?asset_id={a['id']}", headers=users["viewer"]).json()
    assert len(lst) == 1
    # podshipnik nuqsoni SD blokida holat beradi va sog'liqqa ta'sir qiladi
    blocks = client.get(f"/api/assets/{a['id']}/cm", headers=users["viewer"]).json()
    assert blocks["states"]["bearing_defect"]["state"] == "alarm"
    assert "BPFO" in blocks["states"]["bearing_defect"]["reason"]
    assert blocks["score"] <= 65 and blocks["blocks"]["SD"]["state"] == "alarm"
    assert blocks["blocks"]["DA"]["spectra"] == 1 and blocks["blocks"]["AG"]["problems"] >= 1
    assert client.delete(f"/api/cm/spectra/{sid}", headers=users["viewer"]).status_code == 403
    assert client.delete(f"/api/cm/spectra/{sid}", headers=h).status_code == 204


def test_external_cm_result_affects_health(client, users):
    """Qabul mezoni: tashqi tizim natijasi qabul qilinadi va sog'liq indeksiga qo'shiladi."""
    pid = users["project_id"]
    h = users["engineer"]
    a = _asset(client, users, name="Agregat 2")
    before = client.get(f"/api/assets/{a['id']}/cm", headers=users["viewer"]).json()
    assert before["score"] == 100 and before["external"] == [] and before["external_score"] is None
    body = {
        "asset_id": a["id"],
        "source": "Bently Nevada 3500",
        "block": "HA",
        "state": "alert",
        "health_score": 55,
        "rul_days": 120,
        "diagnosis": "Rotor nomutanosibligi (1× ustun)",
        "confidence": 0.8,
    }
    assert client.post(f"/api/projects/{pid}/cm/results", json=body, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/cm/results", json=body, headers=h)
    assert r.status_code == 201, r.text
    after = client.get(f"/api/assets/{a['id']}/cm", headers=users["viewer"]).json()
    assert after["external_score"] == 55 and after["score"] == 55 and after["level"] == "yomon"
    assert after["internal_score"] == 85  # tashqi «alert» ichki ballni ham 15 ga kamaytiradi
    assert after["state"] == "alert"
    assert any("Bently Nevada" in p for p in after["problems"])
    assert after["prognosis"]["rul_days"] == 120 and after["prognosis"]["rul_basis"] == "external"
    assert any("qolgan resurs" in p for p in after["problems"])
    # loyiha hisobotida ham ko'rinadi
    rep = client.get(f"/api/projects/{pid}/health", headers=users["viewer"]).json()
    item = next(x for x in rep["assets"] if x["asset_id"] == a["id"])
    assert item["score"] == 55
    lst = client.get(f"/api/projects/{pid}/cm/results?asset_id={a['id']}", headers=users["viewer"]).json()
    assert lst[0]["source"] == "Bently Nevada 3500" and lst[0]["block"] == "HA"
    # eskirgan natija hisobga olinmaydi (valid_hours)
    with SessionLocal() as db:
        from ges_server.orm import CmResult

        row = db.query(CmResult).filter_by(asset_id=a["id"]).one()
        row.ts = datetime.now(timezone.utc) - timedelta(hours=48)
        db.commit()
        assert sd.external_states(db, a["id"]) == []
    assert client.get(f"/api/assets/{a['id']}/cm", headers=users["viewer"]).json()["score"] == 100


def test_ingest_key_can_post_cm_results(client, users, admin):
    """CM gateway'i ingest kaliti bilan natija yuboradi (foydalanuvchi tokenisiz)."""
    pid = users["project_id"]
    a = _asset(client, users, name="Agregat 3")
    key = client.post(f"/api/projects/{pid}/ingest-key", headers=admin).json()["key"]
    body = {"asset_id": a["id"], "source": "SKF IMx", "block": "SD", "state": "alarm", "diagnosis": "BPFI energiyasi oshgan"}
    r = client.post(f"/api/projects/{pid}/cm/results", json=body, headers={"X-Ingest-Key": key})
    assert r.status_code == 201, r.text
    assert client.post(f"/api/projects/{pid}/cm/results", json=body, headers={"X-Ingest-Key": "yaroqsiz"}).status_code == 401
    with SessionLocal() as db:
        project = db.get(Project, pid)
        rep = cm.compute(db, project)
    item = next(x for x in rep["assets"] if x["asset_id"] == a["id"])
    assert item["score"] == 60 and item["state"] == "alarm"  # tashqi alarm: −40
    assert any("SKF IMx" in p for p in item["problems"])
