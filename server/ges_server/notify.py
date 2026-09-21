"""Email bildirishnomalar (ixtiyoriy). GES_SMTP_URL berilmasa hech narsa yubormaydi.

Format: smtp://user:pass@host:587?from=ges@company.uz&tls=1   (smtps:// — SSL)

Yuborish (C5): cheklangan o'lchamli navbat + bitta ishchi oqim — har xabar uchun yangi thread emas,
navbat to'lsa xabar tashlanadi va loglanadi (`dropped`). Bir guruhdagi (`group`, masalan
`alarm:<project_id>`) navbatda turgan xabarlar bitta jamlangan emailga birlashtiriladi — alarm
toshqinida email bo'roni bo'lmaydi.
"""

from __future__ import annotations

import logging
import queue
import smtplib
import threading
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.parse import parse_qs, unquote, urlparse

from .config import get_settings

log = logging.getLogger("ges_server.notify")

QUEUE_MAX = 500  # navbat sig'imi; to'lsa yangi xabar tashlanadi
COALESCE_MAX = 50  # bitta jamlangan emailga ko'pi bilan shuncha xabar


@dataclass
class Item:
    to: list[str]
    subject: str
    body: str
    group: str | None = None
    merged: int = field(default=1)


_queue: queue.Queue[Item] | None = None
_worker: threading.Thread | None = None
_lock = threading.Lock()
dropped = 0
sent = 0


def _send(to: list[str], subject: str, body: str) -> None:
    url = get_settings().smtp_url
    if not url or not to:
        return
    u = urlparse(url)
    q = parse_qs(u.query)
    sender = q.get("from", [u.username or "sath@localhost"])[0]
    use_tls = q.get("tls", ["1"])[0] == "1"
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        cls = smtplib.SMTP_SSL if u.scheme == "smtps" else smtplib.SMTP
        with cls(
            u.hostname or "localhost", u.port or (465 if u.scheme == "smtps" else 587), timeout=20
        ) as s:
            if u.scheme != "smtps" and use_tls:
                s.starttls()
            if u.username:
                s.login(unquote(u.username), unquote(u.password or ""))
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        log.warning("email yuborilmadi (%s): %s", subject, e)


def _coalesce(first: Item, q: queue.Queue[Item]) -> tuple[Item, list[Item]]:
    """Navbatdagi shu guruh va shu qabul qiluvchilarga mo'ljallangan xabarlarni `first` ga qo'shadi.
    Boshqa xabarlar (tartibi saqlanib) qaytariladi — chaqiruvchi navbatga qaytaradi."""
    if first.group is None:
        return first, []
    same, rest = [first], []
    while len(same) < COALESCE_MAX:
        try:
            it = q.get_nowait()
        except queue.Empty:
            break
        if it.group == first.group and it.to == first.to:
            same.append(it)
        else:
            rest.append(it)
    if len(same) == 1:
        return first, rest
    lines = [f"{it.subject}\n{it.body}" for it in same]
    merged = Item(
        to=first.to,
        subject=f"{len(same)} ta xabar ({first.group.split(':')[0]}) — jamlangan",
        body="\n\n".join(lines),
        group=first.group,
        merged=len(same),
    )
    return merged, rest


def process_once(q: queue.Queue[Item], timeout: float | None = 1.0) -> int:
    """Navbatdan bitta (yoki jamlangan) xabarni oladi va yuboradi. Qaytaradi: birlashtirilgan xabarlar soni
    (0 — navbat bo'sh)."""
    global sent
    try:
        first = q.get(timeout=timeout) if timeout is not None else q.get_nowait()
    except queue.Empty:
        return 0
    item, rest = _coalesce(first, q)
    for r in rest:
        try:
            q.put_nowait(r)
        except queue.Full:
            log.warning("email navbati to'la — xabar tashlandi: %s", r.subject)
    _send(item.to, f"[Sath] {item.subject}", item.body)
    sent += 1
    return item.merged


def _worker_loop() -> None:
    assert _queue is not None
    while True:
        try:
            process_once(_queue, timeout=5.0)
        except Exception:  # noqa: BLE001 — ishchi oqim to'xtamasin; iz logda
            log.exception("email ishchi oqimi xatosi")


def _ensure_worker() -> queue.Queue[Item]:
    global _queue, _worker
    with _lock:
        if _queue is None:
            _queue = queue.Queue(maxsize=QUEUE_MAX)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="email-worker", daemon=True)
            _worker.start()
        return _queue


def send_async(to: list[str], subject: str, body: str, group: str | None = None) -> None:
    """Navbatga qo'yadi (bloklamaydi); SMTP sozlanmagan bo'lsa jim. `group` — jamlash kaliti."""
    global dropped
    if not get_settings().smtp_url or not to:
        return
    q = _ensure_worker()
    try:
        q.put_nowait(Item(list(to), subject, body, group))
    except queue.Full:
        dropped += 1
        log.warning("email navbati to'la (%d) — tashlandi: %s (jami %d)", QUEUE_MAX, subject, dropped)


def pending() -> int:
    return _queue.qsize() if _queue is not None else 0
