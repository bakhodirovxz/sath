"""CMMS chuqurligi (H2): profilaktik xizmat rejalari (vaqt yoki ish soati bo'yicha) → avtomatik ish
buyrug'i, ISO 14224 nosozlik kodlari, mehnat yozuvi, ehtiyot qism bandlash/sarflash, ruxsatnoma (PTW)
va LOTO (boshqaruv blokirovkasi bilan), aktiv bo'yicha xizmat tarixi va xarajat.

Manbalar: ISO 14224:2016 (ishonchlilik ma'lumotlari — nosozlik rejimi/sabab/aniqlash usuli tasnifi,
Annex B), ISO 55001 (aktivlarni boshqarish), LOTO (energiya izolyatsiyasi) — IEC 60204-1 §5.3.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..orm import (
    Asset,
    LaborEntry,
    MaintenancePlan,
    PartMovement,
    PartReservation,
    Project,
    Sensor,
    SparePart,
    WorkOrder,
    WorkOrderStatus,
)
from . import twin

# ISO 14224:2016 Annex B — nosozlik rejimlari (GES uskunalari uchun tegishli to'plam)
FAILURE_MODES = {
    "FTS": "Ishga tushmadi (fail to start on demand)",
    "STP": "Kutilmagan to'xtash (spurious stop)",
    "BRD": "Buzilish (breakdown)",
    "HIO": "Yuqori chiqish (high output)",
    "LOO": "Past chiqish (low output)",
    "ERO": "Nobarqaror chiqish (erratic output)",
    "ELP": "Tashqi oqish — suv/moy (external leakage)",
    "INL": "Ichki oqish (internal leakage)",
    "VIB": "Tebranish (vibration)",
    "NOI": "Shovqin (noise)",
    "OHE": "Qizish (overheating)",
    "PDE": "Parametr og'ishi (parameter deviation)",
    "AIR": "Yaroqsiz ko'rsatkich (abnormal instrument reading)",
    "STD": "Tuzilma nuqsoni (structural deficiency)",
    "SER": "Kichik nosozlik (minor in-service problems)",
    "PLU": "Tiqilish (plugged/choked)",
    "OTH": "Boshqa",
    "UNK": "Noma'lum",
}
# ISO 14224 Table B.3 — nosozlik sabablari (yuqori daraja)
FAILURE_CAUSES = {
    "design": "Loyiha — noto'g'ri quvvat, material, o'rnatish yechimi",
    "fabrication": "Ishlab chiqarish / montaj nuqsoni",
    "operation": "Ekspluatatsiya — noto'g'ri ishlatish, protseduraga rioya qilmaslik",
    "maintenance": "Texnik xizmat — kechikish, noto'g'ri yig'ish",
    "wear": "Kutilgan eskirish / yemirilish",
    "external": "Tashqi ta'sir — toshqin, muz, chaqmoq, begona jism",
    "unknown": "Noma'lum",
}
# ISO 14224 Table B.4 — aniqlash usuli
DETECTION_METHODS = {
    "periodic": "Rejali texnik xizmat / ko'rik",
    "condition": "Holat monitoringi (tebranish, harorat, sog'liq indeksi)",
    "functional": "Funksional sinov",
    "production": "Ishlab chiqarish uzilishi",
    "casual": "Tasodifiy kuzatuv",
    "corrective": "Buzilish sodir bo'lgach (corrective)",
    "alarm": "Alarm / himoya ishlashi",
    "other": "Boshqa",
}
PERMIT_STATES = ("none", "requested", "issued", "closed")
OPEN_STATES = (WorkOrderStatus.open, WorkOrderStatus.in_progress)


def _aware(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=timezone.utc))


def check_codes(mode: str | None, cause: str | None, detection: str | None) -> None:
    """ISO 14224 kodlari ro'yxatdan bo'lishi kerak (bo'sh — belgilanmagan)."""
    for val, table, label in (
        (mode, FAILURE_MODES, "Nosozlik rejimi"),
        (cause, FAILURE_CAUSES, "Nosozlik sababi"),
        (detection, DETECTION_METHODS, "Aniqlash usuli"),
    ):
        if val and val not in table:
            raise ValueError(f"{label} (ISO 14224): {', '.join(table)}")


# --------------------------------------------------------------------------- profilaktik rejalar


def run_hours_map(db: Session, project: Project) -> dict[int, float]:
    """Aktiv → jami ish soati (quvvat sensori kunlik statistikasidan, `twin.asset_status`)."""
    return {a["id"]: float(a.get("run_hours_total") or 0.0) for a in twin.asset_status(db, project)}


def plan_due(plan: MaintenancePlan, run_hours: dict[int, float], now: datetime) -> str | None:
    """Reja muddati kelgan bo'lsa sababi, aks holda None. Vaqt (`interval_days`) — oxirgi buyruqdan
    (yoki reja tuzilganidan) beri; ish soati (`interval_hours`) — aktiv hisoblagichi oxirgi buyruqdagi
    qiymatdan qancha oshgani bo'yicha."""
    if not plan.active:
        return None
    last = _aware(plan.last_generated_at) or _aware(plan.created_at) or now
    if plan.interval_days:
        if now >= last + timedelta(days=plan.interval_days):
            return f"vaqt bo'yicha: oxirgi buyruqdan {(now - last).days} kun ({plan.interval_days} kun davriylik)"
    if plan.interval_hours and plan.asset_id is not None:
        hours = run_hours.get(plan.asset_id)
        if hours is not None:
            delta = hours - (plan.last_run_hours or 0.0)
            if delta >= plan.interval_hours:
                return f"ish soati bo'yicha: {delta:.0f} soat ({plan.interval_hours:.0f} soat davriylik)"
    return None


def generate_work_orders(
    db: Session, project: Project, now: datetime | None = None
) -> list[WorkOrder]:
    """Muddati kelgan rejalar uchun ish buyrug'i yaratadi. Shu reja bo'yicha ochiq (open/in_progress)
    buyruq bo'lsa yangisi yaratilmaydi — takror buyruqlar to'planib ketmasin. Commit chaqiruvchida."""
    now = now or datetime.now(timezone.utc)
    plans = db.query(MaintenancePlan).filter_by(project_id=project.id, active=True).all()
    if not plans:
        return []
    need_hours = any(p.interval_hours and p.asset_id for p in plans)
    run_hours = run_hours_map(db, project) if need_hours else {}
    created: list[WorkOrder] = []
    for plan in plans:
        why = plan_due(plan, run_hours, now)
        if why is None:
            continue
        open_wo = (
            db.query(WorkOrder)
            .filter(WorkOrder.plan_id == plan.id, WorkOrder.status.in_(OPEN_STATES))
            .first()
        )
        if open_wo is not None:
            continue
        wo = WorkOrder(
            project_id=project.id,
            asset_id=plan.asset_id,
            plan_id=plan.id,
            created_by=plan.created_by,
            title=f"[Reja] {plan.name}",
            description="\n".join(x for x in [plan.description, f"Sabab: {why}"] if x),
            priority=plan.priority or "medium",
            source="plan",
            tasks=[{"title": t, "done": False} for t in (plan.tasks or [])],
            due_at=now + timedelta(days=plan.lead_days or 7),
            permit_required=bool(plan.permit_required),
        )
        db.add(wo)
        plan.last_generated_at = now
        if plan.asset_id in run_hours:
            plan.last_run_hours = run_hours[plan.asset_id]
        created.append(wo)
    db.flush()
    return created


def tick_plans(db: Session) -> list[tuple[WorkOrder, Project]]:
    """Fon vazifasi (soatlik): barcha loyihalar bo'yicha rejalarni tekshiradi."""
    out: list[tuple[WorkOrder, Project]] = []
    for project in db.query(Project).all():
        out += [(w, project) for w in generate_work_orders(db, project)]
    return out


# --------------------------------------------------------------------------- mehnat va xarajat


def labor_hours(db: Session, wo: WorkOrder) -> float:
    return round(sum(e.hours for e in db.query(LaborEntry).filter_by(work_order_id=wo.id).all()), 2)


def consumed_movements(db: Session, wo: WorkOrder) -> list[PartMovement]:
    return (
        db.query(PartMovement)
        .filter(PartMovement.work_order_id == wo.id, PartMovement.qty < 0)
        .order_by(PartMovement.id)
        .all()
    )


def _price(m: PartMovement) -> float:
    if m.unit_cost is not None:
        return m.unit_cost
    return (m.part.unit_cost if m.part else 0.0) or 0.0


def recompute_cost(db: Session, wo: WorkOrder) -> float:
    """Xarajat = mehnat (soat × stavka; yozuvda stavka yo'q bo'lsa buyruq stavkasi) + sarflangan qismlar
    (miqdor × sarf paytidagi narx) + qo'shimcha (pudrat, transport)."""
    labor = sum(
        e.hours * (e.rate if e.rate is not None else (wo.labor_rate or 0.0))
        for e in db.query(LaborEntry).filter_by(work_order_id=wo.id).all()
    )
    parts = sum(-m.qty * _price(m) for m in consumed_movements(db, wo))
    wo.labor_cost = round(labor, 2)
    wo.parts_cost = round(parts, 2)
    wo.cost = round(labor + parts + (wo.extra_cost or 0.0), 2)
    return wo.cost


# --------------------------------------------------------------------------- ehtiyot qism bandlash


def reserved_qty(db: Session, part: SparePart) -> float:
    """Shu qism bo'yicha ochiq ish buyruqlarida band miqdor."""
    rows = (
        db.query(PartReservation)
        .join(WorkOrder, PartReservation.work_order_id == WorkOrder.id)
        .filter(PartReservation.part_id == part.id, WorkOrder.status.in_(OPEN_STATES))
        .all()
    )
    return round(sum(r.qty for r in rows), 3)


def free_qty(db: Session, part: SparePart) -> float:
    """Bo'sh qoldiq = ombor qoldig'i − ochiq buyruqlarda band miqdor."""
    return round(part.qty - reserved_qty(db, part), 3)


def reserve(db: Session, wo: WorkOrder, part: SparePart, qty: float) -> PartReservation:
    """Bandlash: ombor qoldig'i kamaymaydi, bo'sh qoldiq kamayadi. `qty=0` — bandlikni bekor qilish.
    Commit chaqiruvchida."""
    if part.project_id != wo.project_id:
        raise ValueError("Ehtiyot qism boshqa loyihaniki")
    if qty < 0:
        raise ValueError("Miqdor manfiy bo'lmasin")
    if wo.status not in OPEN_STATES:
        raise ValueError("Yopilgan ish buyrug'iga bandlash mumkin emas")
    row = db.query(PartReservation).filter_by(work_order_id=wo.id, part_id=part.id).first()
    already = row.qty if row else 0.0
    free = free_qty(db, part)
    if qty - already > free + 1e-9:
        raise ValueError(f"Bo'sh qoldiq yetarli emas: {free:g} {part.unit}")
    if row is None:
        row = PartReservation(work_order_id=wo.id, part_id=part.id, qty=qty)
        db.add(row)
    else:
        row.qty = qty
    db.flush()
    return row


def consume(
    db: Session, wo: WorkOrder, part: SparePart, qty: float, user_id: int, note: str = ""
) -> PartMovement:
    """Sarflash: ombordan chiqim (−); avval shu buyruqdagi bandlikdan yechiladi. Commit chaqiruvchida."""
    if part.project_id != wo.project_id:
        raise ValueError("Ehtiyot qism boshqa loyihaniki")
    if qty <= 0:
        raise ValueError("Miqdor musbat bo'lishi kerak")
    if qty > part.qty + 1e-9:
        raise ValueError(f"Omborda yetarli emas: {part.qty:g} {part.unit}")
    row = db.query(PartReservation).filter_by(work_order_id=wo.id, part_id=part.id).first()
    if row is not None:
        row.qty = max(0.0, round(row.qty - qty, 6))
    part.qty = round(part.qty - qty, 6)
    mv = PartMovement(
        part_id=part.id,
        work_order_id=wo.id,
        user_id=user_id,
        qty=-qty,
        note=note[:200],
        kind="consume",
        unit_cost=part.unit_cost,
    )
    db.add(mv)
    db.flush()
    recompute_cost(db, wo)
    return mv


# --------------------------------------------------------------------------- LOTO ↔ boshqaruv blokirovkasi


def assets_for_sensor(db: Session, sensor: Sensor) -> list[Asset]:
    """Sensor qaysi aktivlarga tegishli: quvvat/tebranish/podshipnik sensori shu bo'lsa, bir xil IFC
    elementi, yoki sensor KKS kodi aktiv kodi bilan boshlansa (H1 ierarxiyasi — komponent sensori
    uskuna LOTO siga kiradi)."""
    out = []
    for a in db.query(Asset).filter_by(project_id=sensor.project_id).all():
        cfg = a.config or {}
        if (
            a.power_sensor_id == sensor.id
            or cfg.get("vibration_sensor_id") == sensor.id
            or cfg.get("bearing_temp_sensor_id") == sensor.id
            or (a.element_guid and a.element_guid == sensor.element_guid)
        ):
            out.append(a)
        elif sensor.kks_code and a.kks_code and sensor.kks_code.startswith(a.kks_code):
            out.append(a)
    return out


def loto_blocks(db: Session, sensor: Sensor) -> list[str]:
    """Faol LOTO sabablari. Bo'sh bo'lmasa — boshqaruv buyrug'i taqiqlanadi va chetlab o'tilmaydi:
    energiya izolyatsiyasi xodim xavfsizligi uchun (IEC 60204-1 §5.3), LOTO ni ish buyrug'ida olib
    tashlash kerak."""
    ids = [a.id for a in assets_for_sensor(db, sensor)]
    rows = (
        db.query(WorkOrder)
        .filter(
            WorkOrder.project_id == sensor.project_id,
            WorkOrder.loto_active.is_(True),
            WorkOrder.status.in_(OPEN_STATES),
        )
        .order_by(WorkOrder.id)
        .all()
    )
    blocks: list[str] = []
    for w in rows:
        if w.asset_id in ids:
            blocks.append(
                f"LOTO faol: #{w.id} «{w.title}»" + (f" — {w.asset.name}" if w.asset else "")
            )
            continue
        for pt in w.loto_points or []:  # sensorning o'zi izolyatsiya nuqtasi sifatida ko'rsatilgan
            if isinstance(pt, dict) and pt.get("sensor_id") == sensor.id:
                blocks.append(
                    f"LOTO faol: #{w.id} «{w.title}» — izolyatsiya nuqtasi: {pt.get('label') or sensor.key}"
                )
                break
    return blocks


# --------------------------------------------------------------------------- tarix va xarajat hisoboti


def asset_history(db: Session, asset: Asset) -> dict:
    """Aktiv bo'yicha xizmat tarixi: ish buyruqlari (mehnat, qismlar, xarajat, ISO 14224 kodlari),
    jami va yil bo'yicha jamlanma, nosozlik rejimlari taqsimoti."""
    wos = (
        db.query(WorkOrder)
        .filter_by(asset_id=asset.id)
        .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .all()
    )
    items = []
    by_year: dict[int, dict] = {}
    modes: dict[str, int] = {}
    for w in wos:
        lh = labor_hours(db, w)
        parts = [
            {
                "part": m.part.name if m.part else "?",
                "qty": -m.qty,
                "unit": m.part.unit if m.part else "",
                "cost": round(-m.qty * _price(m), 2),
            }
            for m in consumed_movements(db, w)
        ]
        created = _aware(w.created_at) or datetime.now(timezone.utc)
        agg = by_year.setdefault(
            created.year,
            {
                "year": created.year,
                "work_orders": 0,
                "labor_hours": 0.0,
                "cost": 0.0,
                "downtime_hours": 0.0,
                "failures": 0,
            },
        )
        agg["work_orders"] += 1
        agg["labor_hours"] += lh
        agg["cost"] += w.cost or 0.0
        agg["downtime_hours"] += w.downtime_hours or 0.0
        if w.failure_mode:
            agg["failures"] += 1
            modes[w.failure_mode] = modes.get(w.failure_mode, 0) + 1
        items.append(
            {
                "id": w.id,
                "title": w.title,
                "status": w.status.value,
                "source": w.source,
                "plan_id": w.plan_id,
                "created_at": created.isoformat(),
                "closed_at": (_aware(w.closed_at).isoformat() if w.closed_at else None),
                "downtime_hours": w.downtime_hours,
                "labor_hours": lh,
                "labor_cost": w.labor_cost,
                "parts_cost": w.parts_cost,
                "cost": w.cost,
                "failure_mode": w.failure_mode,
                "failure_mode_label": FAILURE_MODES.get(w.failure_mode or "", ""),
                "failure_cause": w.failure_cause,
                "detection_method": w.detection_method,
                "parts": parts,
                "resolution": w.resolution,
            }
        )
    return {
        "asset": {"id": asset.id, "name": asset.name, "kks_code": asset.kks_code},
        "work_orders": items,
        "totals": {
            "work_orders": len(items),
            "cost": round(sum(i["cost"] or 0.0 for i in items), 2),
            "labor_hours": round(sum(i["labor_hours"] for i in items), 2),
            "parts_cost": round(sum(i["parts_cost"] or 0.0 for i in items), 2),
            "downtime_hours": round(sum(i["downtime_hours"] or 0.0 for i in items), 1),
            "failures": sum(1 for i in items if i["failure_mode"]),
        },
        "by_year": sorted(
            (
                {
                    **v,
                    "cost": round(v["cost"], 2),
                    "labor_hours": round(v["labor_hours"], 2),
                    "downtime_hours": round(v["downtime_hours"], 1),
                }
                for v in by_year.values()
            ),
            key=lambda x: -x["year"],
        ),
        "failure_modes": [
            {"code": k, "label": FAILURE_MODES.get(k, k), "count": n}
            for k, n in sorted(modes.items(), key=lambda kv: -kv[1])
        ],
    }
