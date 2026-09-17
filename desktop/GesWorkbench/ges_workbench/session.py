"""Server manzili, foydalanuvchi va token. Manzil/login FreeCAD parametrlarida saqlanadi, token faqat xotirada."""

from __future__ import annotations

from .server_client import GesClient

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Sath"

_client: GesClient | None = None
_user: dict | None = None


def _params():
    import FreeCAD

    return FreeCAD.ParamGet(PARAM_PATH)


def saved_server() -> str:
    return _params().GetString("server", "http://localhost:8000")


def saved_username() -> str:
    return _params().GetString("username", "")


def login(server: str, username: str, password: str) -> dict:
    global _client, _user
    c = GesClient(server)
    c.login(username, password)
    _user = c.me()
    _client = c
    p = _params()
    p.SetString("server", server)
    p.SetString("username", username)
    return _user


def logout() -> None:
    global _client, _user
    _client = None
    _user = None


def client() -> GesClient:
    if _client is None:
        raise RuntimeError("Avval serverga kiring (GES → Ulanish)")
    return _client


def user() -> dict | None:
    return _user


def is_logged_in() -> bool:
    return _client is not None
