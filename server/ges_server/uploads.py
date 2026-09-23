"""Yuklash chegaralari (L5): oqimli hajm nazorati (o'qish paytida — xotiraga olgandan keyin emas) va
Content-Length bo'yicha erta 413 (middleware)."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

CHUNK = 1 << 20


def too_large(max_bytes: int) -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, f"Fayl juda katta — chegara {max_bytes // (1024 * 1024)} MB"
    )


async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Butun faylni xotiraga — faqat chegara ichida; oshsa 413 (qolgani o'qilmaydi)."""
    parts: list[bytes] = []
    size = 0
    while chunk := await file.read(CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise too_large(max_bytes)
        parts.append(chunk)
    return b"".join(parts)


async def spool_limited(file: UploadFile, dest: Path, max_bytes: int) -> int:
    """Diskka oqim (atomik: `.part` → os.replace); chegara oshsa qisman fayl o'chiriladi va 413."""
    size, _sha, part = await spool_atomic(file, dest, max_bytes)
    os.replace(part, dest)
    return size


async def spool_atomic(file: UploadFile, dest: Path, max_bytes: int) -> tuple[int, str, Path]:
    """Diskka oqim vaqtinchalik `.part` faylga (dest bilan bir papkada, nuqta bilan boshlanadi — ro'yxatlarga
    tushmaydi) + sha256. Qaytaradi: (hajm, sha256 hex, part yo'li). Chaqiruvchi tekshirib bo'lgach
    `os.replace(part, dest)` (atomik) yoki `part.unlink()` qiladi. Chegara oshsa part o'chiriladi, 413."""
    size = 0
    h = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.parent / f".{dest.name}.{uuid.uuid4().hex}.part"
    try:
        with open(part, "wb") as fh:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise too_large(max_bytes)
                h.update(chunk)
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return size, h.hexdigest(), part


class MaxBodyMiddleware:
    """Content-Length ma'lum bo'lsa chegaradan katta so'rov tanasi o'qilmasdan 413 qaytadi (ASGI)."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for k, v in scope.get("headers", ()):
                if k == b"content-length":
                    try:
                        n = int(v)
                    except ValueError:
                        n = 0
                    if n > self.max_bytes:
                        body = b'{"detail":"So\'rov tanasi juda katta"}'
                        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                        await send({"type": "http.response.body", "body": body})
                        return
                    break
        await self.app(scope, receive, send)
