"""SIM-09: haqiqiy GES ma'lumotlari bilan validatsiya.

`SATH_VALIDATION_DATA` (yoki sim/tests/validation/data/<to'plam>/) da ma'lumot bo'lmasa haqiqiy
testlar SKIP bo'ladi; yuklagich va tekshiruvlarning o'zi sintetik to'plam bilan har doim sinaladi.
Format va kerakli ma'lumotlar: docs/validation-data.md.
"""

import csv
import json
import math
from datetime import datetime, timedelta

import plant_dataset as pdv
import pytest
from ges_sim.reservoir import StorageCurve
from ges_sim.turbine import TurbineSpec

DATASETS = pdv.discover()


# ---------------- Haqiqiy ma'lumot (bo'lmasa skip) ----------------


@pytest.mark.skipif(not DATASETS, reason=f"validatsiya ma'lumoti yo'q ({pdv.ENV} yoki {pdv.DEFAULT_DIR})")
@pytest.mark.parametrize("path", DATASETS, ids=[p.name for p in DATASETS])
def test_plant_turbine_power(path):
    ds = pdv.load(path)
    r = pdv.turbine_power_check(ds)["all"]
    assert r["n"] > 0, "agregat sarfi va quvvati bo'yicha yaroqli qator yo'q"
    assert r["mape_pct"] <= ds.acceptance["power_mape_pct"], r
    assert abs(r["bias_pct"]) <= ds.acceptance["power_bias_pct"], r


@pytest.mark.skipif(not DATASETS, reason=f"validatsiya ma'lumoti yo'q ({pdv.ENV} yoki {pdv.DEFAULT_DIR})")
@pytest.mark.parametrize("path", DATASETS, ids=[p.name for p in DATASETS])
def test_plant_water_balance(path):
    ds = pdv.load(path)
    r = pdv.water_balance_check(ds)
    if r is None:
        pytest.skip("inflow_m3s yoki storage_curve yo'q — suv balansi tekshirilmaydi")
    assert r["rmse_m"] <= ds.acceptance["level_rmse_m"], r


# ---------------- Harness o'z-o'zini tekshirishi (sintetik to'plam) ----------------

UNIT = {"name": "GA-1", "type": "Francis", "rated_power_mw": 25, "rated_head_m": 45, "rated_flow_m3s": 62}
CURVE = {"elevations_m": [100, 110, 120], "volumes_mcm": [0, 20, 60]}


def _write(tmp_path, power_scale=1.0, level_offset=0.0, hours=72):
    """Modelning o'zidan yasalgan "o'lchovlar" (xato ≈ 0) — ixtiyoriy buzilish bilan."""
    t = TurbineSpec(**{k: v for k, v in UNIT.items() if k != "name"})
    curve = StorageCurve(tuple(CURVE["elevations_m"]), tuple(CURVE["volumes_mcm"]))
    t0 = datetime(2026, 1, 1)
    rows = []
    level, tail = 115.0, 68.0
    for h in range(hours + 1):
        q = 40 + 15 * math.sin(h / 6)
        inflow = 60.0
        rows.append(
            {
                "ts": (t0 + timedelta(hours=h)).isoformat(),
                "headwater_m": round(level + (level_offset if h % 24 == 0 and h else 0.0), 6),
                "tailwater_m": tail,
                "inflow_m3s": inflow,
                "spill_m3s": "",
                "u1_flow_m3s": round(q, 6),
                "u1_power_mw": round(t.power_mw(q, level - tail) * power_scale, 6),
            }
        )
        q_next = 40 + 15 * math.sin((h + 1) / 6)
        v = curve.volume(level) + (inflow - (q + q_next) / 2) * 3600
        level = curve.elevation(v)
    d = tmp_path / "sintetik"
    d.mkdir()
    (d / "plant.json").write_text(
        json.dumps({"name": "Sintetik", "units": [UNIT], "storage_curve": CURVE}), encoding="utf-8"
    )
    with (d / "timeseries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return d


def test_harness_self_consistent(tmp_path):
    ds = pdv.load(_write(tmp_path))
    p = pdv.turbine_power_check(ds)["all"]
    assert p["n"] == 73 and p["mape_pct"] < 0.01
    wb = pdv.water_balance_check(ds)
    assert wb["windows"] == 3 and wb["rmse_m"] < 0.01


def test_harness_detects_model_mismatch(tmp_path):
    ds = pdv.load(_write(tmp_path, power_scale=1.10, level_offset=0.5))
    p = pdv.turbine_power_check(ds)["all"]
    assert p["mape_pct"] > ds.acceptance["power_mape_pct"]  # 10 % → mezondan oshadi
    assert p["bias_pct"] < -8
    assert pdv.water_balance_check(ds)["rmse_m"] > ds.acceptance["level_rmse_m"]


def test_loader_rejects_bad_files(tmp_path):
    d = _write(tmp_path)
    txt = (d / "timeseries.csv").read_text(encoding="utf-8").replace("u1_power_mw", "u1_p")
    (d / "timeseries.csv").write_text(txt, encoding="utf-8")
    with pytest.raises(ValueError, match="u1_power_mw"):
        pdv.load(d)
    (d / "plant.json").write_text(json.dumps({"units": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="units"):
        pdv.load(d)
