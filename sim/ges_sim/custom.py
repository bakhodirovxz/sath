"""Maxsus (foydalanuvchi) simulyatsiya: formulalar shablon sifatida — xavfsiz ifoda hisoblagich.

Shablon (JSON):
  inputs:  [{key, label, unit, default, min, max}]         — forma maydonlari
  steps:   qadamlar soni,  dt: qadam (istalgan birlik, masalan soat)
  init:    {o'zgaruvchi: ifoda}                            — boshlang'ich holat (kirishlar bo'yicha)
  step:    [{target, expr}]                                — har qadamda tartib bilan hisoblanadi (t, dt, i mavjud)
  outputs: [o'zgaruvchilar]                                — vaqt qatori sifatida yoziladi
  summary: {nom: ifoda}                                    — series.<nom> ro'yxatlar ustida (max, min, mean, sum, last)
  checks:  [{expr, message}]                               — expr rost bo'lsa ogohlantirish (verdict ga)
Ifodalar Python sintaksisida, faqat arifmetika, taqqoslash, shart (a if c else b) va ruxsat etilgan
funksiyalar: abs min max sqrt exp log log10 sin cos tan atan atan2 pow floor ceil round clip interp mean sum len last.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

MAX_STEPS = 200_000
MAX_EXPR = 4000

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for a, b, ya, yb in zip(xs, xs[1:], ys, ys[1:], strict=False):
        if a <= x <= b:
            return ya + (yb - ya) * (x - a) / (b - a) if b > a else ya
    return ys[-1]


FUNCS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "sqrt": lambda v: math.sqrt(v) if v > 0 else 0.0,
    "exp": math.exp,
    "log": lambda v: math.log(v) if v > 0 else float("-inf"),
    "log10": lambda v: math.log10(v) if v > 0 else float("-inf"),
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "atan": math.atan,
    "atan2": math.atan2,
    "pow": pow,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "clip": lambda v, lo, hi: max(lo, min(hi, v)),
    "interp": _interp,
    "mean": lambda xs: sum(xs) / len(xs) if xs else 0.0,
    "sum": sum,
    "len": len,
    "last": lambda xs: xs[-1] if xs else 0.0,
}
CONSTS = {"pi": math.pi, "e": math.e, "g": 9.80665, "rho": 998.2, "True": True, "False": False}


class _Series:
    """summary ifodalarida `series.V` ko'rinishi uchun."""

    def __init__(self, d: dict[str, list]):
        self._d = d

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise NameError(f"series.{k} yo'q") from None


def compile_expr(src: str) -> ast.Expression:
    if len(src) > MAX_EXPR:
        raise ValueError("Ifoda juda uzun")
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Ifoda xatosi: {src!r}: {e.msg}") from None
    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Expression,
                ast.BinOp,
                ast.UnaryOp,
                ast.BoolOp,
                ast.Compare,
                ast.IfExp,
                ast.Name,
                ast.Load,
                ast.List,
                ast.Tuple,
                ast.Subscript,
                ast.Index,
                ast.Slice,
            ),
        ):  # noqa: UP038
            continue
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, bool)):
                raise ValueError("Faqat sonlar ruxsat etiladi")
            continue
        if isinstance(node, (ast.operator, ast.unaryop, ast.cmpop, ast.boolop)):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise ValueError(f"Ruxsat etilmagan funksiya: {ast.unparse(node.func)}")
            continue
        if isinstance(node, ast.Attribute):
            if not (isinstance(node.value, ast.Name) and node.value.id == "series"):
                raise ValueError("Faqat series.<nom> atributi ruxsat etiladi")
            continue
        raise ValueError(f"Ruxsat etilmagan ifoda: {type(node).__name__}")
    return tree


def evaluate(tree: ast.Expression, env: dict[str, Any]) -> Any:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            if n.id in CONSTS:
                return CONSTS[n.id]
            raise NameError(f"Noma'lum o'zgaruvchi: {n.id}")
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            op = _BIN[type(n.op)]
            if isinstance(n.op, ast.Pow) and isinstance(b, (int, float)) and abs(b) > 1000:
                raise ValueError("Daraja juda katta")
            try:
                return op(a, b)
            except ZeroDivisionError:
                return float("inf") if a >= 0 else float("-inf")
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return (
                -v
                if isinstance(n.op, ast.USub)
                else (+v if isinstance(n.op, ast.UAdd) else (not v))
            )
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators, strict=False):
                right = ev(comp)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Call):
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, (ast.List, ast.Tuple)):
            return [ev(e) for e in n.elts]
        if isinstance(n, ast.Subscript):
            base = ev(n.value)
            sl = n.slice
            if isinstance(sl, ast.Slice):
                return base[
                    (ev(sl.lower) if sl.lower else None) : (ev(sl.upper) if sl.upper else None)
                ]
            return base[int(ev(sl))]
        if isinstance(n, ast.Attribute):
            return getattr(ev(n.value), n.attr)
        raise ValueError(type(n).__name__)

    return ev(tree)


def validate_template(t: dict) -> None:
    if not isinstance(t, dict):
        raise ValueError("Shablon JSON obyekt bo'lishi kerak")
    steps = int(t.get("steps", 100))
    if not 1 <= steps <= MAX_STEPS:
        raise ValueError(f"steps: 1…{MAX_STEPS}")
    for inp in t.get("inputs", []):
        if not isinstance(inp, dict) or not str(inp.get("key", "")).isidentifier():
            raise ValueError("inputs: har birida key (identifikator) bo'lishi kerak")
    for k, v in (t.get("init") or {}).items():
        if not str(k).isidentifier():
            raise ValueError(f"init: {k} identifikator emas")
        compile_expr(str(v))
    for s in t.get("step") or []:
        if not str(s.get("target", "")).isidentifier():
            raise ValueError("step: target identifikator bo'lishi kerak")
        compile_expr(str(s.get("expr", "")))
    for v in (t.get("summary") or {}).values():
        compile_expr(str(v))
    for c in t.get("checks") or []:
        compile_expr(str(c.get("expr", "")))


def run(template: dict, params: dict) -> dict:
    validate_template(template)
    env: dict[str, Any] = {}
    for inp in template.get("inputs", []):
        k = inp["key"]
        v = params.get(k, inp.get("default", 0))
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{inp.get('label', k)}: son kerak") from None
        if inp.get("min") is not None and v < float(inp["min"]):
            raise ValueError(f"{inp.get('label', k)}: kamida {inp['min']}")
        if inp.get("max") is not None and v > float(inp["max"]):
            raise ValueError(f"{inp.get('label', k)}: ko'pi bilan {inp['max']}")
        env[k] = v
    dt = float(template.get("dt", 1.0))
    steps = int(template.get("steps", 100))
    env["dt"] = dt
    env["t"] = 0.0
    env["i"] = 0
    for k, v in (template.get("init") or {}).items():
        env[k] = evaluate(compile_expr(str(v)), env)
    step_code = [(s["target"], compile_expr(str(s["expr"]))) for s in template.get("step") or []]
    outputs = [o for o in template.get("outputs") or [] if str(o).isidentifier()]
    series: dict[str, list] = {"t": []}
    for o in outputs:
        series[o] = []
    for i in range(steps):
        env["i"] = i
        env["t"] = i * dt
        for target, code in step_code:
            env[target] = evaluate(code, env)
        series["t"].append(round(env["t"], 6))
        for o in outputs:
            v = env.get(o, 0.0)
            series[o].append(round(float(v), 6) if isinstance(v, (int, float)) else v)
    senv = dict(env)
    senv["series"] = _Series(series)
    summary: dict[str, Any] = {}
    for k, v in (template.get("summary") or {}).items():
        val = evaluate(compile_expr(str(v)), senv)
        summary[k] = round(float(val), 6) if isinstance(val, (int, float)) else val
    senv.update(summary)
    warns = []
    for c in template.get("checks") or []:
        if evaluate(compile_expr(str(c.get("expr", "False"))), senv):
            warns.append(str(c.get("message", "shart bajarildi")))
    summary["verdict"] = "; ".join(warns) if warns else "Ogohlantirishlar yo'q"
    summary["ok"] = not warns
    return {"series": series, "summary": summary}


def example_template() -> dict:
    """Namuna: oddiy suv ombori balansi — sath, tashlama, quvvat, ogohlantirish."""
    return {
        "name": "Oddiy ombor balansi",
        "description": "dV/dt = Q_in − Q_turb − tashlama; sath = V/A. Tashlama — sath maksimaldan oshsa.",
        "inputs": [
            {"key": "Q_in", "label": "Kiruvchi sarf", "unit": "m³/s", "default": 120, "min": 0},
            {"key": "Q_turb", "label": "Turbina sarfi", "unit": "m³/s", "default": 100, "min": 0},
            {"key": "A", "label": "Ombor yuzasi", "unit": "km²", "default": 20, "min": 0.01},
            {"key": "H0", "label": "Boshlang'ich sath", "unit": "m", "default": 900},
            {"key": "Hmax", "label": "Maksimal sath (tashlama)", "unit": "m", "default": 905},
            {"key": "Htail", "label": "Quyi byef sathi", "unit": "m", "default": 840},
        ],
        "steps": 365,
        "dt": 24,
        "init": {"H": "H0", "spill": "0"},
        "step": [
            {"target": "spill", "expr": "max((H - Hmax) * A * 1e6 / (dt * 3600), 0)"},
            {"target": "H", "expr": "H + (Q_in - Q_turb - spill) * dt * 3600 / (A * 1e6)"},
            {"target": "P", "expr": "0.9 * rho * g * Q_turb * (H - Htail) / 1e6"},
        ],
        "outputs": ["H", "spill", "P"],
        "summary": {
            "H_max": "max(series.H)",
            "H_min": "min(series.H)",
            "E_MWh": "sum(series.P) * dt",
            "spill_mcm": "sum(series.spill) * dt * 3600 / 1e6",
        },
        "checks": [{"expr": "H_min < 880", "message": "Sath o'lik hajmdan pastga tushdi"}],
    }
