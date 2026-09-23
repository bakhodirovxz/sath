"""SIM-09: haqiqiy GES ekspluatatsiya ma'lumotlari bilan validatsiya — ma'lumot to'plami yuklagichi.

Format (to'liq tavsif: docs/validation-data.md). Papka:
  plant.json       — stansiya pasporti (agregatlar, quvur, sath–hajm egri chizig'i, qabul mezonlari)
  timeseries.csv   — vaqt qatori, ustunlar:
      ts                      ISO 8601 (UTC yoki mahalliy — bir xil), qat'iy o'suvchi, doimiy qadam shart emas
      headwater_m             yuqori byef sathi, m (abs)
      tailwater_m             quyi byef sathi, m (abs)
      inflow_m3s              (ixtiyoriy) omborga kiruvchi sarf — suv balansi tekshiruvi uchun
      spill_m3s               (ixtiyoriy) suv tashlagich / salt tashlama sarfi
      other_outflow_m3s       (ixtiyoriy) sug'orish, ekologik oqim, filtratsiya
      u<N>_flow_m3s           N-agregat sarfi (1 dan boshlab; plant.json dagi tartib bilan)
      u<N>_power_mw           N-agregat generator klemmasidagi faol quvvat, MW
  Bo'sh katak — o'lchov yo'q (NaN, hisobga olinmaydi).
Faqat standart kutubxona — ma'lumot yo'q muhitda ham import qilinadi.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ENV = "SATH_VALIDATION_DATA"  # papka (yoki ; bilan ajratilgan papkalar)
DEFAULT_DIR = Path(__file__).resolve().parent / "data"
REQUIRED = ("ts", "headwater_m", "tailwater_m")
DEFAULT_ACCEPTANCE = {
    "power_mape_pct": 5.0,  # agregat quvvati — o'rtacha absolyut nisbiy xato
    "power_bias_pct": 3.0,  # tizimli siljish (o'rtacha nisbiy xato moduli)
    "level_rmse_m": 0.15,  # suv balansi: oyna oxiridagi sath xatosi (RMSE)
    "level_window_h": 24.0,  # suv balansi oynasi — har oyna o'lchangan sathdan qayta boshlanadi
}


@dataclass
class PlantDataset:
    name: str
    path: Path
    plant: dict
    ts: list[datetime]
    cols: dict[str, list[float]]
    acceptance: dict = field(default_factory=dict)

    @property
    def n_units(self) -> int:
        return len(self.plant.get("units") or [])

    def col(self, key: str) -> list[float] | None:
        return self.cols.get(key)

    def has(self, key: str) -> bool:
        c = self.cols.get(key)
        return c is not None and any(not math.isnan(v) for v in c)


def _num(s: str) -> float:
    s = (s or "").strip()
    if not s:
        return math.nan
    return float(s.replace(",", "."))


def load(path: str | Path) -> PlantDataset:
    """Papkadan to'plamni o'qiydi va tekshiradi; xato bo'lsa ValueError (aniq sabab bilan)."""
    d = Path(path)
    pj, tc = d / "plant.json", d / "timeseries.csv"
    if not pj.is_file() or not tc.is_file():
        raise ValueError(f"{d}: plant.json va timeseries.csv kerak")
    plant = json.loads(pj.read_text(encoding="utf-8"))
    units = plant.get("units") or []
    if not units:
        raise ValueError("plant.json: units bo'sh")
    for i, u in enumerate(units, 1):
        for k in ("rated_power_mw", "rated_head_m", "rated_flow_m3s"):
            if not isinstance(u.get(k), int | float) or u[k] <= 0:
                raise ValueError(f"plant.json: units[{i}].{k} musbat son bo'lishi kerak")
    sc = plant.get("storage_curve")
    if sc is not None and len(sc.get("elevations_m") or []) != len(sc.get("volumes_mcm") or []):
        raise ValueError("plant.json: storage_curve.elevations_m va volumes_mcm uzunligi teng emas")
    with tc.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("timeseries.csv bo'sh")
    header = list(rows[0].keys())
    miss = [k for k in REQUIRED if k not in header]
    if miss:
        raise ValueError(f"timeseries.csv: ustun(lar) yo'q: {', '.join(miss)}")
    ts = [datetime.fromisoformat(r["ts"].strip().replace("Z", "+00:00")) for r in rows]
    if any(b <= a for a, b in zip(ts, ts[1:], strict=False)):
        raise ValueError("timeseries.csv: ts qat'iy o'sib borishi kerak")
    cols = {k: [_num(r.get(k, "")) for r in rows] for k in header if k != "ts"}
    for i in range(1, len(units) + 1):
        if f"u{i}_flow_m3s" not in cols or f"u{i}_power_mw" not in cols:
            raise ValueError(f"timeseries.csv: u{i}_flow_m3s va u{i}_power_mw ustunlari kerak")
    acc = {**DEFAULT_ACCEPTANCE, **(plant.get("acceptance") or {})}
    return PlantDataset(plant.get("name") or d.name, d, plant, ts, cols, acc)


def discover() -> list[Path]:
    """SATH_VALIDATION_DATA (yoki sim/tests/validation/data/*) dagi to'plam papkalari."""
    roots = [Path(p) for p in os.environ.get(ENV, "").split(os.pathsep) if p.strip()]
    if not roots:
        roots = [DEFAULT_DIR]
    out: list[Path] = []
    for r in roots:
        if (r / "plant.json").is_file():
            out.append(r)
        elif r.is_dir():
            out += sorted(p for p in r.iterdir() if (p / "plant.json").is_file())
    return out


# ---------------- Tekshiruvlar (natija: metrika lug'ati) ----------------


def turbine_power_check(ds: PlantDataset) -> dict:
    """O'lchangan sarf va sof napor bo'yicha `TurbineSpec.power_mw` ↔ o'lchangan quvvat."""
    from ges_sim.penstock import PenstockSpec, net_head
    from ges_sim.turbine import TurbineSpec

    pen = ds.plant.get("penstock")
    spec_p = PenstockSpec(**pen) if pen else None
    hw, tw = ds.cols["headwater_m"], ds.cols["tailwater_m"]
    rel: list[float] = []
    per_unit: dict[str, dict] = {}
    for i, u in enumerate(ds.plant["units"], 1):
        ts = TurbineSpec(**{k: v for k, v in u.items() if k in TurbineSpec.__dataclass_fields__})
        q, pw = ds.cols[f"u{i}_flow_m3s"], ds.cols[f"u{i}_power_mw"]
        errs = []
        for k in range(len(q)):
            if any(math.isnan(x) for x in (q[k], pw[k], hw[k], tw[k])) or q[k] <= 0 or pw[k] <= 0:
                continue
            gross = hw[k] - tw[k]
            h = net_head(gross, q[k], spec_p) if spec_p else gross
            pred = ts.power_mw(q[k], h)
            if pred <= 0:
                continue
            errs.append((pred - pw[k]) / pw[k])
        rel += errs
        per_unit[u.get("name") or f"u{i}"] = _stats(errs)
    return {"all": _stats(rel), "units": per_unit}


def water_balance_check(ds: PlantDataset) -> dict | None:
    """Sath–hajm egri chizig'i + o'lchangan kiruvchi/chiquvchi sarf bilan sathni marshrutlash
    (`reservoir.step`, modified Puls) — har `level_window_h` oynada o'lchangan sathdan qayta boshlab,
    oyna oxiridagi sath xatosi. inflow_m3s yoki storage_curve bo'lmasa None."""
    from ges_sim.reservoir import ReservoirSpec, ReservoirState, StorageCurve, step

    sc = ds.plant.get("storage_curve")
    if sc is None or not ds.has("inflow_m3s"):
        return None
    curve = StorageCurve(tuple(sc["elevations_m"]), tuple(sc["volumes_mcm"]))
    lo = min(sc["elevations_m"])
    hw, inflow = ds.cols["headwater_m"], ds.cols["inflow_m3s"]
    zero = [0.0] * len(hw)
    spill = ds.cols.get("spill_m3s") or zero
    other = ds.cols.get("other_outflow_m3s") or zero
    turb = [
        sum(
            v
            for v in (ds.cols[f"u{i}_flow_m3s"][k] for i in range(1, ds.n_units + 1))
            if not math.isnan(v)
        )
        for k in range(len(hw))
    ]
    window = ds.acceptance["level_window_h"] * 3600
    errs: list[float] = []
    k0 = 0
    while k0 < len(hw) - 1:
        if math.isnan(hw[k0]):
            k0 += 1
            continue
        st = ReservoirState(hw[k0], curve.volume(hw[k0]))
        k = k0
        while k < len(hw) - 1 and (ds.ts[k + 1] - ds.ts[k0]).total_seconds() <= window:
            dt = (ds.ts[k + 1] - ds.ts[k]).total_seconds()
            # qadam o'rtachasi — boshlanish va oxiri o'lchovlarining o'rtasi
            def avg(c, k=k):
                a, b = c[k], c[k + 1]
                vals = [x for x in (a, b) if not math.isnan(x)]
                return sum(vals) / len(vals) if vals else 0.0

            out_other = avg(spill) + avg(other)
            spec = ReservoirSpec(
                curve=curve,
                dead_level_m=lo,
                normal_level_m=max(sc["elevations_m"]),
                max_level_m=max(sc["elevations_m"]) + 50,
                other_outflow_m3s=out_other,
            )
            st, _ = step(st, spec, avg(inflow), (turb[k] + turb[k + 1]) / 2, dt)
            k += 1
        if k > k0 and not math.isnan(hw[k]):
            errs.append(st.elev_m - hw[k])
        k0 = max(k, k0 + 1)
    if not errs:
        return None
    return {
        "windows": len(errs),
        "rmse_m": math.sqrt(sum(e * e for e in errs) / len(errs)),
        "bias_m": sum(errs) / len(errs),
        "max_abs_m": max(abs(e) for e in errs),
    }


def _stats(rel: list[float]) -> dict:
    if not rel:
        return {"n": 0, "mape_pct": None, "bias_pct": None}
    return {
        "n": len(rel),
        "mape_pct": 100 * sum(abs(e) for e in rel) / len(rel),
        "bias_pct": 100 * sum(rel) / len(rel),
    }
