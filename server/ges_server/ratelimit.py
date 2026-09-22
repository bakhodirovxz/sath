"""Tezlik cheklovi (L1): jarayon ichidagi sirpanuvchi oyna, kalit bo'yicha (IP, foydalanuvchi, loyiha).

Login brute force, ingest toshqini, buyruq/sim spamini cheklaydi. Holat jarayon xotirasida — ko'p
replikali deployda har replika o'z hisobini yuritadi (chegara replika soniga ko'paytiriladi; umumiy
backplane L4/L8 da). Hisobni bloklash (lockout) esa DB da (`User.locked_until`) — replikalar orasida umumiy.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from .config import get_settings


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._last_gc = 0.0

    def hit(self, key: str, limit: int, window_s: float = 60.0, now: float | None = None) -> float | None:
        """Urinishni qayd etadi. Chegara oshgan bo'lsa qancha soniyadan keyin bo'shashini qaytaradi
        (urinish qayd etilmaydi), aks holda None. `limit <= 0` — cheklov o'chirilgan."""
        if limit <= 0:
            return None
        t = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                q = self._hits[key] = deque()
            cutoff = t - window_s
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                return max(0.0, q[0] + window_s - t)
            q.append(t)
            if t - self._last_gc > window_s:
                self._last_gc = t
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """Klient IP; teskari proksi ortida (`rate_trust_forwarded`) X-Forwarded-For ning birinchi manzili."""
    if get_settings().rate_trust_forwarded:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _raise(bucket: str, retry_after: float) -> None:
    secs = max(1, math.ceil(retry_after))
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Juda ko'p so'rov ({bucket}); {secs} soniyadan keyin urinib ko'ring",
        headers={"Retry-After": str(secs)},
    )


def check(bucket: str, key: str, per_min: int) -> None:
    """Chegara oshsa 429 (Retry-After bilan)."""
    ra = limiter.hit(f"{bucket}:{key}", per_min)
    if ra is not None:
        _raise(bucket, ra)


def by_ip(bucket: str, setting: str):
    """Dependency: IP bo'yicha chegara; `setting` — Settings dagi `*_per_min` maydoni."""

    def _dep(request: Request) -> None:
        check(bucket, client_ip(request), getattr(get_settings(), setting))

    return Depends(_dep)


LoginLimit = Annotated[None, by_ip("login", "rate_login_per_min")]
