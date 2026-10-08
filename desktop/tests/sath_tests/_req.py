"""Headless testlar uchun talablar: yo'q bo'lsa test yiqilmaydi, [SKIP] bo'ladi (K7)."""

from __future__ import annotations


class SkipTest(Exception):
    """Test sharoiti yo'q (masalan FreeCAD) — runner `[SKIP]` yozadi, exit 0."""


def require_freecad() -> None:
    from sath import fc_engine

    if not fc_engine.available():
        raise SkipTest("FreeCAD topilmadi (GES_FC_HOME) — P2 da FreeCAD siz builder lar bilan almashadi")
