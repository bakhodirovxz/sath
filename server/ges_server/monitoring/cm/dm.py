"""DM — Data Manipulation (ISO 13374-1 §5.3): signal qayta ishlash va xususiyat ajratish.

Skalyar kanallar uchun: chiziqli trend (kun bo'yicha o'zgarish), baza o'rtachasi/standart og'ishi va
z-score. Spektr uchun: cho'qqilar, val chastotasi garmonikalari (1×, 2×, 3×), podshipnik nuqson
chastotalari (BPFO/BPFI/BSF/FTF) va ularning envelope-spektrdagi mosligi, polosa energiyasi.

Podshipnik chastotalari (ISO 13373-3, Harris — Rolling Bearing Analysis):
    BPFO = (n/2)·f_r·(1 − (d/D)·cos α)      tashqi halqa nuqsoni
    BPFI = (n/2)·f_r·(1 + (d/D)·cos α)      ichki halqa nuqsoni
    BSF  = (D/2d)·f_r·(1 − ((d/D)·cos α)²)  sharcha nuqsoni
    FTF  = (f_r/2)·(1 − (d/D)·cos α)        separator (qafas)
bu yerda n — sharchalar soni, d — sharcha diametri, D — o'rtacha (pitch) diametr, α — kontakt burchagi,
f_r = rpm/60 — val chastotasi, Gs. Geometriya aktiv konfiguratsiyasida `bearing`: {n, d_mm, D_mm, alpha_deg}.
"""

from __future__ import annotations

import math
from datetime import datetime

from ...orm import Asset, Spectrum


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


def scalar_features(ch: dict | None) -> dict | None:
    """Skalyar kanal xususiyatlari: trend, baza, z-score, anomaliya bayrog'i (|z| > 3)."""
    if ch is None:
        return None
    tr = trend(ch["series"])
    v = ch["value"]
    z = None
    if tr and tr[2] > 1e-9 and v is not None:
        z = (v - tr[1]) / tr[2]
    return {
        "sensor_id": ch["sensor_id"],
        "name": ch["name"],
        "unit": ch["unit"],
        "value": v,
        "stale": ch["stale"],
        "slope_per_day": round(tr[0], 5) if tr else None,
        "baseline_mean": round(tr[1], 4) if tr else None,
        "baseline_std": round(tr[2], 4) if tr else None,
        "z": round(z, 2) if z is not None else None,
        "anomaly": bool(z is not None and abs(z) > 3),
        "points": len(ch["series"]),
    }


def bearing_frequencies(bearing: dict | None, rpm: float | None) -> dict[str, float] | None:
    """Podshipnik nuqson chastotalari, Gs (geometriya va val tezligi berilganda)."""
    if not bearing or not rpm or rpm <= 0:
        return None
    try:
        n = float(bearing["n"])
        d = float(bearing["d_mm"])
        dm = float(bearing["D_mm"])
    except (KeyError, TypeError, ValueError):
        return None
    if n <= 0 or d <= 0 or dm <= 0:
        return None
    alpha = math.radians(float(bearing.get("alpha_deg") or 0.0))
    fr = rpm / 60.0
    ratio = (d / dm) * math.cos(alpha)
    return {
        "fr": round(fr, 3),
        "BPFO": round(n / 2 * fr * (1 - ratio), 3),
        "BPFI": round(n / 2 * fr * (1 + ratio), 3),
        "BSF": round(dm / (2 * d) * fr * (1 - ratio**2), 3),
        "FTF": round(fr / 2 * (1 - ratio), 3),
    }


def axis(sp: Spectrum) -> list[float]:
    """Chastota o'qi: aniq berilgan `freqs` yoki f_min..f_max oralig'idagi bir tekis to'r."""
    if sp.freqs:
        return [float(f) for f in sp.freqs]
    n = len(sp.values or [])
    if n < 2 or sp.f_max <= sp.f_min:
        return []
    step = (sp.f_max - sp.f_min) / (n - 1)
    return [sp.f_min + i * step for i in range(n)]


def peaks(sp: Spectrum, top: int = 5) -> list[dict]:
    """Eng katta lokal cho'qqilar (chastota, amplituda)."""
    vals = [float(v) for v in (sp.values or [])]
    fs = axis(sp)
    if len(vals) < 3 or len(fs) != len(vals):
        return []
    out = [
        {"f": round(fs[i], 3), "a": round(vals[i], 4)}
        for i in range(1, len(vals) - 1)
        if vals[i] >= vals[i - 1] and vals[i] >= vals[i + 1]
    ]
    return sorted(out, key=lambda p: -p["a"])[:top]


def amplitude_at(sp: Spectrum, f: float, tol_pct: float = 3.0) -> float | None:
    """Berilgan chastota atrofidagi (±tol %) eng katta amplituda."""
    vals = [float(v) for v in (sp.values or [])]
    fs = axis(sp)
    if not vals or len(fs) != len(vals) or f <= 0:
        return None
    tol = max(f * tol_pct / 100.0, (sp.f_max - sp.f_min) / max(len(vals) - 1, 1))
    band = [v for fi, v in zip(fs, vals, strict=False) if abs(fi - f) <= tol]
    return round(max(band), 4) if band else None


def overall(sp: Spectrum) -> float:
    """Spektr bo'yicha umumiy daraja (r.m.s. yig'indisi — Parseval taxminiy)."""
    vals = [float(v) for v in (sp.values or [])]
    return round(math.sqrt(sum(v * v for v in vals)), 4) if vals else 0.0


def spectrum_features(sp: Spectrum, bearing: dict | None, rpm: float | None) -> dict:
    """Bitta spektr yozuvi xususiyatlari: cho'qqilar, 1×/2×/3× garmonikalar, podshipnik chastotalari."""
    rpm = sp.rpm or rpm
    freqs = bearing_frequencies(bearing, rpm)
    fr = (rpm / 60.0) if rpm else None
    harm = {}
    if fr:
        for k in (1, 2, 3):
            a = amplitude_at(sp, fr * k)
            if a is not None:
                harm[f"{k}x"] = a
    matches = []
    if freqs:
        base = max(overall(sp), 1e-9)
        for name in ("BPFO", "BPFI", "BSF", "FTF"):
            a = amplitude_at(sp, freqs[name])
            if a is None:
                continue
            share = a / base
            matches.append(
                {"name": name, "f": freqs[name], "amplitude": a, "share": round(share, 3)}
            )
    return {
        "id": sp.id,
        "ts": sp.ts,
        "kind": sp.kind,
        "unit": sp.unit,
        "rpm": rpm,
        "overall": overall(sp),
        "peaks": peaks(sp),
        "harmonics": harm,
        "bearing_frequencies": freqs,
        "bearing_matches": sorted(matches, key=lambda m: -m["share"]),
        "source": sp.source,
    }


def features(db, a: Asset, acq: dict) -> dict:
    """DM natijasi: har kanal uchun xususiyatlar + spektr xususiyatlari + FIK trendi."""
    cfg = acq["config"]
    rpm = float(cfg.get("rated_speed_rpm") or 0) or None
    scal = {name: scalar_features(ch) for name, ch in acq["channels"].items()}
    spec = [spectrum_features(sp, cfg.get("bearing"), rpm) for sp in acq["spectra"]]
    eff_tr = trend(acq["efficiency_series"])
    return {
        "scalars": scal,
        "spectra": spec,
        "efficiency_trend_pct_per_month": round(eff_tr[0] * 30 * 100, 3) if eff_tr else None,
    }
