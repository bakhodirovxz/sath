"""Holat monitoringi (condition monitoring) va sog'liq indeksi — GE APM Health / Voith OnCare uslubida.

Har aktiv (agregat) uchun:
  - tebranish: ISO 10816-5 / 20816-5 zonalari (A/B/C/D) mashina guruhi bo'yicha, 30 kunlik trend → C/D
    chegarasigacha qolgan kunlar (RUL);
  - podshipnik harorati: ogohlantirish/alarm chegaralari, trend;
  - FIK: egizak virtual sensori (TWIN.*.EFF) 30 kunlik trend — oyiga % pasayish, model bilan og'ish;
  - anomaliya: oxirgi qiymatning 30 kunlik bazaga nisbatan z-score (|z| > 3);
  - kavitatsiya: Toma σ_plant = (H_atm − H_vap − H_s)/H_net vs σ_kritik (turbina turi, solishtirma tezlik);
  - sog'liq indeksi 0–100 (ballardan ayirish) va tavsiyalar.
Natija HEALTH.<asset> virtual sensoriga yoziladi (trend, alarm < 60).

ISO 10816-5:2000 A ilovasi (podshipnik korpusi tebranish tezligi, mm/s r.m.s.):
  1-guruh (gorizontal, >300 ayl/min): A/B 1.6, B/C 2.5, C/D 4.0
  2-guruh (gorizontal, kapsulali/bulb, <300): 2.5 / 4.0 / 6.4
  3-guruh (vertikal, hamma podshipnik poydevorga): 1.6 / 2.5 / 4.0
  4-guruh (vertikal, yuqori podshipnik statorga; 1-nuqta): 2.5 / 4.0 / 6.4 (boshqa podshipniklar 1.6/2.5/4.0)
Toma (Krivchenko/USBR): Francis σ_c = 0.0625·(n_s/380)², Kaplan σ_c = 0.28 + (n_s/380)³, n_s = n·√P_kW/H^1.25.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..orm import AlarmState, Asset, Project, ReadingHourly, Sensor
from . import live, twin

VIB_ZONES = {  # guruh → (A/B, B/C, C/D)
    1: (1.6, 2.5, 4.0),
    2: (2.5, 4.0, 6.4),
    3: (1.6, 2.5, 4.0),
    4: (2.5, 4.0, 6.4),
}
ZONE_NOTE = {
    "A": "yangi mashina darajasi",
    "B": "cheklanmagan uzoq muddatli ish",
    "C": "uzoq muddatli ishga yaroqsiz — texnik xizmatni rejalashtiring",
    "D": "shikastlanish xavfi — to'xtatish talab etilishi mumkin",
}
H_VAP = 0.24  # suv bug' bosimi napori, m (20 °C)


def vib_zone(v: float, group: int = 4) -> str:
    ab, bc, cd = VIB_ZONES.get(int(group), VIB_ZONES[4])
    return "A" if v < ab else "B" if v < bc else "C" if v < cd else "D"


def thoma_critical(turbine_type: str, ns: float) -> float:
    t = (turbine_type or "Francis").lower()
    if "kaplan" in t or "propeller" in t or "bulb" in t:
        return 0.28 + (ns / 380) ** 3
    if "pelton" in t:
        return 0.0  # erkin oqim — kavitatsiya σ bilan baholanmaydi
    return 0.0625 * (ns / 380) ** 2


def specific_speed(n_rpm: float, p_kw: float, h_m: float) -> float:
    return n_rpm * math.sqrt(max(p_kw, 0.0)) / max(h_m, 0.1) ** 1.25


def _hourly(db: Session, sensor_id: int, days: int = 30) -> list[tuple[datetime, float]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(ReadingHourly.hour, ReadingHourly.avg)
        .filter(ReadingHourly.sensor_id == sensor_id, ReadingHourly.hour >= since)
        .order_by(ReadingHourly.hour)
        .all()
    )
    return [(live._aware(h), float(v)) for h, v in rows]


def trend(points: list[tuple[datetime, float]]) -> tuple[float, float, float] | None:
    """Chiziqli regressiya: (o'zgarish / kun, o'rtacha, std). Kamida 12 nuqta."""
    if len(points) < 12:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [v for _, v in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False)) / sxx if sxx > 0 else 0.0
    std = math.sqrt(sum((y - my) ** 2 for y in ys) / max(n - 1, 1))
    return slope, my, std


def _sensor_block(db: Session, s: Sensor | None) -> dict | None:
    if s is None:
        return None
    v = twin._live(s)
    pts = _hourly(db, s.id)
    tr = trend(pts)
    z = None
    if tr and tr[2] > 1e-9 and v is not None:
        z = (v - tr[1]) / tr[2]
    return {
        "sensor_id": s.id,
        "name": s.name,
        "unit": s.unit,
        "value": v,
        "stale": s.alarm == AlarmState.stale,
        "slope_per_day": round(tr[0], 5) if tr else None,
        "baseline_mean": round(tr[1], 4) if tr else None,
        "baseline_std": round(tr[2], 4) if tr else None,
        "z": round(z, 2) if z is not None else None,
        "anomaly": bool(z is not None and abs(z) > 3),
        "points": len(pts),
    }


def _days_to(value: float | None, slope: float | None, limit: float) -> float | None:
    if value is None or slope is None or slope <= 1e-9 or value >= limit:
        return None
    return round((limit - value) / slope, 0)


def asset_health(
    db: Session, project: Project, a: Asset, twin_state: dict | None, slots: dict[str, Sensor]
) -> dict:
    cfg = a.config or {}
    score = 100.0
    problems: list[str] = []
    tips: list[str] = []
    group = int(cfg.get("machine_group") or 4)

    # --- tebranish ---
    vib = _sensor_block(
        db, db.get(Sensor, cfg["vibration_sensor_id"]) if cfg.get("vibration_sensor_id") else None
    )
    if vib and vib["value"] is not None:
        zone = vib_zone(vib["value"], group)
        vib["zone"] = zone
        vib["zone_note"] = ZONE_NOTE[zone]
        vib["days_to_c"] = _days_to(vib["value"], vib["slope_per_day"], VIB_ZONES[group][1])
        vib["days_to_d"] = _days_to(vib["value"], vib["slope_per_day"], VIB_ZONES[group][2])
        score -= {"A": 0, "B": 8, "C": 30, "D": 60}[zone]
        if zone in ("C", "D"):
            problems.append(f"tebranish {vib['value']:.2f} mm/s — {zone} zona ({ZONE_NOTE[zone]})")
        if vib["days_to_d"] is not None and vib["days_to_d"] < 90:
            problems.append(f"tebranish trendi: D zonaga ≈ {vib['days_to_d']:.0f} kunda yetadi")
            tips.append(
                "balansirovka / yo'naltirish, podshipnik zazorlarini tekshirish (ISO 20816-5 B ilova)"
            )
        if vib["anomaly"]:
            score -= 10
            problems.append(f"tebranish anomaliyasi (z = {vib['z']})")

    # --- podshipnik harorati ---
    temp = _sensor_block(
        db,
        db.get(Sensor, cfg["bearing_temp_sensor_id"])
        if cfg.get("bearing_temp_sensor_id")
        else None,
    )
    if temp and temp["value"] is not None:
        warn = float(cfg.get("temp_warn") or 70)
        alarm = float(cfg.get("temp_alarm") or 80)
        temp["warn"], temp["alarm"] = warn, alarm
        temp["days_to_alarm"] = _days_to(temp["value"], temp["slope_per_day"], alarm)
        if temp["value"] >= alarm:
            score -= 40
            problems.append(f"podshipnik harorati {temp['value']:.1f} °C ≥ {alarm} °C (alarm)")
            tips.append("moy sovutgichi, moy sathi va sifati (tahlil), yuklamani kamaytirish")
        elif temp["value"] >= warn:
            score -= 15
            problems.append(f"podshipnik harorati {temp['value']:.1f} °C ≥ {warn} °C")
        if temp["days_to_alarm"] is not None and temp["days_to_alarm"] < 60:
            problems.append(
                f"harorat trendi: alarm chegarasiga ≈ {temp['days_to_alarm']:.0f} kunda"
            )
        if temp["anomaly"]:
            score -= 10
            problems.append(f"harorat anomaliyasi (z = {temp['z']})")

    # --- FIK (egizak) ---
    eff = None
    unit = None
    if twin_state and a.power_sensor_id:
        unit = next(
            (u for u in twin_state.get("units", []) if u["sensor_id"] == a.power_sensor_id), None
        )
    if unit:
        eff_sensor = (
            db.query(Sensor)
            .filter_by(project_id=project.id, key=f"TWIN.{a.power_sensor_id}.EFF")
            .first()
        )
        eff_pts = _hourly(db, eff_sensor.id) if eff_sensor else []
        tr = trend(eff_pts)
        dev = unit.get("deviation_pct")
        eff = {
            "measured": unit.get("efficiency"),
            "expected": unit.get("expected_efficiency"),
            "deviation_pct": dev,
            "trend_pct_per_month": round(tr[0] * 30 * 100, 3) if tr else None,
            "running": unit.get("running"),
        }
        if dev is not None and unit.get("running"):
            if dev < -10:
                score -= 30
                problems.append(f"quvvat model kutganidan {abs(dev):.1f} % kam (FIK pasaygan)")
                tips.append(
                    "kavitatsiya/eroziya, yo'naltiruvchi apparat, quvur ifloslanishi, sarf o'lchovi"
                )
            elif dev < -5:
                score -= 15
                problems.append(f"quvvat model kutganidan {abs(dev):.1f} % kam")
        if eff["trend_pct_per_month"] is not None and eff["trend_pct_per_month"] < -0.5:
            problems.append(f"FIK trendi: oyiga {abs(eff['trend_pct_per_month']):.2f} % pasaymoqda")

    # --- kavitatsiya (Toma) ---
    cav = None
    tail = twin._live(slots.get("downstream_level"))
    runner = cfg.get("runner_elev_m")
    rpm = float(cfg.get("rated_speed_rpm") or 0)
    if unit and tail is not None and runner is not None and rpm > 0 and unit.get("head_net_m"):
        h_net = float(unit["head_net_m"])
        elev = float(runner)
        hs = elev - tail  # so'rish balandligi (+ runner suvdan yuqorida)
        h_atm = 10.33 - elev / 900.0
        sigma = (h_atm - H_VAP - hs) / h_net
        p_kw = float(unit.get("measured_mw") or unit.get("expected_mw") or 0) * 1000
        ns = specific_speed(rpm, p_kw, h_net)
        sc = thoma_critical(str(cfg.get("turbine_type") or "Francis"), ns)
        cav = {
            "sigma_plant": round(sigma, 4),
            "sigma_critical": round(sc, 4),
            "ns": round(ns, 1),
            "suction_head_m": round(hs, 2),
            "margin": round(sigma - sc, 4),
        }
        if sc > 0 and sigma < sc:
            score -= 20
            problems.append(
                f"kavitatsiya xavfi: σ_plant {sigma:.3f} < σ_kr {sc:.3f} (quyi byef past / napor katta)"
            )
            tips.append(
                "yuklamani kamaytirish yoki quyi byef sathini ko'tarish; runner eroziyasini tekshirish"
            )
        elif sc > 0 and sigma < 1.15 * sc:
            problems.append(f"kavitatsiya zaxirasi kam: σ {sigma:.3f} / σ_kr {sc:.3f}")

    # --- elektr: transformator/generator yuklanishi (aktiv config: rated_mva, cos_phi, ambient_c) ---
    elec = None
    rated_mva = float(cfg.get("rated_mva") or 0)
    if rated_mva > 0 and a.power_sensor_id:
        ps = db.get(Sensor, a.power_sensor_id)
        pw = twin._live(ps)
        if pw is not None:
            from ges_sim import transformer as trf

            cosphi = float(cfg.get("cos_phi") or 0.9)
            amb = float(cfg.get("ambient_c") or 30)
            k = (pw / cosphi) / rated_mva
            x, y, dor, dhr = trf.COOLING[str(cfg.get("cooling") or "ONAF")][:4]
            theta_o = amb + dor * ((1 + 6 * k**2) / 7) ** x
            theta_h = theta_o + dhr * k**y
            elec = {
                "load_factor": round(k, 3),
                "top_oil_c": round(theta_o, 1),
                "hot_spot_c": round(theta_h, 1),
                "aging_rate": round(trf.aging_rate(theta_h, "upgraded"), 2),
            }
            if k > 1.5 or theta_h > 140:
                score -= 40
                problems.append(
                    f"transformator: K = {k:.2f}, issiq nuqta {theta_h:.0f} °C — favqulodda chegara"
                )
                tips.append("yukni darhol kamaytiring (IEC 60076-7)")
            elif k > 1.0 or theta_h > 120:
                score -= 15
                problems.append(
                    f"transformator ortiqcha yuk K = {k:.2f}, issiq nuqta {theta_h:.0f} °C (qarish {elec['aging_rate']}×)"
                )

    # --- texnik xizmat va aloqa ---
    for s in (vib, temp):
        if s and s["stale"]:
            score -= 5
            problems.append(f"{s['name']}: aloqa yo'q")
    score = max(min(round(score), 100), 0)
    level = (
        "yaxshi"
        if score >= 80
        else "qoniqarli"
        if score >= 60
        else "yomon"
        if score >= 40
        else "kritik"
    )
    return {
        "asset_id": a.id,
        "name": a.name,
        "element_guid": a.element_guid,
        "score": score,
        "level": level,
        "vibration": vib,
        "bearing_temp": temp,
        "efficiency": eff,
        "cavitation": cav,
        "electrical": elec,
        "problems": problems,
        "tips": tips,
        "machine_group": group,
    }


def compute(db: Session, project: Project) -> dict:
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    ts = twin.compute(db, project)
    assets = db.query(Asset).filter_by(project_id=project.id).order_by(Asset.name).all()
    items = [asset_health(db, project, a, ts, slots) for a in assets]
    maint = {x["id"]: x for x in twin.asset_status(db, project)}
    for it in items:
        m = maint.get(it["asset_id"])
        if m and m["status"] == "overdue":
            it["score"] = max(it["score"] - 20, 0)
            it["problems"].append("texnik xizmat muddati o'tgan")
        elif m and m["status"] == "due":
            it["problems"].append("texnik xizmat yaqin")
        it["level"] = (
            "yaxshi"
            if it["score"] >= 80
            else "qoniqarli"
            if it["score"] >= 60
            else "yomon"
            if it["score"] >= 40
            else "kritik"
        )
    plant = round(sum(i["score"] for i in items) / len(items)) if items else None
    return {"plant_score": plant, "assets": items, "twin_status": ts.get("status")}


def publish(db: Session, project: Project) -> dict:
    """Sog'liq indekslarini HEALTH.<asset> virtual sensorlariga yozish (trend, alarm < 60)."""
    res = compute(db, project)
    items = []
    for it in res["assets"]:
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
    return res


def auto_work_orders(db: Session, project: Project, report: dict) -> int:
    """Avtomatik ish buyrug'i: sog'liq «yomon/kritik» bo'lsa va shu aktiv uchun ochiq health-buyruq bo'lmasa —
    yaratiladi (muallif — loyiha egasi), muhandislarga bildirishnoma. Qaytaradi: yaratilganlar soni."""
    from .. import notifications
    from ..orm import Role, WorkOrder, WorkOrderStatus

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


def tick_hourly(db: Session) -> int:
    """Fon (soatlik): aktivlari bor barcha loyihalar uchun sog'liq indeksi."""
    n = 0
    for pid in {a.project_id for a in db.query(Asset.project_id).all()}:
        project = db.get(Project, pid)
        if project is not None:
            auto_work_orders(db, project, publish(db, project))
            n += 1
    return n
