"""Raqamli egizak (digital twin): jonli SCADA holati ↔ BIM modeli.

* Kutilayotgan quvvat: mimik sxemadagi sath/sarf sensorlaridan (yuqori/quyi byef → brutto napor,
  quvur sarfi → agregatlar orasida) va tasdiqlangan model versiyasidagi Pset_GES_* (turbina FIK
  egri chizig'i, quvur yo'qotishi) → P_kutilgan; o'lchangan P bilan solishtirish → og'ish %,
  haqiqiy FIK. Natijalar virtual sensorlarga (protocol="twin") yoziladi — og'ish alarmlari, tarix,
  grafiklar oddiy sensorlar kabi ishlaydi.
* Aktivlar: agregat ish soatlari, ishga tushishlar, energiya (kunlik statistika), texnik xizmat
  muddati (soat bo'yicha) → holat ok/due/overdue.
* Vaqt mashinasi: istalgan vaqtdagi sensorlar holati (snapshot) — 3D/sxemada qayta ko'rish.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ges_sim.penstock import PenstockSpec, net_head
from ges_sim.turbine import RHO, TurbineSpec
from sqlalchemy.orm import Session

from ..models import storage
from ..orm import (
    AlarmState,
    Asset,
    Model,
    Project,
    Reading,
    ReadingHourly,
    Sensor,
    UnitDayStats,
    Version,
    VersionState,
)
from ..sim import ges_params
from . import live
from .historian import floor_hour

log = logging.getLogger("ges_server.twin")
G = 9.81
# Agregat "ishlayapti" chegarasi: high_alarm ning 1 % i yoki 0.5 MW
RUN_THRESHOLD = 0.5


def _slots(db: Session, project: Project, sensors: list[Sensor]) -> dict[str, Sensor]:
    """Dispetcher paneli bog'lanishi (qo'lda + avto) → slot → sensor."""
    from .router import _auto_mimic  # aylanma importdan qochish

    cfg = project.dashboard or {}
    mimic = {k: v for k, v in (cfg.get("mimic") or {}).items() if v}
    _auto_mimic(mimic, sensors)
    by_id = {s.id: s for s in sensors}
    return {slot: by_id[sid] for slot, sid in mimic.items() if sid in by_id}


def model_params(db: Session, project_id: int) -> dict | None:
    """Loyihaning tasdiqlangan (yo'q bo'lsa oxirgi) versiyasidan Pset_GES_* parametrlari."""
    versions = (
        db.query(Version)
        .join(Model, Model.id == Version.model_id)
        .filter(Model.project_id == project_id)
        .order_by(Version.id.desc())
        .all()
    )
    if not versions:
        return None
    v = next((x for x in versions if x.state == VersionState.published), versions[0])
    try:
        params = ges_params.extract(storage.resolve(v.file_sha256))
    except (FileNotFoundError, Exception):  # noqa: BLE001 — buzuq fayl egizakni to'xtatmasin
        return None
    params["version_id"] = v.id
    return params if params.get("units") else None


def safety(
    db: Session,
    project: Project,
    slots: dict[str, Sensor] | None = None,
    overrides: dict | None = None,
) -> list[dict]:
    """Xavfsizlik ko'rsatkichlari: maydon pasporti + jonli sath → gerb zaxirasi, suv tashlagich zaxirasi,
    to'g'on sirpanish zaxirasi (joriy sathda), inshootlarning quyi byefdan balandligi.
    Har biri: {name, value, unit, ok, note}."""
    from ges_sim import dam_stability, site
    from ges_sim.schema import parse

    st = {**site.defaults(), **(project.site or {})}
    if slots is None:
        sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
        slots = _slots(db, project, sensors)
    ov = overrides or {}

    def val(slot: str) -> float | None:
        if ov.get(slot) is not None:
            return float(ov[slot])
        return _live(slots.get(slot))

    up, down, inflow = val("upstream_level"), val("downstream_level"), val("inflow")
    out = list(site.risk_summary(st)) if project.site else []
    if up is not None:
        fb = float(st["crest_elevation_m"]) - up
        out.append(
            {
                "name": "Gerb zaxirasi (jonli sath)",
                "value": round(fb, 2),
                "unit": "m",
                "ok": fb >= 1.0,
                "note": f"sath {up:.2f} m, gerb {st['crest_elevation_m']} m",
            }
        )
        # Suv tashlagich o'tkazuvchanligi FPU da vs loyihaviy toshqin
        h = max(float(st["max_level_m"]) - float(st["spill_crest_m"]), 0.0)
        q_cap = float(st["spill_coeff"]) * float(st["spill_width_m"]) * (2 * G) ** 0.5 * h**1.5
        q_need = float(st["flood_01_m3s"])
        if q_need > 0:
            out.append(
                {
                    "name": "Suv tashlagich zaxirasi (FPU da / loyihaviy toshqin)",
                    "value": round(q_cap / q_need * 100, 0),
                    "unit": "%",
                    "ok": q_cap >= q_need,
                    "note": f"{q_cap:.0f} m³/s / {q_need:.0f} m³/s",
                }
            )
        if inflow is not None and q_need > 0:
            out.append(
                {
                    "name": "Kiruvchi sarf / loyihaviy toshqin",
                    "value": round(inflow / q_need * 100, 1),
                    "unit": "%",
                    "ok": inflow < 0.5 * q_need,
                    "note": f"{inflow:.0f} m³/s",
                }
            )
        if st.get("dam_type") == "concrete":
            try:
                p = parse(
                    dam_stability.FIELDS,
                    {
                        **catalog_site_values("dam_stability", st),
                        "headwater_m": up,
                        **({"tailwater_m": down} if down is not None else {}),
                    },
                )
                r = dam_stability.analyze(p)
                out.append(
                    {
                        "name": "To'g'on sirpanish zaxirasi (joriy sath, statik)",
                        "value": round(min(r["fs_s"], 9.99), 2),
                        "unit": "",
                        "ok": r["fs_s"] >= p["req_sliding"],
                        "note": f"ag'darilish {min(r['fs_o'], 9.99):.2f}, tovon kuchlanishi {r['s_toe']:.2f} MPa",
                    }
                )
            except ValueError:
                pass
    if down is not None:
        for key, label in (("powerhouse_floor_m", "Mashina zali poli"), ("switchyard_m", "OPU")):
            m = float(st[key]) - down
            out.append(
                {
                    "name": f"{label} — quyi byefdan balandlik (jonli)",
                    "value": round(m, 2),
                    "unit": "m",
                    "ok": m > 0.5,
                    "note": f"quyi byef {down:.2f} m",
                }
            )
    return out


def catalog_site_values(kind: str, st: dict) -> dict:
    from ges_sim import catalog

    return catalog.site_values(kind, st)


def _live(s: Sensor | None) -> float | None:
    if s is None or s.alarm == AlarmState.stale or s.last_value is None:
        return None
    return float(s.last_value)


def compute(db: Session, project: Project, overrides: dict | None = None) -> dict:
    """Joriy egizak holati (saqlamaydi). units: [{name, measured_mw, expected_mw, deviation_pct,
    efficiency, flow_m3s}], head_gross_m, head_net_m, status.
    overrides — «nima bo'lsa» sinovi: slot → qiymat (upstream_level, downstream_level, penstock_flow,
    unitN_power) jonli o'rniga ishlatiladi, hech narsa yozilmaydi."""
    ov = overrides or {}
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = _slots(db, project, sensors)
    params = model_params(db, project.id)

    def val(slot: str) -> float | None:
        if slot in ov and ov[slot] is not None:
            return float(ov[slot])
        return _live(slots.get(slot))

    up, down = val("upstream_level"), val("downstream_level")
    q_total = val("penstock_flow")
    unit_sensors = [slots.get(f"unit{i}_power") for i in (1, 2, 3, 4)]
    unit_sensors = [s for s in unit_sensors if s is not None]
    if params is None or up is None or down is None:
        return {
            "status": "insufficient",
            "reason": "model Pset_GES yoki byef sathlari (sensor) yo'q",
            "has_model": params is not None,
            "head_gross_m": (up - down) if up is not None and down is not None else None,
            "units": [],
            "safety": safety(db, project, slots, ov),
        }
    head_gross = up - down
    pen = params.get("penstocks") or []
    spec_p = (
        PenstockSpec(pen[0]["length_m"], pen[0]["diameter_m"], pen[0]["roughness_mm"])
        if pen
        else None
    )
    slot_of = {s.id: k for k, s in slots.items()}

    def unit_val(s: Sensor) -> float | None:
        return val(slot_of.get(s.id, ""))

    running = [s for s in unit_sensors if (unit_val(s) or 0) > RUN_THRESHOLD]
    units_out = []
    specs = params["units"]
    for i, s in enumerate(unit_sensors):
        spec_d = specs[min(i, len(specs) - 1)]
        spec = TurbineSpec(
            name=spec_d["name"],
            type=spec_d.get("type", "Francis"),
            rated_power_mw=spec_d["rated_power_mw"],
            rated_head_m=spec_d["rated_head_m"],
            rated_flow_m3s=spec_d["rated_flow_m3s"],
            max_efficiency=spec_d.get("max_efficiency", 0.92),
        )
        measured = unit_val(s)
        is_running = measured is not None and measured > RUN_THRESHOLD
        # Sarf: umumiy quvur sarfi ishlayotganlar orasida teng (alohida sarf sensori bo'lmasa)
        q = (q_total / len(running)) if (q_total is not None and running and is_running) else None
        if q is None and is_running:
            # sarf sensori yo'q — nominal FIK bilan quvvatdan teskari hisob (taxminiy)
            h_est = net_head(head_gross, spec.rated_flow_m3s, spec_p)
            q = measured * 1e6 / (spec.max_efficiency * RHO * G * max(h_est, 1e-3))
        h_net = net_head(head_gross, q if q else 0.0, spec_p) if spec_p else head_gross
        op = spec.output(q, h_net) if q else None  # hill-chart + generator + mexanik yo'qotishlar
        expected = op.electrical_mw if op else 0.0
        # o'lchangan umumiy FIK (klemma quvvati / gidravlik quvvat) — kutilgan eta_total bilan solishtiriladi
        eff = (measured * 1e6 / (RHO * G * q * h_net)) if (q and h_net > 0 and measured) else None
        dev = (
            ((measured - expected) / expected * 100)
            if (expected and measured is not None)
            else None
        )
        units_out.append(
            {
                "sensor_id": s.id,
                "name": s.name,
                "model_unit": spec.name,
                "running": is_running,
                "measured_mw": measured,
                "expected_mw": round(expected, 3),
                "deviation_pct": round(dev, 2) if dev is not None else None,
                "efficiency": round(min(eff, 1.2), 4) if eff is not None else None,
                "expected_efficiency": round(op.eta_total, 4) if op else None,
                "eta_turbine": round(op.eta_turbine, 4) if op else None,
                "eta_generator": round(op.eta_generator, 4) if op else None,
                "rough_zone": bool(op.rough_zone) if op else False,
                "head_factor": round(spec.head_factor(h_net), 4) if q else None,
                "flow_m3s": round(q, 3) if q else None,
                "head_net_m": round(h_net, 3),
            }
        )
    return {
        "status": "ok",
        "version_id": params.get("version_id"),
        "head_gross_m": round(head_gross, 3),
        "flow_total_m3s": q_total,
        "units": units_out,
        "expected_total_mw": round(sum(u["expected_mw"] for u in units_out), 3),
        "measured_total_mw": round(sum(u["measured_mw"] or 0 for u in units_out), 3),
        "safety": safety(db, project, slots, ov),
        "what_if": bool(ov),
    }


def twin_sensor(
    db: Session,
    project_id: int,
    key: str,
    name: str,
    unit: str,
    kind: str = "value",
    low=None,
    high=None,
) -> Sensor:
    s = db.query(Sensor).filter_by(project_id=project_id, key=key).first()
    if s is None:
        s = Sensor(
            project_id=project_id,
            key=key,
            name=name,
            kind=kind,
            unit=unit,
            protocol="twin",
            stale_after_s=600,
            low_alarm=low,
            high_alarm=high,
            priority="high",
        )
        db.add(s)
        db.flush()
    return s


def publish(db: Session, project: Project) -> dict:
    """Egizakni hisoblab, natijalarni virtual sensorlarga yozadi (og'ish alarmlari shu yerdan)."""
    state = compute(db, project)
    if state["status"] != "ok":
        return state
    items = []
    for u in state["units"]:
        base = f"TWIN.{u['sensor_id']}"
        twin_sensor(
            db, project.id, f"{base}.P_EXP", f"{u['name']} — kutilgan quvvat", "MW", "power"
        )
        # og'ish: ±10 % dan tashqarida — alarm (chegaralar sensorda o'zgartiriladi)
        twin_sensor(
            db,
            project.id,
            f"{base}.DEV",
            f"{u['name']} — model bilan og'ish",
            "%",
            "value",
            -10,
            10,
        )
        twin_sensor(db, project.id, f"{base}.EFF", f"{u['name']} — haqiqiy FIK", "%", "value")
        items.append({"key": f"{base}.P_EXP", "value": u["expected_mw"]})
        if u["deviation_pct"] is not None and u["running"]:
            items.append({"key": f"{base}.DEV", "value": u["deviation_pct"]})
        if u["efficiency"] is not None and u["running"]:
            items.append({"key": f"{base}.EFF", "value": round(u["efficiency"] * 100, 2)})
    db.commit()
    if items:
        live.ingest(db, project.id, items, source="twin")
    return state


def tick_all() -> int:
    """Fon: barcha loyihalar uchun egizak (agregat sensorlari bog'langan bo'lsa)."""
    from ..db import SessionLocal

    n = 0
    with SessionLocal() as db:
        for p in db.query(Project).all():
            try:
                if publish(db, p)["status"] == "ok":
                    n += 1
            except Exception:  # noqa: BLE001
                log.exception("twin: loyiha %s", p.id)
                db.rollback()
    return n


# ---------- Aktivlar (agregatlar) ----------


def unit_day_stats(db: Session, sensor: Sensor, day: datetime) -> dict:
    """Bir kun: ish soatlari (soatlik agregat + xom), ishga tushishlar, energiya (MWh)."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == sensor.id, Reading.ts >= start, Reading.ts < end)
        .order_by(Reading.ts)
        .all()
    )
    thr = max(RUN_THRESHOLD, 0.01 * (sensor.high_alarm or 0))
    if rows:
        run_s, starts, energy = 0.0, 0, 0.0
        prev_ts, prev_v = None, None
        for ts, v in rows:
            ts = live._aware(ts)
            if prev_ts is not None:
                dt = (ts - prev_ts).total_seconds()
                if prev_v > thr:
                    run_s += dt
                energy += prev_v * dt / 3600
                if prev_v <= thr < v:
                    starts += 1
            prev_ts, prev_v = ts, v
        scale = 0.001 if sensor.unit.lower().startswith("kw") else 1.0
        return {
            "run_hours": round(run_s / 3600, 2),
            "starts": starts,
            "energy_mwh": round(energy * scale, 3),
            "n": len(rows),
        }
    hourly = (
        db.query(ReadingHourly)
        .filter(
            ReadingHourly.sensor_id == sensor.id,
            ReadingHourly.hour >= start,
            ReadingHourly.hour < end,
        )
        .all()
    )
    scale = 0.001 if sensor.unit.lower().startswith("kw") else 1.0
    return {
        "run_hours": round(sum(1 for h in hourly if h.avg > thr), 2),
        "starts": sum(1 for a, b in zip(hourly, hourly[1:], strict=False) if a.avg <= thr < b.avg),
        "energy_mwh": round(sum(h.avg for h in hourly) * scale, 3),
        "n": sum(h.n for h in hourly),
    }


def rollup_units(db: Session, now: datetime | None = None) -> int:
    """Tugagan kunlar uchun agregat statistikasi (UnitDayStats) — power sensorlari."""
    now = now or datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    written = 0
    for s in db.query(Sensor).filter_by(kind="power").all():
        if s.protocol == "twin":
            continue
        last = (
            db.query(UnitDayStats.day)
            .filter_by(sensor_id=s.id)
            .order_by(UnitDayStats.day.desc())
            .first()
        )
        if last:
            day = live._aware(last[0]) + timedelta(days=1)
        else:
            first = db.query(Reading.ts).filter_by(sensor_id=s.id).order_by(Reading.ts).first()
            fh = (
                db.query(ReadingHourly.hour)
                .filter_by(sensor_id=s.id)
                .order_by(ReadingHourly.hour)
                .first()
            )
            cands = [live._aware(x[0]) for x in (first, fh) if x]
            if not cands:
                continue
            day = min(cands).replace(hour=0, minute=0, second=0, microsecond=0)
        while day < today:
            st = unit_day_stats(db, s, day)
            if st["n"]:
                db.add(
                    UnitDayStats(
                        sensor_id=s.id,
                        day=day,
                        **{k: st[k] for k in ("run_hours", "starts", "energy_mwh")},
                    )
                )
                written += 1
            day += timedelta(days=1)
    if written:
        db.commit()
    return written


def asset_status(db: Session, project: Project) -> list[dict]:
    """Aktivlar ro'yxati + hisoblangan holat (ish soatlari jami/oxirgi 30 kun, ishga tushishlar,
    texnik xizmatgacha qolgan soat)."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for a in db.query(Asset).filter_by(project_id=project.id).order_by(Asset.name).all():
        s = db.get(Sensor, a.power_sensor_id) if a.power_sensor_id else None
        total_h, total_starts, h30, e30 = 0.0, 0, 0.0, 0.0
        if s is not None:
            for r in db.query(UnitDayStats).filter_by(sensor_id=s.id).all():
                total_h += r.run_hours
                total_starts += r.starts
                if live._aware(r.day) >= today - timedelta(days=30):
                    h30 += r.run_hours
                    e30 += r.energy_mwh
            td = unit_day_stats(db, s, today)  # bugungi qism
            total_h += td["run_hours"]
            total_starts += td["starts"]
            h30 += td["run_hours"]
            e30 += td["energy_mwh"]
        total_h += a.base_run_hours
        since_maint = total_h - a.run_hours_at_maintenance
        remaining = (
            (a.maintenance_interval_hours - since_maint) if a.maintenance_interval_hours else None
        )
        status = "ok"
        if remaining is not None:
            status = (
                "overdue"
                if remaining < 0
                else "due"
                if remaining < 0.1 * a.maintenance_interval_hours
                else "ok"
            )
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "element_guid": a.element_guid,
                "power_sensor_id": a.power_sensor_id,
                "running": bool(
                    s and s.alarm != AlarmState.stale and (s.last_value or 0) > RUN_THRESHOLD
                ),
                "run_hours_total": round(total_h, 1),
                "starts_total": total_starts,
                "run_hours_30d": round(h30, 1),
                "energy_30d_mwh": round(e30, 1),
                "availability_30d": round(h30 / (30 * 24) * 100, 1),
                "maintenance_interval_hours": a.maintenance_interval_hours,
                "last_maintenance_at": live._aware(a.last_maintenance_at).isoformat()
                if a.last_maintenance_at
                else None,
                "hours_since_maintenance": round(since_maint, 1),
                "hours_to_maintenance": round(remaining, 1) if remaining is not None else None,
                "status": status,
                "notes": a.notes,
            }
        )
    return out


# ---------- Vaqt mashinasi ----------


def snapshot(db: Session, project_id: int, at: datetime) -> list[dict]:
    """Berilgan vaqtdagi (yoki undan oldingi oxirgi) sensor qiymatlari; xom yo'q bo'lsa soatlik."""
    out = []
    for s in db.query(Sensor).filter_by(project_id=project_id, enabled=True).all():
        r = (
            db.query(Reading.ts, Reading.value)
            .filter(
                Reading.sensor_id == s.id, Reading.ts <= at, Reading.ts >= at - timedelta(hours=6)
            )
            .order_by(Reading.ts.desc())
            .first()
        )
        ts, val = (live._aware(r[0]), r[1]) if r else (None, None)
        if r is None:
            h = (
                db.query(ReadingHourly)
                .filter(ReadingHourly.sensor_id == s.id, ReadingHourly.hour <= floor_hour(at))
                .order_by(ReadingHourly.hour.desc())
                .first()
            )
            if h and live._aware(h.hour) >= floor_hour(at) - timedelta(hours=6):
                ts, val = live._aware(h.hour), h.avg
        alarm = "stale"
        if val is not None:
            alarm = live.evaluate_alarm(s, val).value
        out.append(
            {
                "sensor_id": s.id,
                "key": s.key,
                "value": val,
                "ts": ts.isoformat() if ts else None,
                "alarm": alarm,
                "element_guid": s.element_guid,
                "unit": s.unit,
            }
        )
    return out


def optimal_dispatch(
    db: Session, project: Project, target_mw: float | None = None, overrides: dict | None = None
) -> dict:
    """Jonli holatdan optimal yuk taqsimoti: model agregatlari (Pset_GES_Turbine), brutto napor, joriy umumiy
    quvvat (yoki berilgan target) → minimal sarf bilan taqsimot; joriy sarfga nisbatan tejash."""
    from ges_sim import dispatch as dsp

    state = compute(db, project, overrides)
    if state.get("status") != "ok":
        return {"status": "insufficient", "reason": state.get("reason")}
    params = model_params(db, project.id) or {}
    specs = [
        TurbineSpec(
            name=u["name"],
            type=u.get("type", "Francis"),
            rated_power_mw=u["rated_power_mw"],
            rated_head_m=u["rated_head_m"],
            rated_flow_m3s=u["rated_flow_m3s"],
            max_efficiency=u.get("max_efficiency", 0.92),
        )
        for u in params.get("units", [])
    ]
    if not specs:
        return {"status": "insufficient", "reason": "modelda agregatlar yo'q"}
    head = float(state["head_gross_m"])
    target = float(target_mw) if target_mw is not None else float(state["measured_total_mw"] or 0)
    pen = params.get("penstocks") or []
    spec_p = (
        PenstockSpec(pen[0]["length_m"], pen[0]["diameter_m"], pen[0]["roughness_mm"])
        if pen
        else None
    )
    if target <= 0:
        return {"status": "idle", "target_mw": target, "units": []}
    try:
        res = dsp.optimize(specs, target, head, spec_p)
    except ValueError as e:
        return {"status": "infeasible", "reason": str(e), "target_mw": target}
    current_q = state.get("flow_total_m3s")
    if current_q is None:
        current_q = sum((u.get("flow_m3s") or 0) for u in state["units"]) or None
    saving = round((1 - res["total_flow"] / current_q) * 100, 2) if current_q else None
    return {
        "status": "ok",
        "target_mw": target,
        "head_gross_m": head,
        "units": res["units"],
        "total_flow_m3s": res["total_flow"],
        "current_flow_m3s": current_q,
        "saving_pct": saving,
        "units_on": res["units_on"],
    }


def flood_forecast(db: Session, project: Project, rain: dict) -> dict:
    """Toshqin prognozi jonli holatdan: maydon pasporti (havza, CN, ombor, suv tashlagich) + jonli sath/sarf +
    kutilayotgan yog'in (mm, soat, AMC, qor, GLOF) → yog'in→oqim→ombor (ges_sim.rainfall). Gerbdan oshsa —
    oldindan sath tushirish tavsiyasi (qaysi sathda xavfsiz)."""
    from ges_sim import catalog, site

    st = {**site.defaults(), **(project.site or {})}
    params = catalog.site_values("rainfall", st)
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = _slots(db, project, sensors)
    up, inflow, q_pen = (
        _live(slots.get("upstream_level")),
        _live(slots.get("inflow")),
        _live(slots.get("penstock_flow")),
    )
    live_used = {}
    if up is not None:
        params["initial_level_m"] = up
        live_used["upstream_level"] = up
    if inflow is not None:
        params["base_m3s"] = inflow
        live_used["inflow"] = inflow
    if q_pen is not None:
        params["turbine_m3s"] = q_pen
        live_used["penstock_flow"] = q_pen
    for k in (
        "rain_mm",
        "rain_hours",
        "amc",
        "pattern",
        "snowmelt",
        "air_temp",
        "glof",
        "lake_mcm",
        "gate_opening",
    ):
        if rain.get(k) is not None:
            params[k] = rain[k]
    params["route"] = True
    res = catalog.run("rainfall", params)
    s = res["summary"]
    out = {
        "status": "ok",
        "live": live_used,
        "site_filled": bool(project.site),
        "rain": {k: params.get(k) for k in ("rain_mm", "rain_hours", "amc", "snowmelt", "glof")},
        "summary": s,
        "series": {k: res["series"].get(k) for k in ("t", "inflow", "level", "outflow", "overtop")},
        "recommendation": None,
    }
    if s.get("overtopped"):
        # Oldindan sath tushirish: qaysi boshlang'ich sathda gerbdan oshmaydi (0.5 m qadam, 10 m gacha)
        lvl0 = float(params["initial_level_m"])
        safe = None
        for d in range(1, 21):
            p2 = dict(params, initial_level_m=lvl0 - 0.5 * d, gate_opening=1.0)
            r2 = catalog.run("rainfall", p2)["summary"]
            if not r2.get("overtopped"):
                safe = lvl0 - 0.5 * d
                break
        t_over = s.get("overtop_start_h")
        out["recommendation"] = {
            "action": "pre_release",
            "safe_level_m": safe,
            "lower_by_m": round(lvl0 - safe, 1) if safe is not None else None,
            "hours_to_overtop": t_over,
            "text": (
                f"Gerbdan oshish {t_over} soatdan keyin kutiladi — darvozalarni to'liq oching va sathni "
                f"{safe:.1f} m ga ({lvl0 - safe:.1f} m ga) oldindan tushiring"
                if safe is not None
                else f"Gerbdan oshish {t_over} soatdan keyin — sath tushirish yetarli emas, favqulodda rejim (aholini ogohlantirish)"
            ),
        }
    elif s.get("freeboard_m") is not None and s["freeboard_m"] < 1.0:
        out["recommendation"] = {
            "action": "watch",
            "text": f"Zaxira {s['freeboard_m']:.2f} m — darvozalar tayyor, sathni kuzating",
        }
    return out
