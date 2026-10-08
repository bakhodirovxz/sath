"""Headless testlar uchun soxta Sath serveri (stdlib http.server, alohida oqim). Marshrut → (status, body) funksiyasi;
`?` dan keyingi qism e'tiborga olinmaydi. Kechikish funksiya ichida time.sleep bilan."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def js(obj, status: int = 200):
    return lambda: (status, json.dumps(obj).encode())


def serve(routes: dict) -> tuple[str, callable]:
    class H(BaseHTTPRequestHandler):
        def _go(self):
            fn = routes.get((self.command, self.path.split("?")[0]))
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            status, body = fn() if fn else (404, b'{"detail": "yo\'q"}')
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _go

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv.shutdown
