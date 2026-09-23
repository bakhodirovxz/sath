"""Yuklab olish javoblari uchun yordamchilar (SRV-03).

`Content-Disposition` sarlavhasi latin-1 da kodlanadi: kirill/o'zbek nomli fayl (`To'g'on`, `Тўғон`) to'g'ridan-
to'g'ri `filename="..."` ga qo'yilsa Starlette 500 beradi, qo'shtirnoq yoki CR/LF esa sarlavhani buzadi
(header injection). RFC 6266 + RFC 5987: ASCII zaxira nom (`filename=`) va to'liq UTF-8 nom (`filename*=`).
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

# Boshqaruv belgilari (CR/LF ham), qo'shtirnoq, teskari chiziq — butunlay olib tashlanadi
_STRIP = re.compile(r'[\x00-\x1f\x7f"\\]')
# Yo'l ajratgichlar — fayl nomida bo'lmasin (brauzer ham olib tashlaydi, lekin aniq bo'lsin)
_SEP = re.compile(r"[/]")
_ASCII_OK = re.compile(r"[A-Za-z0-9._()+,=@ -]")


def safe_filename(name: str, default: str = "download") -> str:
    """Nomni tozalaydi: boshqaruv belgilari, qo'shtirnoq, teskari chiziq olib tashlanadi, `/` → `_`."""
    clean = _SEP.sub("_", _STRIP.sub("", name or "")).strip().strip(".")
    return clean[:200] or default


def ascii_fallback(name: str) -> str:
    """ASCII zaxira nom: diakritikalar asosiy harfga (NFKD), qolgan ASCII bo'lmagan belgilar `_`."""
    out = []
    for ch in unicodedata.normalize("NFKD", name):
        if unicodedata.combining(ch):
            continue
        out.append(ch if _ASCII_OK.fullmatch(ch) else "_")
    return "".join(out) or "download"


def content_disposition(name: str, disposition: str = "attachment") -> str:
    """`attachment; filename="<ascii>"; filename*=UTF-8''<percent-encoded>` — har qanday nom uchun xavfsiz."""
    clean = safe_filename(name)
    return f"{disposition}; filename=\"{ascii_fallback(clean)}\"; filename*=UTF-8''{quote(clean, safe='')}"
