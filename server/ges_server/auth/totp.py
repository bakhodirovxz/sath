"""TOTP (RFC 6238, HMAC-SHA1, 30 s, 6 raqam) — tashqi kutubxonasiz; Google Authenticator/Aegis/FreeOTP mos."""

from __future__ import annotations

import base64
import hmac
import secrets
import struct
import time
from hashlib import sha1
from urllib.parse import quote

STEP_S = 30
DIGITS = 6


def new_secret() -> str:
    """160 bitli tasodifiy kalit, base32 (padding siz)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def hotp(secret_b32: str, counter: int) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    digest = hmac.new(key, struct.pack(">Q", counter), sha1).digest()
    off = digest[-1] & 0x0F
    code = (int.from_bytes(digest[off : off + 4], "big") & 0x7FFFFFFF) % (10**DIGITS)
    return f"{code:0{DIGITS}d}"


def counter_at(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // STEP_S)


def totp(secret_b32: str, t: float | None = None) -> str:
    return hotp(secret_b32, counter_at(t))


def verify(secret_b32: str, code: str, *, last_counter: int | None = None, window: int = 1, t: float | None = None) -> int | None:
    """Kod ±`window` qadam ichida mos kelsa mos kelgan hisoblagichni qaytaradi (takror ishlatishni
    `last_counter` bilan rad etadi — RFC 6238 §5.2), aks holda None."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    c0 = counter_at(t)
    for c in range(c0 - window, c0 + window + 1):
        if last_counter is not None and c <= last_counter:
            continue
        if hmac.compare_digest(hotp(secret_b32, c), code):
            return c
    return None


def otpauth_url(secret_b32: str, account: str, issuer: str = "Sath") -> str:
    label = quote(f"{issuer}:{account}", safe=":")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP_S}"
