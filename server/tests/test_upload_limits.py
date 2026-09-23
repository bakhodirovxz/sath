"""L5: yuklash chegaralari (oqimda 413), Content-Length middleware, parser sandboxi."""

import asyncio
import io
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import manual_headers
from fastapi import HTTPException, UploadFile
from ges_server import sandbox, uploads
from ges_server.config import get_settings


class CountingFile(io.BytesIO):
    """Nechta bayt o'qilganini sanaydi — chegaradan keyin o'qilmasligini tekshirish uchun."""

    def __init__(self, data: bytes):
        super().__init__(data)
        self.read_bytes = 0

    def read(self, n=-1):
        b = super().read(n)
        self.read_bytes += len(b)
        return b


def test_read_limited_stops_early():
    f = CountingFile(b"x" * (5 << 20))
    up = UploadFile(f, filename="big.csv")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(uploads.read_limited(up, 2 << 20))
    assert ei.value.status_code == 413
    assert f.read_bytes <= 3 << 20  # 5 MB ning hammasi xotiraga olinmagan


def test_spool_limited_removes_partial(tmp_path: Path):
    up = UploadFile(io.BytesIO(b"y" * (3 << 20)), filename="pkg.zip")
    dest = tmp_path / "pkg.zip"
    with pytest.raises(HTTPException) as ei:
        asyncio.run(uploads.spool_limited(up, dest, 1 << 20))
    assert ei.value.status_code == 413 and not dest.exists()
    up2 = UploadFile(io.BytesIO(b"z" * 1000), filename="ok.zip")
    assert asyncio.run(uploads.spool_limited(up2, dest, 1 << 20)) == 1000 and dest.stat().st_size == 1000


def test_csv_import_over_limit_413(client, users, monkeypatch):
    """Qabul mezoni: hajmi oshgan yuklash 413 beradi va xotirani bosmaydi (oqimda to'xtaydi)."""
    monkeypatch.setattr(get_settings(), "small_upload_mb", 1)
    pid = users["project_id"]
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "T1", "name": "T", "kind": "value"}, headers=users["engineer"])
    sid = r.json()["id"]
    big = b"2026-01-01T00:00:00Z,1.0\n" * 60_000  # ~1.5 MB
    r = client.post(f"/api/sensors/{sid}/import", files={"file": ("big.csv", big, "text/csv")}, headers=manual_headers(client, users))
    assert r.status_code == 413, r.text
    small = b"ts,value\n2026-01-01T00:00:00Z,1.0\n2026-01-01T00:01:00Z,2.0\n"
    r = client.post(f"/api/sensors/{sid}/import", files={"file": ("ok.csv", small, "text/csv")}, headers=manual_headers(client, users))
    assert r.status_code == 200 and r.json()["accepted"] == 2


def test_bcf_import_over_limit_413(client, users, monkeypatch):
    monkeypatch.setattr(get_settings(), "small_upload_mb", 1)
    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("blob.bin", b"\x00" * (2 << 20))
    r = client.post(f"/api/models/{mid}/issues/bcf", files={"file": ("big.bcfzip", buf.getvalue(), "application/zip")}, headers=users["engineer"])
    assert r.status_code == 413, r.text


def test_content_length_middleware_early_413(client, admin, monkeypatch):
    """Content-Length chegaradan katta — tana o'qilmasdan 413 (desktop yuklash yo'li)."""
    r = client.post(
        "/api/desktop/upload",
        headers={**admin, "Content-Type": "multipart/form-data; boundary=x", "Content-Length": str(get_settings().max_upload_mb * 1024 * 1024 + (2 << 20))},
        content=b"",
    )
    assert r.status_code == 413


def test_sandbox_runs_and_times_out(tmp_path: Path):
    r = sandbox.run([sys.executable, "-c", "print('salom')"], cwd=tmp_path, timeout_s=30)
    assert r.returncode == 0 and b"salom" in r.stdout
    with pytest.raises(sandbox.SandboxError):
        sandbox.run([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path, timeout_s=1)
    with pytest.raises(sandbox.SandboxError):
        sandbox.run([sys.executable, "-c", "raise SystemExit(3)"], cwd=tmp_path, timeout_s=10, check=True)
    with pytest.raises(sandbox.SandboxError):
        sandbox.run(["/yoq/bunday/dastur"], cwd=tmp_path, timeout_s=10)


def test_sandbox_isolates_blender_profile(tmp_path: Path):
    """CAD-08: konverter (Blender --factory-startup) foydalanuvchi profiliga emas, ish papkasiga yo'naltiriladi."""
    r = sandbox.run([sys.executable, "-c", "import os; print(os.environ['BLENDER_USER_RESOURCES'])"], cwd=tmp_path, timeout_s=30)
    assert Path(r.stdout.decode().strip()).parent == tmp_path


def test_sandbox_mode_selection(monkeypatch):
    s = get_settings()
    sandbox.mode.cache_clear()
    monkeypatch.setattr(s, "sandbox", "off")
    assert sandbox.mode() == "off"
    sandbox.mode.cache_clear()
    monkeypatch.setattr(s, "sandbox", "auto")
    m = sandbox.mode()
    assert m == ("off" if sys.platform == "win32" else m in ("bwrap", "rlimit") and m)
    sandbox.mode.cache_clear()


@pytest.mark.skipif(sys.platform == "win32", reason="rlimit faqat POSIX")
def test_sandbox_rlimit_memory(tmp_path: Path, monkeypatch):
    sandbox.mode.cache_clear()
    monkeypatch.setattr(get_settings(), "sandbox", "rlimit")
    r = sandbox.run([sys.executable, "-c", "x = bytearray(3 << 30)"], cwd=tmp_path, timeout_s=30, mem_mb=512)
    assert r.returncode != 0  # MemoryError — 512 MB chegarasi
    sandbox.mode.cache_clear()
