import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..config import get_settings

_hasher = PasswordHasher()
ALGORITHM = "HS256"
# L2: tokenlar boshqa xizmat/ilova uchun yaroqsiz — iss/aud tekshiriladi
ISSUER = "sath"
AUDIENCE = "sath-api"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# Eng ko'p uchraydigan parollar (NIST SP 800-63B §5.1.1.2 — bloklash ro'yxati; qisqa, lokal variantlar bilan)
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "passw0rd", "12345678", "123456789", "1234567890", "qwerty123", "qwertyuiop",
        "admin123", "admin1234", "administrator", "letmein1", "welcome1", "iloveyou", "sunshine", "princess",
        "football", "baseball", "superman", "trustno1", "changeme", "p@ssw0rd", "abc12345", "11111111",
        "sath1234", "parol123", "parol1234", "toshkent1", "uzbekistan", "samarkand",
    }
)


def privileged_min_length() -> int:
    """AUTH-01: administrator va tasdiqlovchi uchun minimal uzunlik (default 12; `password_min_length_privileged`
    sozlamasi bo'lsa — o'sha; umumiy minimaldan kam bo'lmaydi)."""
    s = get_settings()
    return max(s.password_min_length, int(getattr(s, "password_min_length_privileged", 12)))


def password_problems(password: str, username: str = "", min_length: int | None = None) -> list[str]:
    """Parol siyosati (L2, NIST 800-63B): uzunlik, bloklash ro'yxati, login bilan mos kelmaslik,
    kamida ikki belgi sinfi (faqat raqam/faqat harf emas). Bo'sh ro'yxat — parol qabul qilinadi.
    `min_length` — rolga qarab kuchaytirilgan minimal (masalan admin/tasdiqlovchi uchun 12)."""
    s = get_settings()
    out: list[str] = []
    need = max(s.password_min_length, min_length or 0)
    if len(password) < need:
        out.append(f"kamida {need} belgi")
    if len(password) > 128:
        out.append("128 belgidan oshmasin")
    low = password.lower()
    if low in COMMON_PASSWORDS or re.sub(r"[^a-z0-9]", "", low) in COMMON_PASSWORDS:
        out.append("juda keng tarqalgan parol")
    if username and len(username) >= 3 and username.lower() in low:
        out.append("login parol ichida bo'lmasin")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 2:
        out.append("harf va raqam (yoki boshqa belgi) aralash bo'lsin")
    if len(set(password)) < 4:
        out.append("juda bir xil belgilar")
    return out


def create_access_token(
    user_id: int,
    minutes: int | None = None,
    scope: str = "session",
    *,
    ver: int = 0,
    sid: str | None = None,
    sn: int | None = None,
    seconds: int | None = None,
) -> str:
    """scope="session" — oddiy kirish tokeni; boshqa scope — tor maqsadli, qisqa muddatli token.
    `ver` — foydalanuvchining token versiyasi (parol/rol o'zgarsa oshadi → eski tokenlar yaroqsiz),
    `sid` — sessiya (refresh) identifikatori (logout shu sessiyani bekor qiladi), `sn` — sessiya qatori
    (barqaror id; AUTH-01: har so'rovda sessiya bekor qilinmaganligi tekshiriladi), `seconds` — muddat soniyada."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl = timedelta(seconds=seconds) if seconds else timedelta(minutes=minutes or settings.access_token_minutes)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "iat": now,
        "exp": now + ttl,
        "scope": scope,
        "ver": ver,
        "jti": secrets.token_urlsafe(12),
    }
    if sid:
        payload["sid"] = sid
    if sn is not None:
        payload["sn"] = sn
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, jti: str, hours: float, ver: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=hours),
        "scope": "refresh",
        "ver": ver,
        "jti": jti,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, scope: str = "session") -> dict | None:
    """Imzo, muddat, iss/aud va scope mos bo'lsa payload (sub — int), aks holda None.

    AUTH-01: sessiya tokeni (`sn` bilan) — sessiya bekor qilingan bo'lsa (logout, sessiyani yopish) darhol
    yaroqsiz (qisqa muddatli kesh, HA da ≤ 5 s)."""
    try:
        payload = jwt.decode(
            token, get_settings().secret_key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER
        )
        if payload.get("scope", "session") != scope:
            return None
        payload["sub"] = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    from . import sessions  # aylanma import: sessions → security

    if scope == "session" and payload.get("sn") is not None:
        try:
            if not sessions.session_alive(int(payload["sn"]), payload["sub"]):
                return None
        except (TypeError, ValueError):
            return None
    return payload


def decode_access_token(token: str, scope: str = "session") -> int | None:
    """Token yaroqli va scope mos bo'lsa user_id, aks holda None. Token versiyasi tekshirilmaydi —
    to'liq tekshiruv `deps.user_from_token`."""
    p = decode_token(token, scope)
    return p["sub"] if p else None
