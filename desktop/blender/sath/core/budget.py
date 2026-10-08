"""Spec §5 unumdorlik byudjetlari — yagona joy: addon register logi (sath/__init__.py), headless `budgets`
sinovi, desktop/tests/perf_baseline.py --check. bpy siz (pytest)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

REGISTER_MS = 150.0  # Sath import + register jami (modullar bilan)
COLD_START_RATIO = 1.2  # sovuq start: Blender+Bonsai+Sath / Blender+Bonsai
IDLE_RSS_DELTA_MB = 50.0  # bo'sh sahnada Sath RSS ortishi (Bonsai ustiga)
HEAVY_MODULES = ("numpy", "ifcopenshell", "ezdxf", "assimp_py")  # faqat funksiya ichida import qilinadi


def heavy_loaded(names: Iterable[str]) -> list[str]:
    """Yangi yuklangan modul nomlaridan og'irlari (yuqori paket nomi bo'yicha)."""
    return sorted({n.split(".", 1)[0] for n in names} & set(HEAVY_MODULES))


def register_line(import_ms: float, core: Mapping[str, float], modules: Mapping[str, float]) -> str:
    """Bitta log qatori (ASCII): jami, har yadro qismi, modullar (Record.ms: import + register)."""
    total = import_ms + sum(core.values())
    head = f"[sath] register {total:.1f} ms (byudjet < {REGISTER_MS:.0f})"
    if total >= REGISTER_MS:
        head += " - BYUDJET OSHDI"
    parts = [f"import {import_ms:.1f}", *(f"{k} {v:.1f}" for k, v in core.items())]
    line = head + ": " + ", ".join(parts)
    if modules:
        line += " [modullar: " + ", ".join(f"{k} {v:.1f}" for k, v in modules.items()) + "]"
    return line


def check(*, register_ms: float | None, cold_ratio: float | None, rss_delta_mb: float | None,
          heavy: Iterable[str]) -> list[str]:  # fmt: skip
    """O'lchovlar → buzilgan byudjetlar (bo'sh — hammasi bajarildi). None — o'lchanmagan (buzilgan)."""
    bad = []
    if register_ms is None or register_ms >= REGISTER_MS:
        bad.append(f"Sath register {register_ms} ms (byudjet < {REGISTER_MS:.0f})")
    if cold_ratio is None or cold_ratio > COLD_START_RATIO:
        bad.append(f"sovuq start nisbati {cold_ratio} (byudjet <= {COLD_START_RATIO})")
    if rss_delta_mb is None or rss_delta_mb > IDLE_RSS_DELTA_MB:
        bad.append(f"RSS ortishi {rss_delta_mb} MB (byudjet <= {IDLE_RSS_DELTA_MB:.0f})")
    heavy = list(heavy)
    if heavy:
        bad.append(f"register da og'ir importlar: {', '.join(heavy)}")
    return bad
