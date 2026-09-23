"""Model validatsiya yozuvlari (I3) — egizak natijasiga tayanish uchun rasmiy asos.

Kalibrovka (I1) modelni ma'lumotga moslashtiradi, lekin «model ishonchli» degani emas: gidrotexnik
xavfsizlik muhandisi uchun **kim**, **qaysi davr ma'lumotida**, **qanday qabul mezoni bilan** va
**qachongacha** amal qiladigan qarorni qabul qilgani yozilishi kerak (ISO/IEC 15288 V&V amaliyoti,
ASME V&V 10/20 ruhida; ICOLD B158 «hujjatlangan tekshiruv» talabi).

Yozuv (`ValidationRecord`): model versiyasi, kalibrovka yozuvi, davr, mezonlar va o'lchangan
ko'rsatkichlar (RMSE, bias, nuqta soni), verdikt (`pass`/`fail`), imzolagan foydalanuvchi va amal
qilish muddati. Muddati o'tgan yoki yo'q bo'lgan yozuv — egizak natijasida ochiq belgilanadi:

    validated      — amaldagi tasdiqlangan yozuv bor
    expired        — yozuv bor, muddati o'tgan
    failed         — oxirgi yozuv «mos emas» deb yopilgan
    unvalidated    — hech qanday yozuv yo'q

Standart qabul mezonlari (`DEFAULT_CRITERIA`) — quvvat qoldig'i bo'yicha: RMSE ≤ nominal quvvatning
2 % i va |bias| ≤ 1 % i, kamida 72 ta ishlagan soat. Ular loyihaga qarab o'zgartirilishi mumkin va
yozuvda saqlanadi (keyin mezon o'zgarsa eski yozuv o'z mezoni bilan qoladi).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..orm import CalibrationRun, Project, ValidationRecord
from . import calibration, twin

DEFAULT_CRITERIA = {
    "rmse_pct_of_rated": 2.0,  # RMSE ≤ 2 % nominal quvvat
    "bias_pct_of_rated": 1.0,  # |bias| ≤ 1 %
    "min_points": 72,  # kamida 72 ta ishlagan soat (3 sutka)
    "valid_days": 180,  # amal qilish muddati (yarim yil)
}
STATUSES = ("validated", "expired", "failed", "unvalidated")


def _aware(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=timezone.utc))


def rated_mw(db: Session, project: Project, indices: set[int] | None = None) -> float | None:
    """Mezon asosi — **o'lchanayotgan** agregatlarning nominal quvvati yig'indisi. Modelda uch agregat
    bo'lib, faqat bittasi o'lchanayotgan bo'lsa, uch agregat nominaliga nisbatan olingan 2 % mezon
    juda yumshoq bo'lib qolardi."""
    params = twin.model_params(db, project.id)
    if not params:
        return None
    units = params.get("units") or []
    if indices:
        chosen = [units[min(i - 1, len(units) - 1)] for i in sorted(indices)]
    else:
        chosen = units
    total = sum(float(u.get("rated_power_mw") or 0) for u in chosen)
    return total or None


def evaluate(db: Session, project: Project, days: int = 30, criteria: dict | None = None) -> dict:
    """Joriy model (kalibrovka qo'llangan bo'lsa u bilan) qabul mezonlariga mos keladimi.
    Hech narsa yozmaydi — natija `check(db, project)` va `create(...)` uchun."""
    crit = {**DEFAULT_CRITERIA, **(criteria or {})}
    rows = calibration.samples(db, project, days)
    indices = {i for r in rows for i in r["powers"]}
    rated = rated_mw(db, project, indices)
    res = calibration.residuals(db, project, days=days)
    if rated is None:
        return {"ok": False, "reason": "model parametrlari yo'q", "criteria": crit, "metrics": {}}
    if res.get("status") == "insufficient":
        return {
            "ok": False,
            "reason": f"ma'lumot yetarli emas ({res.get('n_points', 0)} nuqta)",
            "criteria": crit,
            "metrics": {"n_points": res.get("n_points", 0)},
        }
    rmse_pct = res["rmse_mw"] / rated * 100
    bias_pct = abs(res["bias_mw"]) / rated * 100
    checks = [
        {
            "name": "rmse",
            "label": f"RMSE ≤ {crit['rmse_pct_of_rated']} % nominal",
            "value": round(rmse_pct, 3),
            "limit": crit["rmse_pct_of_rated"],
            "ok": rmse_pct <= crit["rmse_pct_of_rated"],
        },
        {
            "name": "bias",
            "label": f"|siljish| ≤ {crit['bias_pct_of_rated']} % nominal",
            "value": round(bias_pct, 3),
            "limit": crit["bias_pct_of_rated"],
            "ok": bias_pct <= crit["bias_pct_of_rated"],
        },
        {
            "name": "points",
            "label": f"kamida {crit['min_points']} nuqta",
            "value": res["n_points"],
            "limit": crit["min_points"],
            "ok": res["n_points"] >= crit["min_points"],
        },
    ]
    return {
        "ok": all(c["ok"] for c in checks),
        "criteria": crit,
        "checks": checks,
        "metrics": {
            "rated_mw": rated,
            "rmse_mw": res["rmse_mw"],
            "bias_mw": res["bias_mw"],
            "rmse_pct": round(rmse_pct, 3),
            "bias_pct": round(bias_pct, 3),
            "n_points": res["n_points"],
            "days": days,
            "calibrated": res.get("calibrated", False),
        },
        "reason": "" if all(c["ok"] for c in checks) else "qabul mezonlari bajarilmadi",
    }


def create(
    db: Session,
    project: Project,
    user_id: int,
    days: int = 30,
    criteria: dict | None = None,
    note: str = "",
) -> ValidationRecord:
    """Validatsiya yozuvini yaratadi (imzo — chaqirgan foydalanuvchi). Commit chaqiruvchida."""
    ev = evaluate(db, project, days=days, criteria=criteria)
    crit = ev["criteria"]
    now = datetime.now(timezone.utc)
    params = twin.model_params(db, project.id)
    cal = calibration.current(project)
    run_id = cal.get("run_id")
    rec = ValidationRecord(
        project_id=project.id,
        version_id=(params or {}).get("version_id"),
        calibration_run_id=run_id if run_id and db.get(CalibrationRun, run_id) else None,
        validated_by=user_id,
        created_at=now,
        window_from=now - timedelta(days=days),
        window_to=now,
        criteria=crit,
        metrics=ev["metrics"],
        checks=ev.get("checks", []),
        verdict="pass" if ev["ok"] else "fail",
        valid_until=now + timedelta(days=int(crit["valid_days"])) if ev["ok"] else None,
        note=note or ev.get("reason", ""),
    )
    db.add(rec)
    db.flush()
    return rec


def latest(db: Session, project: Project) -> ValidationRecord | None:
    return (
        db.query(ValidationRecord)
        .filter_by(project_id=project.id)
        .order_by(ValidationRecord.id.desc())
        .first()
    )


def status(db: Session, project: Project, now: datetime | None = None) -> dict:
    """Egizak natijasiga qo'shiladigan validatsiya holati."""
    now = now or datetime.now(timezone.utc)
    rec = latest(db, project)
    if rec is None:
        return {
            "status": "unvalidated",
            "note": "Model validatsiya qilinmagan — natija muhandislik qarori uchun asos emas",
        }
    until = _aware(rec.valid_until)
    if rec.verdict != "pass":
        st = "failed"
        note = f"Oxirgi validatsiya mos emas: {rec.note or 'qabul mezonlari bajarilmadi'}"
    elif until is not None and until < now:
        st = "expired"
        note = f"Validatsiya muddati {until.date()} da tugagan — qayta tekshirish kerak"
    else:
        st = "validated"
        note = ""
    params = twin.model_params(db, project.id)
    version_id = (params or {}).get("version_id")
    if st == "validated" and rec.version_id and version_id and rec.version_id != version_id:
        st, note = (
            "expired",
            f"Model versiyasi o'zgargan (v{rec.version_id} → v{version_id}) — qayta validatsiya kerak",
        )
    return {
        "status": st,
        "note": note,
        "record_id": rec.id,
        "verdict": rec.verdict,
        "validated_at": _aware(rec.created_at).isoformat(),
        "validated_by": rec.author.username if rec.author else None,
        "valid_until": until.isoformat() if until else None,
        "version_id": rec.version_id,
        "metrics": rec.metrics or {},
    }


def tick_expiry(db: Session) -> int:
    """Fon (soatlik): muddati o'tgan validatsiya uchun bir marta ogohlantirish."""
    from .. import notifications
    from ..orm import Role

    n = 0
    now = datetime.now(timezone.utc)
    for project in db.query(Project).all():
        rec = latest(db, project)
        if rec is None or rec.verdict != "pass" or rec.expiry_notified:
            continue
        until = _aware(rec.valid_until)
        if until is None or until > now:
            continue
        rec.expiry_notified = True
        notifications.push(
            db,
            notifications.member_ids(db, project.id, Role.engineer, at_least=True),
            "twin",
            f"Egizak validatsiyasi muddati tugadi: {project.name}",
            f"{until.date()} — natijalar «validatsiyalanmagan» deb belgilanadi, qayta tekshiring",
            f"/projects/{project.id}/dashboard",
        )
        n += 1
    if n:
        db.commit()
    return n
