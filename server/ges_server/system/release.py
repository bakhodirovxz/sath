"""Desktop paketlari manifesti va Ed25519 imzosi (SEC-03).

Dizayn:
- Imzo kaliti (Ed25519 private) serverda EMAS — nashr qiluvchida (CI yoki admin kompyuteri,
  `desktop/build/publish_desktop.py --signing-key`). Server buzilsa ham imzolangan paketni soxtalashtira
  olmaydi; klient (Blender addoni) o'zida saqlangan ochiq kalit bilan tekshiradi.
- Server yuklashda sha256/hajmni o'zi hisoblaydi (nashr qiluvchi bergan qiymat bilan solishtiradi), ochiq
  kalit sozlangan bo'lsa (GES_DESKTOP_SIGNING_PUBLIC_KEY) imzoni tekshiradi, GES_DESKTOP_REQUIRE_SIGNATURE=true
  bo'lsa imzosiz paketni rad etadi. Manifest `<paket>.manifest.json` da saqlanadi.
- Imzolanadigan xabar — kanonik JSON: {"kind","name","product","sha256","size","version"} (kalitlar
  tartiblangan, bo'shliqsiz, ASCII). Xuddi shu funksiya publish_desktop.py va addon (sath/update.py) da.
- key_id — ochiq kalit (32 bayt) sha256 ining birinchi 16 hex belgisi.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

PRODUCTS = ("blender", "freecad")
DEFAULT_PRODUCT = "blender"  # asosiy desktop — Blender + FreeCAD dvigatel (web «Sath yuklab olish»)
SIGNED_FIELDS = ("kind", "name", "product", "sha256", "size", "version")


def canonical_message(manifest: dict) -> bytes:
    payload = {k: manifest[k] for k in SIGNED_FIELDS}
    payload["size"] = int(payload["size"])
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def decode_public_key(text: str) -> bytes:
    """Ochiq kalit: base64 (32 bayt xom Ed25519) yoki 64 hex belgi."""
    t = text.strip()
    try:
        raw = bytes.fromhex(t) if len(t) == 64 else base64.b64decode(t, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError("Ochiq kalit formati: base64 yoki hex (32 bayt Ed25519)") from e
    if len(raw) != 32:
        raise ValueError("Ed25519 ochiq kaliti 32 bayt bo'lishi kerak")
    return raw


def key_id(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()[:16]


def verify(public_key: bytes, manifest: dict, signature_b64: str) -> bool:
    """Imzo to'g'rimi (cryptography kutubxonasi — server bog'liqligi)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        sig = base64.b64decode(signature_b64, validate=True)
    except (ValueError, binascii.Error):
        return False
    if len(sig) != 64:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(sig, canonical_message(manifest))
        return True
    except InvalidSignature:
        return False


def sign(private_key_raw: bytes, manifest: dict) -> str:
    """Nashr qiluvchi uchun (publish_desktop.py va testlar): base64 imzo."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.from_private_bytes(private_key_raw)
    return base64.b64encode(sk.sign(canonical_message(manifest))).decode("ascii")
