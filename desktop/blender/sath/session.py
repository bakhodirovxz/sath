"""Server sessiyasi: GesClient + token xotirada; server/login prefs da saqlanadi."""

from __future__ import annotations

from .shared.server_client import GesClient

_client: GesClient | None = None
_user: dict | None = None


def login(server: str, username: str, password: str) -> dict:
    global _client, _user
    c = GesClient(server)
    c.login(username, password)
    _user = c.me()
    _client = c
    from .prefs import prefs

    p = prefs()
    p.server, p.username = server, username
    return _user


def logout() -> None:
    global _client, _user
    _client = None
    _user = None


def client() -> GesClient:
    if _client is None:
        raise RuntimeError("Avval serverga kiring (Sath → Server → Ulanish)")
    return _client


def user() -> dict | None:
    return _user


def is_logged_in() -> bool:
    return _client is not None
