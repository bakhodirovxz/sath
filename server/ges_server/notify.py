"""Email bildirishnomalar (ixtiyoriy). GES_SMTP_URL berilmasa hech narsa yubormaydi.

Format: smtp://user:pass@host:587?from=ges@company.uz&tls=1   (smtps:// — SSL)
        ixtiyoriy `cafile=/yo'l/ca.pem` — ichki (korporativ) CA sertifikati.
TLS (SRV-02): STARTTLS va SMTPS `ssl.create_default_context()` bilan — server sertifikati va host nomi
tekshiriladi (MITM da parol/xabar ochiq ketmaydi).

Yuborish (C5): cheklangan o'lchamli navbat + bitta ishchi oqim — har xabar uchun yangi thread emas,
navbat to'lsa xabar tashlanadi va loglanadi (`dropped`). Bir guruhdagi (`group`, masalan
`alarm:<project_id>`) navbatda turgan xabarlar bitta jamlangan emailga birlashtiriladi — alarm
toshqinida email bo'roni bo'lmaydi; jamlashda boshqa guruh xabarlari tartibi saqlanadi (navbat
oldiga qaytadi, oxiriga emas). Yuborish xatosi — eksponensial kutish bilan `MAX_ATTEMPTS` gacha qayta
urinish; `sent` faqat muvaffaqiyatli, `failed` — urinishlar tugagan xabarlar.
"""

from __future__ import annotations

import collections
import heapq
import itertools
import logging
import queue
import smtplib
import ssl
import threading
import time
import weakref
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.parse import parse_qs, unquote, urlparse

from .config import get_settings

log = logging.getLogger("ges_server.notify")

QUEUE_MAX = 500  # navbat sig'imi; to'lsa yangi xabar tashlanadi
COALESCE_MAX = 50  # bitta jamlangan emailga ko'pi bilan shuncha xabar
MAX_ATTEMPTS = 5  # bitta xabar uchun urinishlar (1 + 4 qayta)
RETRY_BASE_S = 10.0  # kutish: 10, 20, 40, 80 s … (RETRY_MAX_S dan oshmaydi)
RETRY_MAX_S = 600.0


@dataclass
class Item:
    to: list[str]
    subject: str
    body: str
    group: str | None = None
    merged: int = field(default=1)
    attempts: int = field(default=0)


_queue: queue.Queue[Item] | None = None
_worker: threading.Thread | None = None
_lock = threading.Lock()
dropped = 0
sent = 0
failed = 0
retried = 0
_now = time.monotonic  # testlarda almashtiriladi
# Navbat bo'yicha: oldingi (jamlashda ajratilgan) xabarlar va kechiktirilgan qayta urinishlar
_front: weakref.WeakKeyDictionary[queue.Queue, collections.deque[Item]] = weakref.WeakKeyDictionary()
_retry: weakref.WeakKeyDictionary[queue.Queue, list[tuple[float, int, Item]]] = weakref.WeakKeyDictionary()
_seq = itertools.count()


def tls_context(cafile: str | None = None) -> ssl.SSLContext:
    """Sertifikat va host nomini tekshiradigan kontekst (CERT_REQUIRED, check_hostname)."""
    return ssl.create_default_context(cafile=cafile)


def _send(to: list[str], subject: str, body: str) -> bool:
    """Bitta email. True — yuborildi (yoki SMTP sozlanmagan — yuboradigan narsa yo'q), False — xato."""
    url = get_settings().smtp_url
    if not url or not to:
        return True
    u = urlparse(url)
    q = parse_qs(u.query)
    sender = q.get("from", [u.username or "sath@localhost"])[0]
    use_tls = q.get("tls", ["1"])[0] == "1"
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    host = u.hostname or "localhost"
    try:
        ctx = tls_context(q.get("cafile", [None])[0])
        if u.scheme == "smtps":
            conn = smtplib.SMTP_SSL(host, u.port or 465, timeout=20, context=ctx)
        else:
            conn = smtplib.SMTP(host, u.port or 587, timeout=20)
        with conn as s:
            if u.scheme != "smtps" and use_tls:
                s.starttls(context=ctx)
            if u.username:
                s.login(unquote(u.username), unquote(u.password or ""))
            s.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException, ssl.SSLError) as e:
        log.warning("email yuborilmadi (%s): %s", subject, e)
        return False


def _take(q: queue.Queue[Item], timeout: float | None) -> Item | None:
    """Keyingi xabar: avval navbat oldiga qaytarilganlar, keyin navbat."""
    front = _front.get(q)
    if front:
        return front.popleft()
    try:
        return q.get(timeout=timeout) if timeout is not None else q.get_nowait()
    except queue.Empty:
        return None


def _coalesce(first: Item, q: queue.Queue[Item]) -> tuple[Item, list[Item]]:
    """Navbatdagi shu guruh va shu qabul qiluvchilarga mo'ljallangan xabarlarni `first` ga qo'shadi.
    Boshqa xabarlar (tartibi saqlanib) qaytariladi — chaqiruvchi ularni navbat OLDIGA qaytaradi."""
    if first.group is None or first.attempts:
        return first, []
    same, rest = [first], []
    while len(same) < COALESCE_MAX:
        it = _take(q, None)
        if it is None:
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


def _due_retry(q: queue.Queue[Item]) -> Item | None:
    h = _retry.get(q)
    if h and h[0][0] <= _now():
        return heapq.heappop(h)[2]
    return None


def process_once(q: queue.Queue[Item], timeout: float | None = 1.0) -> int:
    """Navbatdan bitta (yoki jamlangan) xabarni oladi va yuboradi; vaqti kelgan qayta urinish birinchi.
    Qaytaradi: ishlangan (jamlangan) xabarlar soni (0 — ishlanadigan xabar yo'q)."""
    global sent, failed, retried
    first = _due_retry(q)
    if first is None:
        h = _retry.get(q)
        if h and timeout is not None:  # kechiktirilgan urinish bor — navbatni uzoq kutmaymiz
            timeout = max(0.0, min(timeout, h[0][0] - _now()))
        first = _take(q, timeout)
    if first is None:
        return 0
    item, rest = _coalesce(first, q)
    if rest:
        _front.setdefault(q, collections.deque()).extendleft(reversed(rest))
    ok = _send(item.to, f"[Sath] {item.subject}", item.body)
    item.attempts += 1
    if ok is False:
        if item.attempts < MAX_ATTEMPTS:
            delay = min(RETRY_BASE_S * 2 ** (item.attempts - 1), RETRY_MAX_S)
            heapq.heappush(_retry.setdefault(q, []), (_now() + delay, next(_seq), item))
            retried += 1
            log.info("email qayta yuboriladi %.0f s dan keyin (%d/%d): %s", delay, item.attempts, MAX_ATTEMPTS, item.subject)
        else:
            failed += 1
            log.error("email %d urinishdan keyin yuborilmadi — tashlandi: %s", item.attempts, item.subject)
        return item.merged
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
    """Navbatdagi + oldiga qaytarilgan + qayta urinish kutayotgan xabarlar."""
    if _queue is None:
        return 0
    return _queue.qsize() + len(_front.get(_queue, ())) + len(_retry.get(_queue, ()))
