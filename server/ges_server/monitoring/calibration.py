"""Model kalibrovkasi (I1): egizak parametrlarini o'lchangan tarixga moslashtirish, qoldiqni kuzatish
va drift aniqlanganda qayta kalibrovka taklifi.

Muammo: `twin.compute` model parametrlarini (quvur g'adir-budurligi, turbina maksimal FIK i) IFC
pasportidan olingan holda ishlatadi. Ular o'lchangan ma'lumotga moslashtirilmasa, «og'ish %» ikki xil
narsani qo'shib yuboradi: haqiqiy degradatsiya va kalibrovkalanmagan model xatosi.

Yechim: tarixiy soatlik ma'lumot ustida eng kichik kvadratlar — qoldiq
    r_i = P_measured,i − P_model,i(θ)
ni minimallashtiruvchi θ qidiriladi. Parametrlar fizik chegarada saqlanadi va identifikatsiya
qilinadigan qismi bilan cheklanadi:

  * `penstock_roughness_mm` — quvur g'adir-budurligi (Darcy–Weisbach; po'lat 0.05–0.15,
    temir-beton 0.3–1.0; eskirgan quvurda 1–3). Mahalliy yo'qotish koeffitsienti bilan birga
    identifikatsiya qilinmaydi (ikkalasi ham v² ga proporsional), shuning uchun faqat shu.
  * `max_efficiency` — agregat gidravlik FIK cho'qqisi (IEC 60193 qabul sinovidagi kabi
    «shartli» qiymat; 0.80–0.96 oralig'ida).

Usul: koordinata bo'yicha tushish + oltin kesim qidiruvi (tashqi kutubxonasiz, deterministik).
Har qadamda RMSE hisoblanadi; yaxshilanish 0.1 % dan kam bo'lsa to'xtaydi.

Drift: kalibrovkadan keyingi qoldiq o'rtachasi (bias) kalibrovka paytidagi RMSE ning `DRIFT_K`
barobaridan oshsa — model eskirgan deb belgilanadi va qayta kalibrovka taklif qilinadi
(ISO 13374 nuqtayi nazaridan bu DM/SD darajasidagi «model sifati» belgisi).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..orm import CalibrationRun, Project, ReadingHourly, Sensor
from . import twin

# Parametr chegaralari (fizik ma'noli oraliq)
BOUNDS = {
    "penstock_roughness_mm": (0.01, 5.0),
    "max_efficiency": (0.80, 0.96),
}
MIN_POINTS = 24  # kamida bir sutkalik ishlagan soat
DRIFT_K = 2.0  # bias > DRIFT_K × RMSE → drift
IDENT_MIN_GAIN = 0.02  # parametrni erkin qoldirish RMSE ni kamida 2 % yaxshilashi kerak
GOLDEN = (math.sqrt(5) - 1) / 2


def _aware(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=timezone.utc))


# --------------------------------------------------------------------------- ma'lumot


def _hourly_map(db: Session, sensor: Sensor | None, since: datetime) -> dict[datetime, float]:
    if sensor is None:
        return {}
    rows = (
        db.query(ReadingHourly.hour, ReadingHourly.avg)
        .filter(ReadingHourly.sensor_id == sensor.id, ReadingHourly.hour >= since)
        .all()
    )
    return {_aware(h): float(v) for h, v in rows}


def samples(db: Session, project: Project, days: int = 30) -> list[dict]:
    """Kalibrovka namunalari: har soat uchun {up, down, flow, powers{sensor_id: MW}}.
    Faqat ikkala byef sathi va kamida bitta ishlayotgan agregat bo'lgan soatlar olinadi."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    up = _hourly_map(db, slots.get("upstream_level"), since)
    down = _hourly_map(db, slots.get("downstream_level"), since)
    flow = _hourly_map(db, slots.get("penstock_flow"), since)
    units = {i: slots.get(f"unit{i}_power") for i in (1, 2, 3, 4)}
    units = {i: s for i, s in units.items() if s is not None}
    power = {i: _hourly_map(db, s, since) for i, s in units.items()}
    out = []
    for hour in sorted(set(up) & set(down)):
        powers = {i: p[hour] for i, p in power.items() if hour in p and p[hour] > twin.RUN_THRESHOLD}
        if not powers:
            continue
        out.append(
            {
                "hour": hour,
                "up": up[hour],
                "down": down[hour],
                "flow": flow.get(hour),
                "powers": powers,
                "sensor_ids": {i: units[i].id for i in powers},
            }
        )
    return out


# --------------------------------------------------------------------------- model


def _unit_specs(params: dict) -> list[dict]:
    return params.get("units") or []


def predict(sample: dict, params: dict, theta: dict) -> dict[int, float]:
    """Berilgan parametrlar bilan har agregat uchun kutilgan quvvat (MW).
    `theta`: {"penstock_roughness_mm": …, "eff": {unit_index: max_efficiency}}"""
    from ges_sim.penstock import PenstockSpec, net_head
    from ges_sim.turbine import TurbineSpec

    pen = (params.get("penstocks") or [None])[0]
    spec_p = (
        PenstockSpec(pen["length_m"], pen["diameter_m"], theta["penstock_roughness_mm"])
        if pen
        else None
    )
    head_gross = sample["up"] - sample["down"]
    specs = _unit_specs(params)
    running = sorted(sample["powers"])
    out: dict[int, float] = {}
    for idx in running:
        spec_d = specs[min(idx - 1, len(specs) - 1)]
        eff = theta["eff"].get(idx, spec_d.get("max_efficiency", 0.92))
        spec = TurbineSpec(
            name=spec_d["name"],
            type=spec_d.get("type", "Francis"),
            rated_power_mw=spec_d["rated_power_mw"],
            rated_head_m=spec_d["rated_head_m"],
            rated_flow_m3s=spec_d["rated_flow_m3s"],
            max_efficiency=eff,
        )
        measured = sample["powers"][idx]
        q = (sample["flow"] / len(running)) if sample["flow"] else None
        if q is None:  # sarf sensori yo'q — quvvatdan teskari baho (twin bilan bir xil qoida)
            h_est = net_head(head_gross, spec.rated_flow_m3s, spec_p)
            q = measured * 1e6 / (eff * twin.RHO * twin.G * max(h_est, 1e-3))
        h_net = net_head(head_gross, q, spec_p) if spec_p else head_gross
        op = spec.output(q, h_net)
        out[idx] = op.electrical_mw if op else 0.0
    return out


def rmse(rows: list[dict], params: dict, theta: dict) -> float:
    """Qoldiqning o'rtacha kvadratik ildizi (MW) — barcha namuna va ishlayotgan agregatlar bo'yicha."""
    n, acc = 0, 0.0
    for s in rows:
        pred = predict(s, params, theta)
        for idx, p in pred.items():
            acc += (s["powers"][idx] - p) ** 2
            n += 1
    return math.sqrt(acc / n) if n else float("inf")


def bias(rows: list[dict], params: dict, theta: dict) -> float:
    """O'rtacha qoldiq (MW): musbat — o'lchov modeldan katta."""
    n, acc = 0, 0.0
    for s in rows:
        pred = predict(s, params, theta)
        for idx, p in pred.items():
            acc += s["powers"][idx] - p
            n += 1
    return acc / n if n else 0.0


# --------------------------------------------------------------------------- optimallashtirish


def _golden(f, lo: float, hi: float, tol: float, iters: int = 40) -> float:
    """Bir o'lchovli minimum (oltin kesim) — f bir modali deb qaraladi, chegara saqlanadi."""
    a, b = lo, hi
    c = b - GOLDEN * (b - a)
    d = a + GOLDEN * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if b - a < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - GOLDEN * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + GOLDEN * (b - a)
            fd = f(d)
    return (a + b) / 2


def _optimize(rows: list[dict], params: dict, theta0: dict, targets: tuple[str, ...]) -> dict:
    """Koordinata bo'yicha tushish: g'adir-budurlik → har agregat FIK i, 3 marta takrorlanadi yoki
    yaxshilanish 0.1 % dan kam bo'lganda to'xtaydi. `targets` ga kirmagan parametr o'zgarmaydi."""
    theta = {"penstock_roughness_mm": theta0["penstock_roughness_mm"], "eff": dict(theta0["eff"])}
    best = rmse(rows, params, theta)
    for _ in range(3):
        start = best
        if "penstock_roughness_mm" in targets and (params.get("penstocks") or []):
            lo, hi = BOUNDS["penstock_roughness_mm"]

            def f_rough(x: float, th=theta) -> float:
                return rmse(rows, params, {**th, "penstock_roughness_mm": x})

            theta["penstock_roughness_mm"] = round(_golden(f_rough, lo, hi, 1e-3), 4)
        if "max_efficiency" in targets:
            for idx in sorted({i for s in rows for i in s["powers"]}):
                lo, hi = BOUNDS["max_efficiency"]

                def f_eff(x: float, i=idx, th=theta) -> float:
                    return rmse(rows, params, {**th, "eff": {**th["eff"], i: x}})

                theta["eff"][idx] = round(_golden(f_eff, lo, hi, 1e-4), 4)
        best = rmse(rows, params, theta)
        if start - best < max(start * 0.001, 1e-9):
            break
    return theta


def fit(rows: list[dict], params: dict, theta0: dict, targets: tuple[str, ...]) -> tuple[dict, dict]:
    """Moslashtirish va **identifikatsiya tekshiruvi**.

    Quvvat o'lchovi ba'zi parametrlarni ajrata olmaydi: masalan, qisqa quvurda g'adir-budurlikning
    quvvatga ta'siri FIK dagi kichik o'zgarish bilan to'liq qoplanadi (kollinearlik). Bunday holda
    optimizator parametrni chegaraga surib yuboradi va «kalibrovkalangan» soxta qiymat hosil bo'ladi.

    Shuning uchun har parametr uchun profil tekshiruvi bajariladi: parametr dastlabki (pasport)
    qiymatida qotiriladi, qolganlari qaytadan moslashtiriladi va RMSE solishtiriladi. Agar erkin
    qoldirish RMSE ni `IDENT_MIN_GAIN` dan kam yaxshilasa — parametr shu ma'lumotdan aniqlanmaydi va
    pasport qiymatida qoldiriladi (natijada `diagnostics` da sababi yoziladi)."""
    theta = _optimize(rows, params, theta0, targets)
    diag: dict[str, dict] = {}
    for name in targets:
        restricted = tuple(t for t in targets if t != name)
        th_r = _optimize(rows, params, theta0, restricted)
        r_full, r_restr = rmse(rows, params, theta), rmse(rows, params, th_r)
        gain = (r_restr - r_full) / r_restr if r_restr > 1e-12 else 0.0
        ok = gain >= IDENT_MIN_GAIN
        diag[name] = {
            "gain": round(gain, 4),
            "identifiable": ok,
            "note": ""
            if ok
            else "ma'lumotdan ajratilmaydi (boshqa parametr qoplaydi) — pasport qiymati saqlandi",
        }
        if not ok:
            theta = th_r  # parametr pasport qiymatida qoladi, qolganlari shunga moslashtiriladi
    return theta, diag


# --------------------------------------------------------------------------- saqlash va qo'llash


def current(project: Project) -> dict:
    """Loyihaga qo'llangan kalibrovka (bo'lmasa bo'sh)."""
    return dict(project.calibration or {})


def theta_from(project: Project, params: dict) -> dict:
    """Joriy θ: qo'llangan kalibrovka bo'lsa undan, aks holda IFC pasportidan."""
    cal = current(project)
    pen = (params.get("penstocks") or [None])[0]
    rough = cal.get("penstock_roughness_mm") or (pen["roughness_mm"] if pen else 0.1)
    specs = _unit_specs(params)
    eff = {}
    cal_eff = {int(k): v for k, v in (cal.get("eff") or {}).items()}
    for i in range(1, len(specs) + 1):
        eff[i] = cal_eff.get(i, specs[min(i - 1, len(specs) - 1)].get("max_efficiency", 0.92))
    return {"penstock_roughness_mm": float(rough), "eff": eff}


def run(
    db: Session,
    project: Project,
    user_id: int | None,
    days: int = 30,
    targets: tuple[str, ...] = ("penstock_roughness_mm", "max_efficiency"),
    apply: bool = False,
) -> CalibrationRun:
    """Kalibrovkani bajaradi va natijani `CalibrationRun` sifatida yozadi. `apply=True` bo'lsa
    natija loyihaga qo'llanadi (egizak shu parametrlar bilan hisoblaydi). Commit chaqiruvchida."""
    params = twin.model_params(db, project.id)
    rows = samples(db, project, days)
    now = datetime.now(timezone.utc)
    rec = CalibrationRun(
        project_id=project.id,
        created_by=user_id,
        created_at=now,
        window_from=now - timedelta(days=days),
        window_to=now,
        n_points=sum(len(s["powers"]) for s in rows),
        targets=list(targets),
        status="ok",
        applied=False,
    )
    if params is None:
        rec.status = "insufficient"
        rec.note = "Model parametrlari yo'q (Pset_GES_* bilan versiya nashr etilmagan)"
    elif rec.n_points < MIN_POINTS:
        rec.status = "insufficient"
        rec.note = f"Ma'lumot yetarli emas: {rec.n_points} nuqta (kamida {MIN_POINTS})"
    else:
        before = theta_from(project, params)
        rec.params_before = {"penstock_roughness_mm": before["penstock_roughness_mm"], "eff": before["eff"]}
        rec.rmse_before = round(rmse(rows, params, before), 4)
        after, diag = fit(rows, params, before, targets)
        rec.diagnostics = diag
        rec.params_after = {"penstock_roughness_mm": after["penstock_roughness_mm"], "eff": after["eff"]}
        rec.rmse_after = round(rmse(rows, params, after), 4)
        rec.bias_after = round(bias(rows, params, after), 4)
        rec.improvement_pct = (
            round((rec.rmse_before - rec.rmse_after) / rec.rmse_before * 100, 2)
            if rec.rmse_before
            else 0.0
        )
        skipped = [k for k, v in diag.items() if not v["identifiable"]]
        rec.note = (
            f"RMSE {rec.rmse_before:.3f} → {rec.rmse_after:.3f} MW ({rec.improvement_pct:+.1f} %)"
            + (f"; aniqlanmadi: {', '.join(skipped)}" if skipped else "")
        )
    db.add(rec)
    db.flush()
    if apply and rec.status == "ok":
        apply_run(db, project, rec)
    return rec


def apply_run(db: Session, project: Project, rec: CalibrationRun) -> None:
    """Kalibrovka natijasini loyihaga qo'llash (egizak shundan keyin shu parametrlar bilan hisoblaydi)."""
    if rec.status != "ok" or not rec.params_after:
        raise ValueError("Faqat muvaffaqiyatli kalibrovka qo'llanadi")
    project.calibration = {
        **rec.params_after,
        "run_id": rec.id,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "rmse": rec.rmse_after,
        "bias": rec.bias_after,
    }
    rec.applied = True
    db.flush()


def revert(db: Session, project: Project) -> None:
    """Kalibrovkani bekor qilish — model yana IFC pasporti qiymatlari bilan ishlaydi."""
    project.calibration = {}
    db.flush()


# --------------------------------------------------------------------------- qoldiq va drift


def residuals(db: Session, project: Project, days: int = 7) -> dict:
    """Oxirgi davr qoldig'i: RMSE, bias va drift holati.

    Holat: `uncalibrated` — kalibrovka qo'llanmagan; `insufficient` — ma'lumot kam;
    `drifted` — bias kalibrovka RMSE sining DRIFT_K barobaridan katta; `ok` — model amalda."""
    cal = current(project)
    params = twin.model_params(db, project.id)
    if params is None:
        return {"status": "insufficient", "reason": "model parametrlari yo'q"}
    rows = samples(db, project, days)
    n = sum(len(s["powers"]) for s in rows)
    if n < MIN_POINTS:
        return {"status": "insufficient", "n_points": n, "calibrated": bool(cal)}
    theta = theta_from(project, params)
    r, b = rmse(rows, params, theta), bias(rows, params, theta)
    base = cal.get("rmse")
    drifted = bool(base) and abs(b) > DRIFT_K * float(base)
    return {
        "status": "drifted" if drifted else ("ok" if cal else "uncalibrated"),
        "calibrated": bool(cal),
        "n_points": n,
        "days": days,
        "rmse_mw": round(r, 4),
        "bias_mw": round(b, 4),
        "calibration_rmse_mw": base,
        "run_id": cal.get("run_id"),
        "applied_at": cal.get("applied_at"),
        "advice": (
            "Qayta kalibrovka tavsiya etiladi — qoldiq siljigan (drift)"
            if drifted
            else ("Model kalibrovkalanmagan — og'ish % model xatosini ham o'z ichiga oladi" if not cal else "")
        ),
    }


def tick_drift(db: Session) -> int:
    """Fon (soatlik): kalibrovkalangan loyihalarda drift tekshiruvi; topilsa muhandislarga
    bildirishnoma (har drift uchun bir marta — `calibration.drift_notified_at`)."""
    from .. import notifications
    from ..orm import Role

    n = 0
    for project in db.query(Project).all():
        cal = current(project)
        if not cal:
            continue
        res = residuals(db, project, days=7)
        if res.get("status") != "drifted":
            if cal.pop("drift_notified_at", None) is not None:
                project.calibration = cal  # drift tugadi — belgini olib tashlaymiz
            continue
        if cal.get("drift_notified_at"):
            continue
        project.calibration = {**cal, "drift_notified_at": datetime.now(timezone.utc).isoformat()}
        notifications.push(
            db,
            notifications.member_ids(db, project.id, Role.engineer),
            "twin",
            f"Egizak modeli siljidi: {project.name}",
            f"qoldiq {res['bias_mw']:+.2f} MW (kalibrovka RMSE {res['calibration_rmse_mw']} MW) — qayta kalibrovka kerak",
            f"/projects/{project.id}/dashboard",
        )
        n += 1
    if n:
        db.commit()
    return n
