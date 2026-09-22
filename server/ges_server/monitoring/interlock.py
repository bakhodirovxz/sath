"""Texnologik blokirovkalar (interlock, B4): buyruq faqat shart bajarilganda bajariladi.

Shart — `ges_sim.custom` xavfsiz ifoda (AST, faqat arifmetika/taqqoslash/ruxsat etilgan funksiyalar),
o'zgaruvchilar: loyiha sensorlari (kalit identifikatorga keltiriladi: `AGG1.RUN` → `AGG1_RUN`) va
`value` — so'ralayotgan buyruq qiymati. Masalan, zatvor ochilishi: `AGG1_RUN == 0 and RES_H > 890`.

Sifat qoidasi: `bad` sifatli yoki `stale` sensor muhitga kirmaydi → ifoda NameError beradi → blokirovka
baholanmadi = TAQIQ (xavfsiz tomonga). Chetlab o'tish faqat tasdiqlovchi (approver) uchun, sabab bilan,
alohida audit yozuvi va dispetcherlarga alarm-bildirishnoma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ges_sim import custom
from sqlalchemy.orm import Session

from ..orm import Interlock, Sensor

_IDENT = re.compile(r"[^0-9A-Za-z_]")


def var_name(key: str) -> str:
    """Sensor kaliti → ifoda o'zgaruvchisi (`AGG1.P` → `AGG1_P`; raqam bilan boshlansa `_` qo'shiladi)."""
    v = _IDENT.sub("_", key)
    return v if not v[:1].isdigit() else "_" + v


def validate(condition: str) -> None:
    """Ifoda sintaksisi va ruxsat etilgan tugunlar (ValueError)."""
    custom.compile_expr(condition)


def env_for(db: Session, project_id: int, value: float | None = None) -> dict:
    """Baholash muhiti: faqat ishonchli (stale emas, bad emas, qiymati bor) sensorlar."""
    env: dict = {}
    for s in db.query(Sensor).filter_by(project_id=project_id, enabled=True).all():
        if s.last_value is None or s.stale or (s.last_quality or "good") == "bad":
            continue
        env[var_name(s.key)] = float(s.last_value)
    if value is not None:
        env["value"] = float(value)
    return env


@dataclass
class Result:
    interlock_id: int
    name: str
    ok: bool
    message: str


def evaluate(db: Session, sensor: Sensor, value: float) -> list[Result]:
    """Sensorga tegishli faol blokirovkalar; `ok=False` — buyruq taqiqlanadi (sabab `message` da)."""
    rows = (
        db.query(Interlock)
        .filter_by(sensor_id=sensor.id, enabled=True)
        .order_by(Interlock.id)
        .all()
    )
    if not rows:
        return []
    env = env_for(db, sensor.project_id, value)
    out: list[Result] = []
    for il in rows:
        try:
            ok = bool(custom.evaluate(custom.compile_expr(il.condition), env))
            msg = "" if ok else (il.message or f"shart bajarilmadi: {il.condition}")
        except NameError as e:
            ok, msg = False, f"baholab bo'lmadi — {e} (sensor ma'lumoti yo'q/yaroqsiz) → taqiq"
        except (ValueError, TypeError, ZeroDivisionError, ArithmeticError) as e:
            ok, msg = False, f"ifoda xatosi: {e} → taqiq"
        out.append(Result(il.id, il.name, ok, msg))
    return out


def blocked(results: list[Result]) -> list[Result]:
    return [r for r in results if not r.ok]
