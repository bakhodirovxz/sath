"""Server sessiyasi: GesClient + token xotirada; server/login prefs da saqlanadi.

K3: `connect_client` ishchi oqimda (bpy siz), `set_session`/`remember` asosiy oqimda. `epoch` sessiya yoki ochiq
model almashganda oshadi — fon vazifasining eskirgan natijasi yangi sahnaga yozilmaydi (core/ui_tasks.run_op).
"""

from __future__ import annotations

from .shared.server_client import GesClient

_client: GesClient | None = None
_user: dict | None = None
_epoch = 0


def epoch() -> int:
    return _epoch


def bump_epoch() -> None:
    global _epoch
    _epoch += 1


def connect_client(server: str, username: str, password: str, otp: str = "") -> tuple[GesClient, dict]:
    """Tarmoq qismi (ishchi oqim uchun xavfsiz): login + me. Global holatga tegmaydi."""
    c = GesClient(server)
    c.login(username, password, otp)
    return c, c.me()


def set_session(client: GesClient, user: dict) -> None:
    global _client, _user
    _client, _user = client, user
    bump_epoch()
    from .core import events

    events.publish("session.login", user=user)


def remember(server: str, username: str) -> None:
    """Asosiy oqim: server va login prefs ga (parol hech qachon saqlanmaydi)."""
    from .prefs import prefs

    p = prefs()
    p.server, p.username = server, username


def login(server: str, username: str, password: str, otp: str = "") -> dict:
    """Sinxron login (testlar va skriptlar uchun)."""
    c, u = connect_client(server, username, password, otp)
    set_session(c, u)
    remember(server, username)
    return u


def logout() -> None:
    global _client, _user
    _client = None
    _user = None
    bump_epoch()
    from .core import events

    events.publish("session.logout")


def client() -> GesClient:
    if _client is None:
        raise RuntimeError("Avval serverga kiring (Sath → Server → Ulanish)")
    return _client


def user() -> dict | None:
    return _user


def is_logged_in() -> bool:
    return _client is not None
