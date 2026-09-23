"""Kod gigiyenasi: Starlette 1.x da eskirgan HTTP status nomlari ishlatilmaydi (DeprecationWarning)."""

from pathlib import Path

from starlette import status

SRC = Path(__file__).resolve().parents[1] / "ges_server"
DEPRECATED = ("HTTP_422_UNPROCESSABLE_ENTITY", "HTTP_413_REQUEST_ENTITY_TOO_LARGE")


def test_no_deprecated_status_names():
    assert status.HTTP_422_UNPROCESSABLE_CONTENT == 422 and status.HTTP_413_CONTENT_TOO_LARGE == 413
    bad = [
        f"{p.relative_to(SRC)}: {name}"
        for p in SRC.rglob("*.py")
        for name in DEPRECATED
        if name in p.read_text(encoding="utf-8")
    ]
    assert bad == [], bad
