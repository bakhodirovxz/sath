"""AG — Advisory Generation (ISO 13374-1 §5.7): aniqlangan holat va prognozdan amaliy tavsiya.

Chiqish: `problems` (nima bo'lyapti) va `tips` (nima qilish kerak) ro'yxatlari, HEALTH.* virtual
sensorlariga yozish va sog'liq «yomon/kritik» bo'lganda avtomatik ish buyrug'i (H2 CMMS bilan bog'lanadi).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...orm import Asset, Project
from .. import live, twin

# Holat → tavsiya (manba: ISO 20816-5 B ilova, IEC 60076-7, IEC 60422, IEC 60270, ISO 13373-3)
TIPS = {
    "vibration": "balansirovka / yo'naltirish, podshipnik zazorlarini tekshirish (ISO 20816-5 B ilova)",
    "bearing_temp": "moy sovutgichi, moy sathi va sifati (tahlil), yuklamani kamaytirish",
    "shaft_vibration": "val orbitasini yozib olish, podshipnik zazori va moy plyonkasini tekshirish (ISO 20816-5 B ilova)",
    "bearing_defect": "envelope-spektrni takrorlang, podshipnikni ko'zdan kechiring va almashtirishni rejalashtiring (ISO 13373-3)",
    "partial_discharge": "statorli chulg'am izolyatsiyasini sinash, qisman razryad manbasini lokalizatsiya qilish (IEC 60270)",
    "air_gap": "rotor/stator markazlashuvi va havo oralig'i o'lchovlarini tekshirish",
    "oil_water": "moyni quritish/filtrlash, namlik kirish yo'lini topish (IEC 60422)",
    "cavitation": "yuklamani kamaytirish yoki quyi byef sathini ko'tarish; runner eroziyasini tekshirish",
    "efficiency": "kavitatsiya/eroziya, yo'naltiruvchi apparat, quvur ifloslanishi, sarf o'lchovi",
    "electrical": "yukni darhol kamaytiring (IEC 60076-7)",
}


def advise(a: Asset, acq: dict, feats: dict, state: dict, health: dict, prog: dict) -> dict:
    problems = list(health["reasons"])
    tips: list[str] = []
    for name, item in state["items"].items():
        if item["state"] in ("alert", "alarm") and name in TIPS:
            tips.append(TIPS[name])
    # prognoz asosidagi ogohlantirishlar
    d = prog["days"]
    if d.get("vibration_d") is not None and d["vibration_d"] < 90:
        problems.append(f"tebranish trendi: D zonaga ≈ {d['vibration_d']:.0f} kunda yetadi")
        tips.append(TIPS["vibration"])
    if d.get("bearing_temp_alarm") is not None and d["bearing_temp_alarm"] < 60:
        problems.append(f"harorat trendi: alarm chegarasiga ≈ {d['bearing_temp_alarm']:.0f} kunda")
    if d.get("shaft_limit") is not None and d["shaft_limit"] < 90:
        problems.append(f"val tebranishi trendi: chegaraga ≈ {d['shaft_limit']:.0f} kunda")
    if prog["external_rul_days"] is not None and prog["external_rul_days"] < 180:
        src = next((e["source"] for e in state["external"] if e["rul_days"] == prog["external_rul_days"]), "tashqi tizim")
        problems.append(f"{src}: qolgan resurs ≈ {prog['external_rul_days']:.0f} kun")
    eff = health["efficiency"]
    if eff and eff["deviation_pct"] is not None and eff["deviation_pct"] < -5 and eff.get("running"):
        tips.append(TIPS["efficiency"])
    cav = health["cavitation"]
    if cav and cav["sigma_critical"] > 0 and cav["sigma_plant"] < cav["sigma_critical"]:
        tips.append(TIPS["cavitation"])
    elec = health["electrical"]
    if elec and (elec["load_factor"] > 1.5 or elec["hot_spot_c"] > 140):
        tips.append(TIPS["electrical"])
    seen: set[str] = set()
    tips = [t for t in tips if not (t in seen or seen.add(t))]
    return {"problems": problems, "tips": tips}


def publish(db: Session, project: Project, report: dict) -> dict:
    """Sog'liq indekslarini HEALTH.<asset> virtual sensorlariga yozish (trend, alarm < 60)."""
    items = []
    for it in report["assets"]:
        twin.twin_sensor(
            db,
            project.id,
            f"HEALTH.{it['asset_id']}",
            f"{it['name']} — sog'liq indeksi",
            "%",
            kind="value",
            low=60,
        )
        items.append({"key": f"HEALTH.{it['asset_id']}", "value": float(it["score"])})
    db.commit()
    if items:
        live.ingest(db, project.id, items, source="health")
    return report


def auto_work_orders(db: Session, project: Project, report: dict) -> int:
    """Avtomatik ish buyrug'i: sog'liq «yomon/kritik» bo'lsa va shu aktiv uchun ochiq health-buyruq bo'lmasa —
    yaratiladi (muallif — loyiha egasi), muhandislarga bildirishnoma. Qaytaradi: yaratilganlar soni."""
    from ... import notifications
    from ...orm import Role, WorkOrder, WorkOrderStatus

    n = 0
    for it in report.get("assets", []):
        if it["level"] not in ("yomon", "kritik"):
            continue
        exists = (
            db.query(WorkOrder)
            .filter(
                WorkOrder.asset_id == it["asset_id"],
                WorkOrder.source == "health",
                WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.in_progress]),
            )
            .first()
        )
        if exists:
            continue
        w = WorkOrder(
            project_id=project.id,
            asset_id=it["asset_id"],
            created_by=project.created_by,
            title=f"{it['name']}: sog'liq indeksi {it['score']} ({it['level']})",
            description="Muammolar: "
            + "; ".join(it["problems"])
            + (" | Tavsiya: " + "; ".join(it["tips"]) if it["tips"] else ""),
            priority="critical" if it["level"] == "kritik" else "high",
            source="health",
            detection_method="condition",  # ISO 14224: holat monitoringi orqali aniqlandi
        )
        db.add(w)
        db.flush()
        notifications.push(
            db,
            notifications.member_ids(db, project.id, Role.engineer),
            "workorder",
            f"Avto ish buyrug'i: {w.title}",
            "; ".join(it["problems"])[:300],
            f"/projects/{project.id}/dashboard",
        )
        n += 1
    if n:
        db.commit()
    return n
