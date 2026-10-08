"""Headless testlar uchun talablar: sharoit yo'q bo'lsa test yiqilmaydi, [SKIP] bo'ladi (K7). CI da SKIP taqiqlangan
(SATH_REQUIRE_NO_SKIP=1) — SkipTest faqat haqiqatan ixtiyoriy tashqi sharoit uchun."""

from __future__ import annotations


class SkipTest(Exception):
    """Test sharoiti yo'q — runner `[SKIP]` yozadi, exit 0."""
