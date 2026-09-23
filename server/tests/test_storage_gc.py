"""SRV-05: fayl ombori GC — murojaatsiz blob, hosilaviy kesh, eskirgan vaqtinchalik fayllar; dry-run; grace."""

import io
import os
import time

from conftest import upload
from ges_server.config import get_settings
from ges_server.db import SessionLocal
from ges_server.models import blob_gc, storage


def _age(p, hours):
    t = time.time() - hours * 3600
    os.utime(p, (t, t))


def _model(client, users, name="GC"):
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": name}, headers=users["engineer"])
    return r.json()["id"]


def _no_bg_gc(monkeypatch):
    """Fon navbatidagi kunlik GC test fayllarini oldinroq o'chirib yubormasin."""
    from ges_server import jobs

    monkeypatch.setitem(jobs.HANDLERS, "blob_gc", lambda payload: None)


def test_gc_removes_only_old_unreferenced(client, users, admin, ifc_file, monkeypatch):
    _no_bg_gc(monkeypatch)
    mid = _model(client, users)
    v = upload(client, users["engineer"], mid, ifc_file).json()
    kept = storage.resolve(v["file_sha256"])
    orphan_sha, _ = storage.store(io.BytesIO(b"rad etilgan yuklash"))
    orphan = storage.resolve(orphan_sha)
    fresh_sha, _ = storage.store(io.BytesIO(b"hali commit bo'lmagan yuklash"))
    fresh = storage.resolve(fresh_sha)
    derived = get_settings().data_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    orphan_frag = derived / f"{orphan_sha}.frag"
    orphan_frag.write_bytes(b"x")
    part = derived / f"{orphan_sha}.frag.part"
    part.write_bytes(b"x")
    tmp = get_settings().files_dir / "tmpabc123"
    tmp.write_bytes(b"uzilgan")
    for p in (kept, orphan, orphan_frag, part, tmp):
        _age(p, 48)

    # dry-run: hech narsa o'chmaydi, hisobot bor
    r = client.post("/api/admin/storage/gc", json={"dry_run": True}, headers=admin)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["dry_run"] and rep["blobs"] >= 1 and rep["temp"] >= 2 and rep["derived"] >= 1
    assert orphan.exists() and tmp.exists()

    rep = client.post("/api/admin/storage/gc", json={"dry_run": False}, headers=admin).json()
    assert not orphan.exists() and not orphan_frag.exists() and not part.exists() and not tmp.exists()
    assert kept.exists()  # versiya murojaat qiladi
    assert fresh.exists() and rep["kept_recent"] >= 1  # grace oynasi ichida
    acts = client.get("/api/audit", params={"action": "storage.gc"}, headers=admin).json()
    assert len(acts) == 1
    # ruxsat va grace chegarasi
    assert client.post("/api/admin/storage/gc", json={}, headers=users["approver"]).status_code == 403
    assert client.post("/api/admin/storage/gc", json={"grace_hours": 0}, headers=admin).status_code == 422


def test_dedup_store_refreshes_mtime(ifc_file, monkeypatch):
    """Mavjud faylga dedup — mtime yangilanadi (parallel yuklash va GC poygasi)."""
    _no_bg_gc(monkeypatch)
    with open(ifc_file, "rb") as fh:
        sha, _ = storage.store(fh)
    p = storage.resolve(sha)
    _age(p, 48)
    with open(ifc_file, "rb") as fh:
        storage.store(fh)
    assert p.stat().st_mtime > time.time() - 60
    with SessionLocal() as db:
        rep = blob_gc.collect(db, dry_run=False)
    assert p.exists() and rep["kept_recent"] >= 1


def test_daily_gc_job_enqueued_on_upload(client, users, ifc_file):
    from ges_server.orm import Job

    mid = _model(client, users)
    upload(client, users["engineer"], mid, ifc_file)
    with SessionLocal() as db:
        assert db.query(Job).filter(Job.kind == "blob_gc").count() == 1
