"""Usul amal qilish diapazonlari va tuzilgan ogohlantirishlar (`summary.warnings`).

Har modul `warnings: list[str]` yig'adi va `summary["warnings"]` ga qo'yadi; `catalog.run` ro'yxat
mavjudligini kafolatlaydi. `ok` ogohlantirishlardan mustaqil — ogohlantirish natijaning
ishonchliligi haqida, verdikt esa inshoot holati haqida.
"""

from __future__ import annotations


def check_range(
    warnings: list[str],
    label: str,
    value: float,
    lo: float | None,
    hi: float | None,
    unit: str = "",
    source: str = "",
    note: str = "natija taxminiy",
) -> bool:
    """value [lo, hi] ichida bo'lmasa ogohlantirish qo'shadi. Qaytaradi: diapazon ichidami."""
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        rng = f"{lo if lo is not None else '−∞'}–{hi if hi is not None else '∞'}"
        u = f" {unit}" if unit else ""
        src = f"; {source}" if source else ""
        warnings.append(
            f"{label} = {value:.3g}{u} usul amal doirasidan tashqarida ({rng}{u}{src}) — {note}"
        )
        return False
    return True


BUDGET_OPS = 5_000_000  # bitta hisob uchun ichki amallar (qadam × tugun) chegarasi


def check_budget(ops: float, label: str, advice: str) -> None:
    """Hisob hajmi chegaradan oshsa ValueError — server 400 qaytaradi (J12)."""
    if ops > BUDGET_OPS:
        raise ValueError(
            f"{label}: hisob hajmi {ops:.2e} amal > chegara {BUDGET_OPS:.0e} — {advice}"
        )


def nice_step(x: float, steps: tuple[float, ...] = (1.0, 0.5, 0.25, 0.1, 0.05)) -> float:
    """x dan katta bo'lmagan eng katta "chiroyli" qadam (soat)."""
    for s in steps:
        if s <= x + 1e-12:
            return s
    return steps[-1]
