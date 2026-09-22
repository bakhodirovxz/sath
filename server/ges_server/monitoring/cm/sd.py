"""SD — State Detection (ISO 13374-1 §5.4): xususiyatlarni baza va chegaralar bilan solishtirib holat
belgilash (normal / ogohlantirish / alarm), ISO 20816-5 zonalari va tashqi tizim holati.

ISO 10816-5:2000 / ISO 20816-5:2018 A ilovasi (podshipnik korpusi tebranish tezligi, mm/s r.m.s.),
mashina guruhi bo'yicha zona chegaralari (A/B, B/C, C/D):
  1-guruh (gorizontal, >300 ayl/min): 1.6 / 2.5 / 4.0
  2-guruh (gorizontal, kapsulali/bulb, ≤300): 2.5 / 4.0 / 6.4
  3-guruh (vertikal, barcha podshipnik poydevorga): 1.6 / 2.5 / 4.0
  4-guruh (vertikal, yuqori podshipnik statorga): 2.5 / 4.0 / 6.4
Val nisbiy tebranishi (ISO 20816-5 B ilova, µm p-p) — `shaft_limits` konfiguratsiyasidan yoki
podshipnik zazorining 25 % / 40 % qoidasi bo'yicha (`shaft_clearance_um`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...orm import Asset, CmResult

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
STATES = ("normal", "alert", "alarm", "unknown")
ZONE_STATE = {"A": "normal", "B": "normal", "C": "alert", "D": "alarm"}
# Podshipnik nuqson chastotasi energiyasining umumiy darajaga nisbati (envelope-spektr)
BEARING_SHARE_ALERT = 0.15
BEARING_SHARE_ALARM = 0.30


def vib_zone(v: float, group: int = 4) -> str:
    ab, bc, cd = VIB_ZONES.get(int(group), VIB_ZONES[4])
    return "A" if v < ab else "B" if v < bc else "C" if v < cd else "D"


def worst(states: list[str]) -> str:
    for s in ("alarm", "alert", "normal"):
        if s in states:
            return s
    return "unknown"


def external_states(db: Session, asset_id: int, now: datetime | None = None) -> list[dict]:
    """Tashqi holat monitoringi tizimlaridan kelgan amaldagi natijalar (manba bo'yicha eng so'nggisi)."""
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(CmResult)
        .filter(CmResult.asset_id == asset_id)
        .order_by(CmResult.ts.desc())
        .limit(50)
        .all()
    )
    seen: set[tuple[str, str]] = set()
    out = []
    for r in rows:
        key = (r.source, r.block)
        if key in seen:
            continue
        ts = r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=timezone.utc)
        if now - ts > timedelta(hours=r.valid_hours or 24):
            continue  # eskirgan natija hisobga olinmaydi
        seen.add(key)
        out.append(
            {
                "id": r.id,
                "source": r.source,
                "block": r.block,
                "ts": ts,
                "state": r.state if r.state in STATES else "unknown",
                "health_score": r.health_score,
                "rul_days": r.rul_days,
                "diagnosis": r.diagnosis,
                "confidence": r.confidence,
                "detail": r.detail or {},
            }
        )
    return out


def _shaft_limits(cfg: dict) -> tuple[float, float] | None:
    lim = cfg.get("shaft_limits")
    if isinstance(lim, (list, tuple)) and len(lim) == 2:
        return float(lim[0]), float(lim[1])
    clearance = cfg.get("shaft_clearance_um")
    if clearance:  # ISO 20816-5 B ilova: zazorning 25 % (B/C) va 40 % (C/D) qismi
        c = float(clearance)
        return 0.25 * c, 0.40 * c
    return None


def detect(db: Session, a: Asset, acq: dict, feats: dict) -> dict:
    """SD natijasi: har kanal/spektr uchun holat va sabab, hamda umumiy holat."""
    cfg = acq["config"]
    group = acq["machine_group"]
    items: dict[str, dict] = {}

    vib = feats["scalars"].get("vibration")
    if vib and vib["value"] is not None:
        zone = vib_zone(vib["value"], group)
        items["vibration"] = {
            "state": ZONE_STATE[zone],
            "zone": zone,
            "zone_note": ZONE_NOTE[zone],
            "limits": VIB_ZONES.get(group, VIB_ZONES[4]),
            "reason": f"tebranish {vib['value']:.2f} {vib['unit'] or 'mm/s'} — {zone} zona (ISO 20816-5, {group}-guruh)",
            "anomaly": vib["anomaly"],
        }

    temp = feats["scalars"].get("bearing_temp")
    if temp and temp["value"] is not None:
        warn = float(cfg.get("temp_warn") or 70)
        alarm = float(cfg.get("temp_alarm") or 80)
        st = "alarm" if temp["value"] >= alarm else "alert" if temp["value"] >= warn else "normal"
        items["bearing_temp"] = {
            "state": st,
            "warn": warn,
            "alarm": alarm,
            "reason": f"podshipnik harorati {temp['value']:.1f} °C"
            + (f" ≥ {alarm} °C (alarm)" if st == "alarm" else f" ≥ {warn} °C" if st == "alert" else ""),
            "anomaly": temp["anomaly"],
        }

    shaft = feats["scalars"].get("shaft_vibration")
    lim = _shaft_limits(cfg)
    if shaft and shaft["value"] is not None and lim:
        bc, cd = lim
        st = "alarm" if shaft["value"] >= cd else "alert" if shaft["value"] >= bc else "normal"
        items["shaft_vibration"] = {
            "state": st,
            "limits": [round(bc, 1), round(cd, 1)],
            "reason": f"val nisbiy tebranishi {shaft['value']:.0f} µm p-p (chegara {bc:.0f}/{cd:.0f}, ISO 20816-5 B ilova)",
            "anomaly": shaft["anomaly"],
        }

    pd = feats["scalars"].get("partial_discharge")
    if pd and pd["value"] is not None and cfg.get("pd_alarm"):
        warn = float(cfg.get("pd_warn") or float(cfg["pd_alarm"]) * 0.6)
        alarm = float(cfg["pd_alarm"])
        st = "alarm" if pd["value"] >= alarm else "alert" if pd["value"] >= warn else "normal"
        items["partial_discharge"] = {
            "state": st,
            "warn": warn,
            "alarm": alarm,
            "reason": f"qisman razryad {pd['value']:.0f} {pd['unit'] or 'pC'} (IEC 60270)",
            "anomaly": pd["anomaly"],
        }

    gap = feats["scalars"].get("air_gap")
    if gap and gap["value"] is not None and cfg.get("air_gap_min_mm"):
        mn = float(cfg["air_gap_min_mm"])
        st = "alarm" if gap["value"] < mn else "alert" if gap["value"] < mn * 1.1 else "normal"
        items["air_gap"] = {
            "state": st,
            "min_mm": mn,
            "reason": f"havo oralig'i {gap['value']:.1f} mm (minimal {mn:.1f} mm)",
            "anomaly": gap["anomaly"],
        }

    oil = feats["scalars"].get("oil_water")
    if oil and oil["value"] is not None:
        warn = float(cfg.get("oil_water_warn") or 200)  # ppm, IEC 60422 (moy sifati)
        alarm = float(cfg.get("oil_water_alarm") or 300)
        st = "alarm" if oil["value"] >= alarm else "alert" if oil["value"] >= warn else "normal"
        items["oil_water"] = {
            "state": st,
            "warn": warn,
            "alarm": alarm,
            "reason": f"moyda suv {oil['value']:.0f} ppm (IEC 60422)",
            "anomaly": oil["anomaly"],
        }

    # spektr: podshipnik nuqson chastotalari (envelope ustunroq)
    bearing_hit = None
    for sp in feats["spectra"]:
        for m in sp["bearing_matches"]:
            share = m["share"] * (1.2 if sp["kind"] == "envelope" else 1.0)
            if share >= BEARING_SHARE_ALERT and (bearing_hit is None or share > bearing_hit["share"]):
                bearing_hit = {**m, "share": round(share, 3), "kind": sp["kind"], "spectrum_id": sp["id"]}
    if bearing_hit:
        items["bearing_defect"] = {
            "state": "alarm" if bearing_hit["share"] >= BEARING_SHARE_ALARM else "alert",
            "reason": f"podshipnik nuqson chastotasi {bearing_hit['name']} ({bearing_hit['f']:.1f} Gs) "
            f"energiyaning {bearing_hit['share'] * 100:.0f} % ini tashkil qiladi ({bearing_hit['kind']} spektr)",
            "match": bearing_hit,
        }

    ext = external_states(db, a.id)
    for e in ext:
        if e["block"] in ("SD", "HA") and e["state"] != "unknown":
            items[f"external:{e['source']}"] = {
                "state": e["state"],
                "reason": f"{e['source']}: {e['diagnosis'] or e['state']}"
                + (f" (ishonch {e['confidence']:.0%})" if e["confidence"] is not None else ""),
                "external": True,
            }

    stale = [
        f["name"]
        for f in feats["scalars"].values()
        if f and f["stale"]
    ]
    return {
        "items": items,
        "overall": worst([v["state"] for v in items.values()]) if items else "unknown",
        "external": ext,
        "stale_channels": stale,
    }
