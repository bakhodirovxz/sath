"""SRV-02: SMTP TLS sertifikat tekshiruvi, yuborish xatosida qayta urinish, jamlashda tartib."""

import queue
import ssl
from types import SimpleNamespace

import pytest
from ges_server import notify


class FakeSMTP:
    instances: list = []
    fail = 0  # nechta ulanish xato bersin

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context, self.tls_ctx, self.msgs = host, port, context, None, []
        FakeSMTP.instances.append(self)
        if FakeSMTP.fail > 0:
            FakeSMTP.fail -= 1
            raise OSError("ulanib bo'lmadi")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls_ctx = context

    def login(self, u, p):
        pass

    def send_message(self, msg):
        self.msgs.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], 0
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def _url(monkeypatch, url):
    monkeypatch.setattr(notify, "get_settings", lambda: SimpleNamespace(smtp_url=url))


def _strict(ctx):
    return isinstance(ctx, ssl.SSLContext) and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_starttls_and_smtps_verify_certificates(monkeypatch, smtp):
    _url(monkeypatch, "smtp://u:p@mail.local:587?from=a@b.uz&tls=1")
    assert notify._send(["x@y.uz"], "s", "b") is True
    assert _strict(smtp.instances[-1].tls_ctx)
    _url(monkeypatch, "smtps://u:p@mail.local")
    assert notify._send(["x@y.uz"], "s", "b") is True
    assert smtp.instances[-1].port == 465 and _strict(smtp.instances[-1].context)


def test_send_failure_retried_with_backoff_and_counted(monkeypatch, smtp):
    _url(monkeypatch, "smtp://mail.local:25?tls=0")
    clock = [1000.0]
    monkeypatch.setattr(notify, "_now", lambda: clock[0])
    for k in ("sent", "failed", "retried"):
        monkeypatch.setattr(notify, k, 0)
    q: queue.Queue = queue.Queue()
    q.put(notify.Item(["x@y.uz"], "Alarm", "matn"))
    smtp.fail = 2
    assert notify.process_once(q, timeout=None) == 1
    assert notify.sent == 0 and notify.retried == 1  # xato — yuborilgan deb sanalmaydi
    assert notify.process_once(q, timeout=None) == 0  # hali vaqti kelmagan
    clock[0] += notify.RETRY_BASE_S
    notify.process_once(q, timeout=None)  # 2-urinish ham xato → 20 s kutish
    assert notify.sent == 0 and notify.retried == 2
    clock[0] += notify.RETRY_BASE_S  # 10 s — hali erta
    assert notify.process_once(q, timeout=None) == 0
    clock[0] += notify.RETRY_BASE_S
    assert notify.process_once(q, timeout=None) == 1
    assert notify.sent == 1 and notify.failed == 0 and len(smtp.instances[-1].msgs) == 1


def test_gives_up_after_max_attempts(monkeypatch, smtp):
    _url(monkeypatch, "smtp://mail.local:25?tls=0")
    clock = [0.0]
    monkeypatch.setattr(notify, "_now", lambda: clock[0])
    for k in ("sent", "failed", "retried"):
        monkeypatch.setattr(notify, k, 0)
    q: queue.Queue = queue.Queue()
    q.put(notify.Item(["x@y.uz"], "X", "y"))
    smtp.fail = 100
    for _ in range(notify.MAX_ATTEMPTS):
        clock[0] += notify.RETRY_MAX_S
        notify.process_once(q, timeout=None)
    assert notify.failed == 1 and notify.sent == 0 and notify.retried == notify.MAX_ATTEMPTS - 1
    clock[0] += notify.RETRY_MAX_S
    assert notify.process_once(q, timeout=None) == 0


def test_coalescing_preserves_order_of_other_groups(monkeypatch):
    got = []
    monkeypatch.setattr(notify, "_send", lambda to, subject, body: got.append(subject) or True)
    monkeypatch.setattr(notify, "COALESCE_MAX", 2)
    q: queue.Queue = queue.Queue()
    for subj, grp in (("A1", "alarm:1"), ("B", "report:1"), ("A2", "alarm:1"), ("D", "report:2")):
        q.put(notify.Item(["x@y.uz"], subj, "", grp))
    while notify.process_once(q, timeout=None):
        pass
    # A1+A2 jamlanadi; B navbat OLDIGA qaytadi — D dan oldin (eski: oxiriga → D, B)
    assert got[0].startswith("[Sath] 2 ta xabar") and got[1:] == ["[Sath] B", "[Sath] D"]
