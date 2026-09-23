"""Kuzatuvchanlik (SRV-06): strukturalangan log (JSON yoki matn), so'rov identifikatori, Prometheus metrikalari.

- Log: `GES_LOG_FORMAT=json|text` (default text), `GES_LOG_LEVEL` (INFO). Har yozuvda `request_id` (HTTP so'rov
  ichida bo'lsa). JSON — bir qator bitta obyekt (Loki/ELK uchun).
- So'rov id: kiruvchi `X-Request-ID` (xavfsiz belgilar, ≤64) yoki yangi; javobda `X-Request-ID`.
- Metrikalar: `GET /api/metrics` (Prometheus text exposition 0.0.4). prometheus_client kerak emas — kichik
  o'z hisoblagichlari: HTTP so'rovlar (method, status), davomiylik (yig'indi/soni), ingest so'rovlari,
  ish navbati chuqurligi (sim_jobs / jobs holati bo'yicha, scrape paytida DB dan). Himoya: `GES_METRICS_TOKEN`
  berilsa `Authorization: Bearer <token>` shart; berilmasa faqat loopback (127.0.0.1/::1) dan.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_RID_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_INGEST = re.compile(r"^/api/projects/\d+/(readings|soe)$")
_HANDLER_MARK = "_sath_handler"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Bir qatorli JSON: ts, level, logger, msg, request_id, (xato bo'lsa) exc."""

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = getattr(record, "request_id", "") or request_id_var.get()
        if rid:
            out["request_id"] = rid
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def configure_logging(fmt: str = "text", level: str = "INFO") -> logging.Handler:
    """Root logger ga bitta Sath handler (qayta chaqirilsa almashtiriladi — idempotent)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_MARK, False):
            root.removeHandler(h)
    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_MARK, True)
    handler.addFilter(_RequestIdFilter())
    if fmt.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    return handler


class Metrics:
    """Jarayon ichidagi hisoblagichlar (replika boshiga — Prometheus har replikani alohida yig'adi)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests: dict[tuple[str, str], int] = defaultdict(int)
            self.duration_sum = 0.0
            self.duration_count = 0
            self.ingest: dict[str, int] = defaultdict(int)

    def observe(self, method: str, path: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, str(status))] += 1
            self.duration_sum += seconds
            self.duration_count += 1
            if method == "POST" and _INGEST.match(path):
                self.ingest["ok" if status < 400 else "rejected"] += 1


metrics = Metrics()


def _queue_depth() -> dict[tuple[str, str], int]:
    """Ish navbati chuqurligi: (jadval, holat) → soni (faqat queued/running)."""
    from sqlalchemy import func

    from .db import SessionLocal
    from .orm import Job, JobStatus, SimJob, SimStatus

    out: dict[tuple[str, str], int] = {}
    with SessionLocal() as db:
        for table, name, statuses in (
            (SimJob, "sim", (SimStatus.queued, SimStatus.running)),
            (Job, "derived", (JobStatus.queued, JobStatus.running)),
        ):
            for st in statuses:
                out[(name, st.value)] = 0
            rows = db.query(table.status, func.count()).filter(table.status.in_(statuses)).group_by(table.status)
            for st, n in rows:
                out[(name, getattr(st, "value", st))] = int(n)
    return out


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_metrics(version: str = "") -> str:
    lines = [
        "# HELP sath_build_info Sath server versiyasi",
        "# TYPE sath_build_info gauge",
        f'sath_build_info{{version="{_esc(version)}"}} 1',
        "# HELP sath_http_requests_total HTTP so'rovlar soni (method, status)",
        "# TYPE sath_http_requests_total counter",
    ]
    with metrics._lock:
        req = dict(metrics.requests)
        dsum, dcount = metrics.duration_sum, metrics.duration_count
        ingest = dict(metrics.ingest)
    for (method, status), n in sorted(req.items()):
        lines.append(f'sath_http_requests_total{{method="{_esc(method)}",status="{status}"}} {n}')
    lines += [
        "# HELP sath_http_request_duration_seconds HTTP so'rov davomiyligi",
        "# TYPE sath_http_request_duration_seconds summary",
        f"sath_http_request_duration_seconds_sum {dsum:.6f}",
        f"sath_http_request_duration_seconds_count {dcount}",
        "# HELP sath_ingest_requests_total SCADA ingest so'rovlari (POST readings/soe)",
        "# TYPE sath_ingest_requests_total counter",
    ]
    for result in ("ok", "rejected"):
        lines.append(f'sath_ingest_requests_total{{result="{result}"}} {ingest.get(result, 0)}')
    lines += [
        "# HELP sath_job_queue_depth Ish navbati chuqurligi (queued/running)",
        "# TYPE sath_job_queue_depth gauge",
    ]
    try:
        for (queue, status), n in sorted(_queue_depth().items()):
            lines.append(f'sath_job_queue_depth{{queue="{queue}",status="{status}"}} {n}')
    except Exception:  # noqa: BLE001 — DB yo'q bo'lsa metrika qolgani baribir chiqadi
        logging.getLogger("ges_server.metrics").warning("navbat chuqurligini o'qib bo'lmadi", exc_info=True)
    return "\n".join(lines) + "\n"


class RequestContextMiddleware:
    """ASGI: so'rov id (kontekst + javob sarlavhasi) va metrikalar (davomiylik, status)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = ""
        for k, v in scope.get("headers", ()):
            if k == b"x-request-id":
                cand = v.decode("latin-1")
                rid = cand if _RID_OK.match(cand) else ""
                break
        rid = rid or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message["headers"] = list(message.get("headers", ())) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            metrics.observe(scope.get("method", ""), scope.get("path", ""), status_holder["status"], time.perf_counter() - start)
            request_id_var.reset(token)
