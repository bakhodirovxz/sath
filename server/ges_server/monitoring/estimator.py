"""Holat baholash va ortiqcha o'lchovlarni solishtirish (I2).

Muammo: o'lchovlar orasidagi fizik bog'liqlik ishlatilmaydi. Umumiy quvvat sensori agregatlar
yig'indisiga, quvur sarfi quvvat va napordan hisoblangan sarfga, sath o'zgarishi esa suv balansiga
mos kelishi kerak. Bu bog'liqliklar ikki ish qiladi: yomon ma'lumotni aniqlaydi va sensor
yo'qolganda uning o'rnini bosadi.

Ikki qism:

1. **Ortiqchalik (redundancy)** — bitta kattalik uchun bir nechta manba solishtiriladi:
   * quvvat: `total_power` sensori ↔ agregatlar yig'indisi;
   * sarf: `penstock_flow` sensori ↔ egizak modeli (quvvat va napordan) hisoblagan sarf;
   * sath: o'lchangan o'zgarish ↔ suv balansidan kutilgan o'zgarish.
   Chidamlilik (tolerance) nisbiy va absolyut qismdan iborat; oshsa — `alert`, ikki baravar oshsa
   `alarm`. Natija `TWIN.CHK.<nom>` virtual sensoriga (og'ish %) yoziladi — alarm oddiy chegara bilan.

2. **Holat baholash (Kalman, 1D)** — ombor sathi uchun:
       bashorat:  h⁻ = h + (Q_in − Q_chiq)·Δt / A(h),   P⁻ = P + Q_proc
       yangilash: K = P⁻/(P⁻ + R),  h = h⁻ + K·(h_o'lchov − h⁻),  P = (1 − K)·P⁻
   bu yerda A(h) — ko'zgu yuzasi (maydon pasporti saqlash egri chizig'idan yoki `area_km2`),
   Q_proc — model shovqini, R — sensor shovqini (dispersiyasi). Sensor yaroqsiz yoki **qotgan**
   bo'lsa faqat bashorat qadami bajariladi va natija `substituted` sifati bilan yoziladi
   (`TWIN.EST.LEVEL`).

**Qotgan sensor (frozen)**: oxirgi N o'lchov bir xil (std ≈ 0), lekin balans shu davrda sezilarli
o'zgarishni kutadi. Bu holda sensor «qotgan» deb belgilanadi, baho uning o'rnini bosadi va
dispetcherlarga bildirishnoma yuboriladi. Ma'lumot yetarli bo'lmasa — hech narsa taxmin qilinmaydi
(`status: insufficient`).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..orm import Project, Reading, Sensor
from . import live, twin

FROZEN_N = 6  # qotganlikni tekshirish uchun oxirgi o'lchovlar soni
FROZEN_EPS = 1e-9  # o'zgarish yo'q deb hisoblanadigan std
LEVEL_PROC_VAR = 1e-4  # model shovqini (m²) — bir qadamda
LEVEL_MEAS_VAR = 4e-4  # sensor shovqini (m²) ≈ 2 sm
TOL = {  # (nisbiy, absolyut) — kattalikka qarab
    "power_total": (0.03, 0.5),  # 3 % yoki 0.5 MW
    "penstock_flow": (0.08, 1.0),  # 8 % yoki 1 m³/s (model sarfi taxminiy)
    "level_balance": (0.0, 0.05),  # 5 sm/soat — balans va o'lchov farqi
}


def _aware(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=timezone.utc))


def _tol(name: str, scale: float) -> float:
    rel, abs_ = TOL[name]
    return max(rel * abs(scale), abs_)


def _status(diff: float, tol: float) -> str:
    if abs(diff) <= tol:
        return "ok"
    return "alarm" if abs(diff) > 2 * tol else "alert"


# --------------------------------------------------------------------------- ortiqchalik


def redundancy(db: Session, project: Project, state: dict | None = None) -> list[dict]:
    """Ortiqcha manbalarni solishtirish. `state` — tayyor egizak holati (bo'lmasa hisoblanadi)."""
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    st = state if state is not None else twin.compute(db, project)
    checks: list[dict] = []

    # 1) umumiy quvvat ↔ agregatlar yig'indisi
    total = twin._live(slots.get("total_power"))
    units = [u for u in st.get("units", []) if u.get("measured_mw") is not None]
    if total is not None and units:
        s = sum(u["measured_mw"] for u in units)
        tol = _tol("power_total", max(total, s))
        checks.append(
            {
                "name": "power_total",
                "label": "Umumiy quvvat ↔ agregatlar yig'indisi",
                "unit": "MW",
                "sources": [
                    {"label": "umumiy sensor", "value": round(total, 3)},
                    {"label": "agregatlar yig'indisi", "value": round(s, 3)},
                ],
                "diff": round(total - s, 3),
                "tolerance": round(tol, 3),
                "status": _status(total - s, tol),
            }
        )

    # 2) quvur sarfi ↔ modeldan hisoblangan sarf
    q_meas = twin._live(slots.get("penstock_flow"))
    q_model = sum(u["flow_m3s"] for u in st.get("units", []) if u.get("flow_m3s"))
    if q_meas is not None and q_model > 0 and st.get("status") == "ok":
        tol = _tol("penstock_flow", max(q_meas, q_model))
        checks.append(
            {
                "name": "penstock_flow",
                "label": "Quvur sarfi ↔ model (quvvat va napordan)",
                "unit": "m³/s",
                "sources": [
                    {"label": "sarf o'lchagichi", "value": round(q_meas, 3)},
                    {"label": "model", "value": round(q_model, 3)},
                ],
                "diff": round(q_meas - q_model, 3),
                "tolerance": round(tol, 3),
                "status": _status(q_meas - q_model, tol),
                "note": "model sarfi kalibrovkalanmagan bo'lsa farq model xatosini ham o'z ichiga oladi"
                if not (project.calibration or {})
                else "",
            }
        )
    return checks


# --------------------------------------------------------------------------- suv balansi va Kalman


def surface_area_m2(project: Project, level_m: float | None) -> float | None:
    """Ko'zgu yuzasi: saqlash egri chizig'idan (aniqroq) yoki pasportdagi `area_km2`."""
    from ges_sim import site
    from ges_sim.reservoir import StorageCurve

    st = {**site.defaults(), **(project.site or {})}
    elev, vol = st.get("curve_elev"), st.get("curve_vol")
    if elev and vol and len(elev) == len(vol) and len(elev) >= 2 and level_m is not None:
        try:
            curve = StorageCurve(tuple(float(x) for x in elev), tuple(float(v) for v in vol))
            d = 0.5
            area = (curve.volume(level_m + d) - curve.volume(level_m - d)) / (2 * d)
            if area > 0:
                return area
        except (ValueError, TypeError):
            pass
    area_km2 = st.get("area_km2")
    return float(area_km2) * 1e6 if area_km2 else None


def _recent(db: Session, sensor: Sensor | None, n: int = FROZEN_N) -> list[tuple[datetime, float]]:
    if sensor is None:
        return []
    rows = (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == sensor.id, Reading.quality != "bad")
        .order_by(Reading.ts.desc())
        .limit(n)
        .all()
    )
    return [(_aware(t), float(v)) for t, v in reversed(rows)]


def frozen(points: list[tuple[datetime, float]], expected_change: float, tol: float) -> bool:
    """Sensor qotganmi: oxirgi nuqtalar bir xil, lekin model sezilarli o'zgarishni kutadi."""
    if len(points) < FROZEN_N:
        return False
    vals = [v for _, v in points]
    spread = max(vals) - min(vals)
    return spread <= FROZEN_EPS and abs(expected_change) > tol


def balance(
    db: Session, project: Project, state: dict | None = None, level_hint: float | None = None
) -> dict:
    """Suv balansidan kutilgan sath o'zgarishi (m/soat) va uning tarkibi.

    `level_hint` — sath sensori yaroqsiz (qotgan/aloqasiz) bo'lganda ko'zgu yuzasini hisoblash uchun
    oxirgi baho; yuza sath bilan sekin o'zgaradi, shuning uchun bu maqbul."""
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    st = state if state is not None else twin.compute(db, project)
    level = twin._live(slots.get("upstream_level"))
    if level is None:
        level = level_hint
    inflow = twin._live(slots.get("inflow"))
    spill = twin._live(slots.get("spillway_flow")) or 0.0
    q_turb = twin._live(slots.get("penstock_flow"))
    if q_turb is None and st.get("status") == "ok":
        q_turb = sum(u["flow_m3s"] for u in st.get("units", []) if u.get("flow_m3s")) or None
    area = surface_area_m2(project, level)
    if inflow is None or q_turb is None or area is None or level is None:
        missing = [
            k
            for k, v in (
                ("kiruvchi sarf", inflow),
                ("chiqim sarfi", q_turb),
                ("ko'zgu yuzasi (pasport)", area),
                ("yuqori byef sathi", level),
            )
            if v is None
        ]
        return {"status": "insufficient", "missing": missing}
    net = inflow - q_turb - spill  # m³/s
    return {
        "status": "ok",
        "level_m": level,
        "inflow_m3s": inflow,
        "outflow_m3s": round(q_turb + spill, 3),
        "net_m3s": round(net, 3),
        "area_m2": round(area, 1),
        "dlevel_m_per_h": round(net * 3600.0 / area, 5),
    }


def estimate(db: Session, project: Project, state: dict | None = None) -> dict:
    """Ombor sathi uchun 1D Kalman bahosi + qotgan sensor aniqlash.

    Holat `Project.dashboard["estimator"]` da saqlanadi ({level, P, ts}) — har chaqiruvda bir qadam."""
    st = state if state is not None else twin.compute(db, project)
    cfg = dict(project.dashboard or {})
    prev = dict(cfg.get("estimator") or {})
    bal = balance(db, project, st, level_hint=prev.get("level"))
    if bal["status"] != "ok":
        return {"status": "insufficient", "missing": bal.get("missing", [])}
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    sensor = slots.get("upstream_level")
    meas = twin._live(sensor)
    now = datetime.now(timezone.utc)
    last_ts = _aware(datetime.fromisoformat(prev["ts"])) if prev.get("ts") else None
    dt_h = min((now - last_ts).total_seconds() / 3600.0, 6.0) if last_ts else 0.0
    h_prev = float(prev.get("level", meas if meas is not None else bal["level_m"]))
    p_prev = float(prev.get("P", LEVEL_MEAS_VAR))

    # bashorat (balans bo'yicha)
    expected_change = bal["dlevel_m_per_h"] * dt_h
    h_pred = h_prev + expected_change
    p_pred = p_prev + LEVEL_PROC_VAR * max(dt_h, 1e-3)

    pts = _recent(db, sensor)
    is_frozen = frozen(pts, expected_change, _tol("level_balance", 1.0) * max(dt_h, 1.0))
    usable = meas is not None and not is_frozen and not (sensor is not None and sensor.stale)
    if usable:
        k = p_pred / (p_pred + LEVEL_MEAS_VAR)
        h_est = h_pred + k * (meas - h_pred)
        p_est = (1 - k) * p_pred
        source = "measured"
    else:  # sensor yo'q/qotgan — faqat model qadami
        h_est, p_est, k = h_pred, p_pred, 0.0
        source = "model"
    innovation = (meas - h_pred) if meas is not None else None
    return {
        "status": "ok",
        "level_measured_m": meas,
        "level_estimate_m": round(h_est, 4),
        "sigma_m": round(math.sqrt(p_est), 4),
        "gain": round(k, 4),
        "source": source,
        "frozen": is_frozen,
        "sensor_id": sensor.id if sensor else None,
        "sensor_key": sensor.key if sensor else None,
        "innovation_m": round(innovation, 4) if innovation is not None else None,
        "expected_change_m": round(expected_change, 5),
        "dt_hours": round(dt_h, 3),
        "balance": bal,
    }


def _save_state(db: Session, project: Project, est: dict) -> None:
    cfg = dict(project.dashboard or {})
    cfg["estimator"] = {
        "level": est["level_estimate_m"],
        "P": est["sigma_m"] ** 2,
        "ts": datetime.now(timezone.utc).isoformat(),
        "frozen": est["frozen"],
    }
    project.dashboard = cfg


def run(db: Session, project: Project, state: dict | None = None) -> dict:
    """Baho va tekshiruvlarni hisoblab, virtual sensorlarga yozadi:
    `TWIN.EST.LEVEL` (baho, sifat `substituted` — model qadami bo'lsa) va `TWIN.CHK.<nom>` (og'ish %).
    Qotgan sensor birinchi marta aniqlanganda dispetcherlarga bildirishnoma."""
    from .. import notifications
    from ..orm import Role

    st = state if state is not None else twin.compute(db, project)
    est = estimate(db, project, st)
    checks = redundancy(db, project, st)
    items: list[dict] = []
    if est["status"] == "ok":
        twin.twin_sensor(
            db, project.id, "TWIN.EST.LEVEL", "Ombor sathi — baho (Kalman)", "m", kind="level"
        )
        items.append(
            {
                "key": "TWIN.EST.LEVEL",
                "value": est["level_estimate_m"],
                "quality": "substituted" if est["source"] == "model" else "good",
            }
        )
        was_frozen = bool((project.dashboard or {}).get("estimator", {}).get("frozen"))
        _save_state(db, project, est)
        if est["frozen"] and not was_frozen:
            notifications.push(
                db,
                notifications.member_ids(db, project.id, Role.operator, at_least=True),
                "twin",
                f"Sensor qotgan: {est['sensor_key']}",
                f"sath o'zgarmayapti, balans {est['expected_change_m']:+.3f} m kutmoqda — baho o'rnini bosdi",
                f"/projects/{project.id}/dashboard",
            )
    for c in checks:
        scale = max(abs(s["value"]) for s in c["sources"]) or 1.0
        key = f"TWIN.CHK.{c['name'].upper()}"
        twin.twin_sensor(
            db,
            project.id,
            key,
            f"{c['label']} — farq",
            "%",
            kind="deviation",
            low=-round(c["tolerance"] / scale * 100, 2),
            high=round(c["tolerance"] / scale * 100, 2),
        )
        items.append({"key": key, "value": round(c["diff"] / scale * 100, 3)})
    db.commit()
    if items:
        live.ingest(db, project.id, items, source="estimator")
    return {"estimate": est, "checks": checks}


def tick_all(db: Session) -> int:
    """Fon vazifasi: barcha loyihalar uchun baho va ortiqchalik tekshiruvi."""
    n = 0
    for project in db.query(Project).all():
        res = run(db, project)
        if res["estimate"]["status"] == "ok" or res["checks"]:
            n += 1
    return n
