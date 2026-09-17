"""Email bildirishnomalar (ixtiyoriy). GES_SMTP_URL berilmasa hech narsa yubormaydi.

Format: smtp://user:pass@host:587?from=ges@company.uz&tls=1   (smtps:// — SSL)
Yuborish alohida oqimda — API javobini kechiktirmaydi.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage
from urllib.parse import parse_qs, unquote, urlparse

from .config import get_settings

log = logging.getLogger("ges_server.notify")


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


def send_async(to: list[str], subject: str, body: str) -> None:
    """Fon oqimda yuboradi; SMTP sozlanmagan bo'lsa jim."""
    if not get_settings().smtp_url or not to:
        return
    threading.Thread(target=_send, args=(to, f"[Sath] {subject}", body), daemon=True).start()
