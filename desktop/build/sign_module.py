"""Uchinchi tomon Sath modulini Ed25519 bilan imzolash: <papka>/sath_module.sig yoziladi (sof Python, RFC 8032).

  python desktop/build/sign_module.py --new-key kalit.txt          # yangi maxfiy kalit + ochiq kalitni chiqaradi
  python desktop/build/sign_module.py <modul_papkasi> --key kalit.txt

Imzolangan xabar — sath.core.registry.module_message (fayllar sha256 + id + version). Ochiq kalit (base64) ilovada
Sozlamalar → Sath → «Modul kalitlari» ga yoziladi. Maxfiy kalit faylini repo ga qo'shmang.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import update  # noqa: E402
from sath.core import registry  # noqa: E402


def _h(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _compress(pt: tuple) -> bytes:
    zinv = update._inv(pt[2])
    x, y = pt[0] * zinv % update._P, pt[1] * zinv % update._P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _expand(seed: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _compress(update._mul(a, update._G))


def sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(seed)
    pub = _compress(update._mul(a, update._G))
    r = _h(prefix + msg) % update._Q
    big_r = _compress(update._mul(r, update._G))
    h = _h(big_r + pub + msg) % update._Q
    s = (r + h * a) % update._Q
    return big_r + int.to_bytes(s, 32, "little")


def sign_module(path: Path, seed: bytes) -> Path:
    m = registry.parse_manifest((path / registry.MANIFEST).read_text(encoding="utf-8"), path, "user")
    out = path / registry.SIGNATURE
    out.write_text(base64.b64encode(sign(seed, registry.module_message(path, m))).decode("ascii") + "\n", encoding="ascii")
    return out


def _read_seed(path: Path) -> bytes:
    t = path.read_text(encoding="ascii").strip()
    raw = bytes.fromhex(t) if len(t) == 64 else base64.b64decode(t, validate=True)
    if len(raw) != 32:
        raise SystemExit("maxfiy kalit 32 bayt bo'lishi kerak (hex yoki base64)")
    return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module_dir", type=Path, nargs="?")
    ap.add_argument("--key", type=Path, help="maxfiy kalit fayli (32 bayt: hex yoki base64)")
    ap.add_argument("--new-key", type=Path, help="yangi maxfiy kalit yaratib shu faylga yozish")
    a = ap.parse_args(argv)
    if a.new_key:
        if a.new_key.exists():
            ap.error(f"{a.new_key} allaqachon bor — ustidan yozilmaydi")
        seed = os.urandom(32)
        a.new_key.write_text(seed.hex() + "\n", encoding="ascii")
        print("ochiq kalit:", base64.b64encode(public_key(seed)).decode())
        return 0
    if a.module_dir is None or a.key is None:
        ap.error("modul papkasi va --key kerak")
    seed = _read_seed(a.key)
    print("imzo:", sign_module(a.module_dir, seed))
    print("ochiq kalit:", base64.b64encode(public_key(seed)).decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
