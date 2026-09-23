"""HTTP xavfsizlik sarlavhalari (OPS-01) — ilovaning o'zida (Caddy siz ishga tushirilganda ham).

CSP: SPA faqat o'z manbasidan (`script-src 'self'`, web-ifc wasm uchun `'wasm-unsafe-eval'`), ulanishlar —
faqat shu host (`connect-src 'self'` + shu hostga ws/wss; boshqa hostga WebSocket yo'q). Inline style —
three.js/React uslublari uchun. `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy`; HTTPS bo'lsa (yoki ishonchli proksi `X-Forwarded-Proto: https`
bersa) HSTS. Javobda sarlavha allaqachon bo'lsa almashtirilmaydi. `/docs`, `/redoc` (Swagger CDN va inline
skript) — qat'iy CSP siz.
"""

from __future__ import annotations

import re

_HOST_OK = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](:\d{1,5})?$")
_DOCS = ("/docs", "/redoc", "/openapi.json")

HSTS = "max-age=31536000; includeSubDomains"


def csp(host: str | None) -> str:
    connect = "'self'"
    if host and _HOST_OK.match(host):
        connect += f" ws://{host} wss://{host}"  # eski brauzerlarda 'self' ws(s) ni qamramaydi
    return (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        f"connect-src {connect} blob: data:; worker-src 'self' blob:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
    )


class SecurityHeadersMiddleware:
    """ASGI: har HTTP javobiga xavfsizlik sarlavhalari (WebSocket ga tegmaydi)."""

    def __init__(self, app, trust_forwarded: bool = False):
        self.app = app
        self.trust_forwarded = trust_forwarded

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", ())}
        host = headers.get(b"host", b"").decode("latin-1")
        https = scope.get("scheme") == "https" or (
            self.trust_forwarded and headers.get(b"x-forwarded-proto", b"").split(b",")[0].strip() == b"https"
        )
        path = scope.get("path", "")
        extra = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
        ]
        if not path.startswith(_DOCS):
            extra.append((b"content-security-policy", csp(host).encode("latin-1")))
        if https:
            extra.append((b"strict-transport-security", HSTS.encode()))

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", ())}
                message["headers"] = list(message.get("headers", ())) + [
                    (k, v) for k, v in extra if k not in existing
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)
