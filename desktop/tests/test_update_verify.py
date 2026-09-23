"""SEC-03: addon yangilanish tekshiruvi (sath/update.py) — Blender siz. Hajm, sha256, Ed25519 imzo; manifest
kanonik formati server (release.py) va publish_desktop.py bilan bir xil."""

import base64
import hashlib
import http.server
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
sys.path.insert(0, str(ROOT / "desktop" / "build"))

from sath import update  # noqa: E402

crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
from cryptography.hazmat.primitives import serialization  # noqa: E402


def _key():
    sk = crypto.Ed25519PrivateKey.generate()
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sk, pub, base64.b64encode(pub).decode()


def _pkg(body: bytes, sk=None, **over) -> dict:
    pkg = {
        "product": "blender",
        "version": "0.4.0",
        "kind": "zip",
        "name": "Sath-0.4.0-Windows-x86_64.zip",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "url": "/api/desktop/download/blender/Sath-0.4.0-Windows-x86_64.zip",
    }
    if sk is not None:
        pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        pkg["signature"] = base64.b64encode(sk.sign(update.canonical_message(pkg))).decode()
        pkg["key_id"] = hashlib.sha256(pub).hexdigest()[:16]
    pkg.update(over)
    return pkg


def test_pure_ed25519_matches_cryptography():
    sk, pub, _ = _key()
    for msg in (b"", b"sath", bytes(range(256)) * 3):
        sig = sk.sign(msg)
        assert update.ed25519_verify(pub, msg, sig)
        assert not update.ed25519_verify(pub, msg + b"x", sig)
        assert not update.ed25519_verify(pub, msg, sig[:-1] + bytes([sig[-1] ^ 1]))
    # RFC 8032 7.1 TEST 1 (bo'sh xabar)
    pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    sig = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    assert update.ed25519_verify(pk, b"", sig)


def test_canonical_message_same_everywhere():
    import publish_desktop

    sys.path.insert(0, str(ROOT / "server"))
    from ges_server.system import release

    pkg = _pkg(b"abc")
    assert update.canonical_message(pkg) == release.canonical_message(pkg) == publish_desktop.canonical_message(pkg)


def test_verify_package_size_sha_signature(tmp_path):
    body = b"sath-bundle" * 1000
    f = tmp_path / "p.zip"
    f.write_bytes(body)
    sk, _pub, pub_b64 = _key()
    ok = _pkg(body, sk)
    assert update.verify_package(f, ok, pub_b64) == {"sha256": ok["sha256"], "signed": True}
    assert update.verify_package(f, _pkg(body), "")["signed"] is False  # kalit sozlanmagan — faqat sha256
    with pytest.raises(update.UpdateError, match="sha256 mos emas"):
        update.verify_package(f, {**ok, "sha256": "0" * 64}, pub_b64)
    with pytest.raises(update.UpdateError, match="hajmi mos emas"):
        update.verify_package(f, {**ok, "size": len(body) + 1}, pub_b64)
    with pytest.raises(update.UpdateError, match="imzolanmagan"):
        update.verify_package(f, _pkg(body), pub_b64)
    other, _, other_b64 = _key()
    with pytest.raises(update.UpdateError, match="key_id"):
        update.verify_package(f, _pkg(body, other), pub_b64)
    # boshqa versiya uchun imzo (replay) — rad
    forged = {**ok, "version": "9.9.9"}
    with pytest.raises(update.UpdateError, match="imzosi noto'g'ri"):
        update.verify_package(f, forged, pub_b64)


class _Client:
    """GesClient o'rnini bosuvchi: download-token va base_url."""

    timeout = 10

    def __init__(self, base_url):
        self.base_url = base_url

    def _json(self, method, path, **kw):
        assert (method, path) == ("POST", "/api/desktop/download-token")
        return {"token": "t"}


def _serve(body: bytes):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_download_and_verify_rejects_tampered_file(tmp_path):
    """Server boshqa (buzilgan/almashtirilgan) fayl bersa — o'rnatilmaydi, fayl qolmaydi."""
    real = b"haqiqiy paket" * 100
    sk, _pub, pub_b64 = _key()
    pkg = _pkg(real, sk)
    srv, url = _serve(b"soxta paket!!" * 100)  # hajmi bir xil, mazmuni boshqa
    try:
        with pytest.raises(update.UpdateError, match="sha256 mos emas"):
            update.download_and_verify(_Client(url), pkg, tmp_path, pub_b64)
    finally:
        srv.shutdown()
    assert not any(tmp_path.iterdir())
    srv, url = _serve(real)
    try:
        path = update.download_and_verify(_Client(url), pkg, tmp_path, pub_b64)
    finally:
        srv.shutdown()
    assert path.read_bytes() == real and path.name == pkg["name"]
    assert not list(tmp_path.glob(".*.part"))
