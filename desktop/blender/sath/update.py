"""Desktop yangilanishini yuklab olish va tekshirish (SEC-03) — bpy siz, pytest bilan sinaladi.

Oqim: /api/desktop/latest (product=blender) → paketni o'zi yuklab oladi (brauzerda ochmaydi) `.part` ga →
hajm + sha256 manifest bilan solishtiriladi → sozlamalarda ochiq kalit bo'lsa Ed25519 imzo tekshiriladi →
faqat shundan keyin fayl yakuniy nomga o'tkaziladi va foydalanuvchiga o'rnatish taklif qilinadi.
Mos kelmasa — fayl o'chiriladi, `UpdateError` (o'zbekcha xabar).

Imzolangan xabar — kanonik JSON {"kind","name","product","sha256","size","version"} (server
`ges_server/system/release.py` va `desktop/build/publish_desktop.py` bilan bir xil). Ed25519 tekshiruvi sof
Python (RFC 8032 §6 namunaviy algoritmi) — Blender Python ida `cryptography` bo'lmasa ham ishlaydi.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
from urllib import parse, request

PRODUCT = "blender"
SIGNED_FIELDS = ("kind", "name", "product", "sha256", "size", "version")
CHUNK = 1 << 20


class UpdateError(RuntimeError):
    """Yangilanish rad etildi (foydalanuvchiga ko'rsatiladigan o'zbekcha xabar)."""


# ---------- Ed25519 (RFC 8032 §6, faqat tekshirish) ----------

_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _add(a: tuple, b: tuple) -> tuple:
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s: int, pt: tuple) -> tuple:
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(a: tuple, b: tuple) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _decompress(s: bytes) -> tuple | None:
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    a = _decompress(public_key)
    r = _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % _Q
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


# ---------- Manifest ----------


def canonical_message(pkg: dict) -> bytes:
    payload = {k: pkg[k] for k in SIGNED_FIELDS}
    payload["size"] = int(payload["size"])
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def decode_public_key(text: str) -> bytes:
    t = text.strip()
    try:
        raw = bytes.fromhex(t) if len(t) == 64 else base64.b64decode(t, validate=True)
    except (ValueError, binascii.Error):
        raise UpdateError("Yangilanish ochiq kaliti noto'g'ri formatda (base64 yoki hex, 32 bayt)") from None
    if len(raw) != 32:
        raise UpdateError("Yangilanish ochiq kaliti 32 bayt bo'lishi kerak")
    return raw


def key_id(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()[:16]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify_package(path: Path, pkg: dict, public_key: str = "") -> dict:
    """Yuklangan faylni manifest bilan tekshiradi. Qaytaradi: {"sha256": ..., "signed": bool}.
    Ochiq kalit berilgan bo'lsa imzo MAJBURIY (imzosiz yoki noto'g'ri — rad)."""
    for k in ("size", "sha256", "name", "version", "kind"):
        if not pkg.get(k):
            raise UpdateError(f"Server manifestida «{k}» yo'q — paket tekshirib bo'lmaydi, o'rnatilmaydi")
    size = path.stat().st_size
    if size != int(pkg["size"]):
        raise UpdateError(f"Paket hajmi mos emas ({size} ≠ {pkg['size']} bayt) — yuklash buzilgan, o'rnatilmaydi")
    digest = sha256_file(path)
    if digest != str(pkg["sha256"]).lower():
        raise UpdateError("Paket sha256 mos emas — fayl buzilgan yoki almashtirilgan, o'rnatilmaydi")
    signed = False
    if public_key.strip():
        pub = decode_public_key(public_key)
        sig_b64 = pkg.get("signature") or ""
        if not sig_b64:
            raise UpdateError("Paket imzolanmagan, sozlamalarda esa imzo kaliti bor — o'rnatilmaydi")
        if pkg.get("key_id") and pkg["key_id"] != key_id(pub):
            raise UpdateError("Paket boshqa kalit bilan imzolangan (key_id mos emas) — o'rnatilmaydi")
        try:
            sig = base64.b64decode(sig_b64, validate=True)
        except (ValueError, binascii.Error):
            raise UpdateError("Paket imzosi buzilgan — o'rnatilmaydi") from None
        if not ed25519_verify(pub, canonical_message({**pkg, "product": pkg.get("product") or PRODUCT}), sig):
            raise UpdateError("Paket imzosi noto'g'ri (Ed25519) — soxta yoki buzilgan paket, o'rnatilmaydi")
        signed = True
    return {"sha256": digest, "signed": signed}


def latest(client, product: str = PRODUCT) -> dict | None:
    """Serverdagi eng yangi paket (mahsulot bo'yicha) yoki None."""
    from .shared.server_client import ServerError

    try:
        return client._json("GET", "/api/desktop/latest", params={"product": product})
    except ServerError as e:
        if e.status == 404:
            return None
        raise


def download_and_verify(client, pkg: dict, dest_dir: Path, public_key: str = "", progress=None) -> Path:
    """Paketni yuklab oladi (`.part`), tekshiradi, yakuniy nomga o'tkazadi. Xato — UpdateError, fayl o'chiriladi.
    `progress(olingan, jami)` — ixtiyoriy."""
    name = Path(str(pkg.get("name") or "")).name
    if not name or name != pkg.get("name"):
        raise UpdateError("Server manifestidagi fayl nomi noto'g'ri")
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / name
    part = dest_dir / f".{name}.part"
    expected = int(pkg.get("size") or 0)
    # qisqa muddatli yuklab olish tokeni (sessiya tokeni URL/log ga tushmaydi; 401 da client o'zi yangilaydi)
    tok = client._json("POST", "/api/desktop/download-token")["token"]
    url = f"{client.base_url}{pkg['url']}?{parse.urlencode({'token': tok})}"
    if not url.lower().startswith(("https://", "http://")):
        raise UpdateError("Yuklab olish manzili noto'g'ri")
    try:
        got = 0
        with request.urlopen(request.Request(url), timeout=client.timeout) as resp, open(part, "wb") as fh:  # noqa: S310
            while chunk := resp.read(CHUNK):
                got += len(chunk)
                if expected and got > expected:
                    raise UpdateError("Server manifestdagidan katta fayl yubordi — o'rnatilmaydi")
                fh.write(chunk)
                if progress:
                    progress(got, expected)
        verify_package(part, pkg, public_key)
        os.replace(part, final)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except OSError as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Yuklab olishda xato: {e}") from None
    return final
