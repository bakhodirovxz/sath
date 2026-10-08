"""GesClient: parallel 401 da bitta refresh, timeout → ServerError, oqimli yuklash (.part, progress, bekor qilish).
Soxta urlopen bilan — server kerak emas."""

import io
import json
import sys
import threading
import time
from pathlib import Path
from urllib import error

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import server_client as sc  # noqa: E402


class FakeResp(io.BytesIO):
    def __init__(self, data: bytes, headers: dict | None = None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _http_error(code: int, url: str):
    return error.HTTPError(url, code, "x", {}, io.BytesIO(b'{"detail": "x"}'))


def test_concurrent_401_refreshes_once(monkeypatch):
    calls = {"refresh": 0}
    lock = threading.Lock()

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if url.endswith("/api/auth/refresh"):
            with lock:
                calls["refresh"] += 1
            time.sleep(0.05)
            return FakeResp(json.dumps({"access_token": "new", "refresh_token": "r2"}).encode())
        if req.get_header("Authorization") == "Bearer new":
            return FakeResp(b'{"ok": true}')
        raise _http_error(401, url)

    monkeypatch.setattr(sc.request, "urlopen", fake_urlopen)
    c = sc.GesClient("http://x", token="old")
    c.refresh_token = "r1"
    results = []
    ths = [threading.Thread(target=lambda: results.append(c.me())) for _ in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert results == [{"ok": True}] * 4
    assert calls["refresh"] == 1


def test_timeout_is_server_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(sc.request, "urlopen", fake_urlopen)
    with pytest.raises(sc.ServerError) as ei:
        sc.GesClient("http://x").health()
    assert ei.value.status == 0 and "timeout" in ei.value.message


def test_download_streams_with_progress(monkeypatch, tmp_path):
    data = b"x" * (3 * sc.CHUNK + 10)
    monkeypatch.setattr(
        sc.request, "urlopen", lambda req, timeout=None: FakeResp(data, {"Content-Length": str(len(data))})
    )
    seen = []
    dest = tmp_path / "v.ifc"
    sc.GesClient("http://x").download_version(1, dest, progress=lambda got, total: seen.append((got, total)))
    assert dest.read_bytes() == data
    assert seen[-1] == (len(data), len(data)) and len(seen) == 4
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_cancel_keeps_old_file(monkeypatch, tmp_path):
    data = b"y" * (3 * sc.CHUNK)
    monkeypatch.setattr(sc.request, "urlopen", lambda req, timeout=None: FakeResp(data))
    dest = tmp_path / "v.ifc"
    dest.write_bytes(b"OLD")
    n = {"i": 0}

    def cancelled():
        n["i"] += 1
        return n["i"] > 1

    with pytest.raises(sc.TransferCancelled):
        sc.GesClient("http://x").download_version(1, dest, cancelled=cancelled)
    assert dest.read_bytes() == b"OLD"
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_error_keeps_old_file(monkeypatch, tmp_path):
    class Broken(FakeResp):
        def read(self, n=-1):
            raise ConnectionResetError("uzildi")

    monkeypatch.setattr(sc.request, "urlopen", lambda req, timeout=None: Broken(b""))
    dest = tmp_path / "v.ifc"
    dest.write_bytes(b"OLD")
    with pytest.raises(sc.ServerError):
        sc.GesClient("http://x").download_version(1, dest)
    assert dest.read_bytes() == b"OLD"
    assert not dest.with_name(dest.name + ".part").exists()
