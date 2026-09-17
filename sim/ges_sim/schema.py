"""Simulyatsiya parametrlari sxemasi — web forma avtomatik quriladi, server validatsiya qiladi.

Har simulyatsiya moduli `FIELDS` ro'yxatini beradi: kalit, sarlavha, birlik, tur, default, chegaralar,
guruh (formada bo'lim). `parse(fields, params)` — defaultlar bilan to'ldirib, turini tekshirib qaytaradi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str = ""
    type: str = "number"  # number | int | bool | select | text | series (raqamlar ro'yxati)
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[tuple[str, str], ...] = ()  # select: (qiymat, sarlavha)
    group: str = ""  # forma bo'limi
    hint: str = ""  # qisqa izoh (formula, manba)
    live: str = ""  # raqamli egizak: qaysi jonli kattalik (upstream_level, downstream_level, inflow, penstock_flow, power)
    model: str = ""  # modeldan: Pset_GES_* maydoni (masalan "dam.height_m")
    advanced: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["options"] = [list(o) for o in self.options]
        return d


@dataclass
class Meta:
    id: str
    title: str
    description: str
    group: str  # gidrologiya | gidravlika | mustahkamlik | favqulodda | ekspluatatsiya | custom
    icon: str
    formulas: list[str] = field(default_factory=list)  # ko'rsatiladigan asosiy formulalar/manbalar
    viz: dict = field(default_factory=dict)  # 3D ko'rsatish maslahatlari (web)
    outputs: list[dict] = field(default_factory=list)  # {key, label, unit} — xulosa/seriyalar

    def to_dict(self) -> dict:
        return asdict(self)


def parse(fields: list[Field], params: dict) -> dict:
    """Defaultlar bilan to'ldiradi, turlarni tekshiradi; xato bo'lsa ValueError (foydalanuvchiga)."""
    out: dict[str, Any] = {}
    for f in fields:
        v = params.get(f.key, f.default)
        if v is None or v == "":
            if f.default is None and f.type != "bool":
                raise ValueError(f"{f.label}: qiymat kerak")
            v = f.default
        if f.type in ("number", "int"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{f.label}: son bo'lishi kerak") from None
            if f.min is not None and v < f.min:
                raise ValueError(f"{f.label}: kamida {f.min} {f.unit}".strip())
            if f.max is not None and v > f.max:
                raise ValueError(f"{f.label}: ko'pi bilan {f.max} {f.unit}".strip())
            if f.type == "int":
                v = int(round(v))
        elif f.type == "bool":
            v = bool(v)
        elif f.type == "select":
            keys = [o[0] for o in f.options]
            if str(v) not in keys:
                raise ValueError(f"{f.label}: {keys}")
            v = str(v)
        elif f.type == "series":
            if isinstance(v, str):
                v = [x for x in v.replace(";", " ").replace(",", " ").split()]
            try:
                v = [float(x) for x in v]
            except (TypeError, ValueError):
                raise ValueError(f"{f.label}: raqamlar ro'yxati") from None
        else:
            v = str(v)
        out[f.key] = v
    return out
