"""HA — Health Assessment (ISO 13374-1 §5.5): holat belgilaridan sog'liq bahosi va tashxis.

Sog'liq indeksi 100 dan boshlanib har bir aniqlangan holat uchun ball ayiriladi (GE APM Health /
Voith OnCare uslubi). Tashqi tizim (Bently Nevada, SKF, OnCare) HA darajasidagi bahosini bersa,
yakuniy indeks ikkalasining eng pastiga tenglashtiriladi — tashqi tizim Sath ko'rmaydigan kanallarni
(orbita, qisman razryad, moy tahlili) ko'rishi mumkin, shuning uchun xavfsiz tomon tanlanadi.

Tashxis qismlari: kavitatsiya (Toma soni), FIK og'ishi (egizak), transformator issiq nuqtasi
(IEC 60076-7), podshipnik nuqsoni (spektr).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...orm import Asset, Project
from .. import twin

H_VAP = 0.24  # suv bug' bosimi napori, m (20 °C)

# Holat → ball ayirmasi (kanal bo'yicha)
DEDUCT = {
    "vibration": {"alert": 30, "alarm": 60, "normal": 0},  # C / D zona
    "bearing_temp": {"alert": 15, "alarm": 40, "normal": 0},
    "shaft_vibration": {"alert": 15, "alarm": 35, "normal": 0},
    "bearing_defect": {"alert": 15, "alarm": 35, "normal": 0},
    "partial_discharge": {"alert": 10, "alarm": 25, "normal": 0},
    "air_gap": {"alert": 10, "alarm": 30, "normal": 0},
    "oil_water": {"alert": 8, "alarm": 20, "normal": 0},
}
EXTERNAL_DEDUCT = {"alert": 15, "alarm": 40, "normal": 0, "unknown": 0}
ANOMALY_DEDUCT = 10
STALE_DEDUCT = 5
ZONE_B_DEDUCT = 8  # B zona — ogohlantirish emas, lekin yangi mashina darajasidan yuqori


def thoma_critical(turbine_type: str, ns: float) -> float:
    """Kritik Toma soni — yagona manba `ges_sim.cavitation.sigma_critical` (formulalar va manbalar
    o'sha modulda; Blender addoni ham shu faylning nusxasini ishlatadi)."""
    from ges_sim.cavitation import sigma_critical

    return sigma_critical(turbine_type, ns)


def specific_speed(n_rpm: float, p_kw: float, h_m: float) -> float:
    """n_s = n·√P/H^1.25 [m-kVt] — `ges_sim.cavitation.specific_speed`."""
    from ges_sim.cavitation import specific_speed as _ns

    return _ns(n_rpm, max(p_kw, 0.0), max(h_m, 0.1))


def cavitation(acq: dict) -> dict | None:
    """Toma soni: σ_plant = (H_atm − H_vap − H_s)/H_net, H_s = runner_elev − quyi byef sathi."""
    cfg = acq["config"]
    unit = acq["unit"]
    tail = acq["downstream_level"]
    runner = cfg.get("runner_elev_m")
    rpm = float(cfg.get("rated_speed_rpm") or 0)
    if not (unit and tail is not None and runner is not None and rpm > 0 and unit.get("head_net_m")):
        return None
    h_net = float(unit["head_net_m"])
    elev = float(runner)
    hs = elev - tail
    h_atm = 10.33 - elev / 900.0
    sigma = (h_atm - H_VAP - hs) / h_net
    p_kw = float(unit.get("measured_mw") or unit.get("expected_mw") or 0) * 1000
    ns = specific_speed(rpm, p_kw, h_net)
    sc = thoma_critical(str(cfg.get("turbine_type") or "Francis"), ns)
    return {
        "sigma_plant": round(sigma, 4),
        "sigma_critical": round(sc, 4),
        "ns": round(ns, 1),
        "suction_head_m": round(hs, 2),
        "margin": round(sigma - sc, 4),
    }


def electrical(acq: dict) -> dict | None:
    """Transformator/generator issiqlik holati (IEC 60076-7): yuk koeffitsienti K, yuqori moy va issiq
    nuqta harorati, nisbiy qarish tezligi."""
    cfg = acq["config"]
    rated_mva = float(cfg.get("rated_mva") or 0)
    pw = acq["power"]
    if rated_mva <= 0 or pw is None:
        return None
    from ges_sim import transformer as trf

    cosphi = float(cfg.get("cos_phi") or 0.9)
    amb = float(cfg.get("ambient_c") or 30)
    k = (pw / cosphi) / rated_mva
    x, y, dor, dhr = trf.COOLING[str(cfg.get("cooling") or "ONAF")][:4]
    theta_o = amb + dor * ((1 + 6 * k**2) / 7) ** x
    theta_h = theta_o + dhr * k**y
    return {
        "load_factor": round(k, 3),
        "top_oil_c": round(theta_o, 1),
        "hot_spot_c": round(theta_h, 1),
        "aging_rate": round(trf.aging_rate(theta_h, "upgraded"), 2),
    }


def efficiency(acq: dict, feats: dict) -> dict | None:
    unit = acq["unit"]
    if not unit:
        return None
    return {
        "measured": unit.get("efficiency"),
        "expected": unit.get("expected_efficiency"),
        "deviation_pct": unit.get("deviation_pct"),
        "trend_pct_per_month": feats["efficiency_trend_pct_per_month"],
        "running": unit.get("running"),
    }


def level_for(score: int) -> str:
    return (
        "yaxshi" if score >= 80 else "qoniqarli" if score >= 60 else "yomon" if score >= 40 else "kritik"
    )


def assess(db: Session, project: Project, a: Asset, acq: dict, feats: dict, state: dict) -> dict:
    """HA natijasi: ichki ball, tashqi baho, yakuniy indeks va tashxis bloklari."""
    score = 100.0
    reasons: list[str] = []
    for name, item in state["items"].items():
        if name.startswith("external:"):
            score -= EXTERNAL_DEDUCT.get(item["state"], 0)
            if item["state"] in ("alert", "alarm"):
                reasons.append(item["reason"])
            continue
        table = DEDUCT.get(name)
        if table is None:
            continue
        score -= table.get(item["state"], 0)
        if name == "vibration" and item.get("zone") == "B":
            score -= ZONE_B_DEDUCT
        if item["state"] in ("alert", "alarm"):
            reasons.append(item["reason"])
        if item.get("anomaly"):
            score -= ANOMALY_DEDUCT
            f = feats["scalars"].get(name)
            reasons.append(f"{item.get('label', name)} anomaliyasi (z = {f['z']})" if f else f"{name} anomaliyasi")

    eff = efficiency(acq, feats)
    if eff and eff["deviation_pct"] is not None and eff.get("running"):
        dev = eff["deviation_pct"]
        if dev < -10:
            score -= 30
            reasons.append(f"quvvat model kutganidan {abs(dev):.1f} % kam (FIK pasaygan)")
        elif dev < -5:
            score -= 15
            reasons.append(f"quvvat model kutganidan {abs(dev):.1f} % kam")
    if eff and eff["trend_pct_per_month"] is not None and eff["trend_pct_per_month"] < -0.5:
        reasons.append(f"FIK trendi: oyiga {abs(eff['trend_pct_per_month']):.2f} % pasaymoqda")

    cav = cavitation(acq)
    if cav and cav["sigma_critical"] > 0:
        if cav["sigma_plant"] < cav["sigma_critical"]:
            score -= 20
            reasons.append(
                f"kavitatsiya xavfi: σ_plant {cav['sigma_plant']:.3f} < σ_kr {cav['sigma_critical']:.3f}"
                " (quyi byef past / napor katta)"
            )
        elif cav["sigma_plant"] < 1.15 * cav["sigma_critical"]:
            reasons.append(
                f"kavitatsiya zaxirasi kam: σ {cav['sigma_plant']:.3f} / σ_kr {cav['sigma_critical']:.3f}"
            )

    elec = electrical(acq)
    if elec:
        if elec["load_factor"] > 1.5 or elec["hot_spot_c"] > 140:
            score -= 40
            reasons.append(
                f"transformator: K = {elec['load_factor']:.2f}, issiq nuqta {elec['hot_spot_c']:.0f} °C — favqulodda chegara"
            )
        elif elec["load_factor"] > 1.0 or elec["hot_spot_c"] > 120:
            score -= 15
            reasons.append(
                f"transformator ortiqcha yuk K = {elec['load_factor']:.2f}, issiq nuqta "
                f"{elec['hot_spot_c']:.0f} °C (qarish {elec['aging_rate']}×)"
            )

    for name in state["stale_channels"]:
        score -= STALE_DEDUCT
        reasons.append(f"{name}: aloqa yo'q")

    internal = max(min(round(score), 100), 0)
    ext_scores = [
        e["health_score"] for e in state["external"] if e["block"] in ("HA", "PA") and e["health_score"] is not None
    ]
    external = round(min(ext_scores)) if ext_scores else None
    final = min(internal, external) if external is not None else internal
    return {
        "score": final,
        "internal_score": internal,
        "external_score": external,
        "level": level_for(final),
        "reasons": reasons,
        "efficiency": eff,
        "cavitation": cav,
        "electrical": elec,
    }


def render(a: Asset, acq: dict, feats: dict, state: dict, health: dict, prog: dict, advice: dict) -> dict:
    """Bloklar natijasini bitta javobga yig'ish (web interfeysi kutgan tuzilma + ISO 13374 bloklari)."""
    vib = feats["scalars"].get("vibration")
    if vib is not None:
        item = state["items"].get("vibration", {})
        vib = {
            **vib,
            "zone": item.get("zone"),
            "zone_note": item.get("zone_note"),
            "days_to_c": prog["days"].get("vibration_c"),
            "days_to_d": prog["days"].get("vibration_d"),
        }
    temp = feats["scalars"].get("bearing_temp")
    if temp is not None:
        item = state["items"].get("bearing_temp", {})
        temp = {
            **temp,
            "warn": item.get("warn"),
            "alarm": item.get("alarm"),
            "days_to_alarm": prog["days"].get("bearing_temp_alarm"),
        }
    return {
        "asset_id": a.id,
        "name": a.name,
        "element_guid": a.element_guid,
        "kks_code": a.kks_code,
        "score": health["score"],
        "level": health["level"],
        "vibration": vib,
        "bearing_temp": temp,
        "efficiency": health["efficiency"],
        "cavitation": health["cavitation"],
        "electrical": health["electrical"],
        "problems": advice["problems"],
        "tips": advice["tips"],
        "machine_group": acq["machine_group"],
        # H3 — ISO 13374 bloklari
        "state": state["overall"],
        "states": state["items"],
        "external": state["external"],
        "internal_score": health["internal_score"],
        "external_score": health["external_score"],
        "prognosis": prog,
        "channels": {k: v for k, v in feats["scalars"].items() if v is not None},
        "spectra": [
            {k: (v.isoformat() if k == "ts" else v) for k, v in sp.items()} for sp in feats["spectra"]
        ],
        "blocks": {
            "DA": {"channels": [k for k, v in acq["channels"].items() if v], "spectra": len(acq["spectra"])},
            "DM": {"features": [k for k, v in feats["scalars"].items() if v], "spectra": len(feats["spectra"])},
            "SD": {"state": state["overall"], "items": list(state["items"])},
            "HA": {"score": health["score"], "internal": health["internal_score"], "external": health["external_score"]},
            "PA": {"rul_days": prog["rul_days"]},
            "AG": {"problems": len(advice["problems"]), "tips": len(advice["tips"])},
        },
    }


def apply_maintenance(item: dict, maint: dict | None) -> None:
    """Texnik xizmat muddati sog'liq indeksiga ta'siri (AG bloki uchun ham muammo matni)."""
    if maint and maint["status"] == "overdue":
        item["score"] = max(item["score"] - 20, 0)
        item["problems"].append("texnik xizmat muddati o'tgan")
    elif maint and maint["status"] == "due":
        item["problems"].append("texnik xizmat yaqin")
    item["level"] = level_for(item["score"])


def twin_live(s):  # qulaylik uchun (tashqi modullar `twin._live` ni chaqirmasin)
    return twin._live(s)
