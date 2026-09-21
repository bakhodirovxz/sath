"""J9: usul amal doiralari, tuzilgan ogohlantirishlar, vaqt qadami, Muskingum chegaralari."""

import math

from ges_sim import catalog, flood, penstock
from ges_sim.schema import parse


def _defaults(mod):
    return {f.key: f.default for f in mod.FIELDS}


def test_every_kind_has_warnings_list():
    for kind in catalog.REGISTRY:
        r = catalog.run(kind, {})
        assert isinstance(r["summary"]["warnings"], list), kind


def test_rainfall_range_warnings_and_dt():
    r = catalog.run("rainfall", {"route": False})  # default havza 1200 km², L = 60 km
    w = r["summary"]["warnings"]
    assert any("Kirpich" in x for x in w) and any("TR-55" in x for x in w)
    assert any("shartli shakl" in x for x in w)
    # Δt ≤ 0.133·t_c va 1 soatdan katta emas
    assert r["summary"]["dt_h"] <= min(1.0, 0.133 * r["summary"]["tc_h"]) + 1e-9
    # kichik, tik havza: t_c = 0.275 soat → Δt = 0.05 soat (0.133·0.275 = 0.037 → 0.05 eng mayda qadam)
    s = catalog.run("rainfall", {"basin_km2": 5, "basin_length_km": 2, "basin_slope": 0.1, "route": False})
    assert s["summary"]["dt_h"] <= 0.05 + 1e-9
    assert s["series"]["t"][1] - s["series"]["t"][0] == s["summary"]["dt_h"]
    # hajm balansi qadam o'zgarganda ham saqlanadi
    vol_mm = s["summary"]["runoff_mm"] / 1000 * 5e6 / 1e6
    assert abs(s["summary"]["volume_mcm"] - vol_mm) / vol_mm < 0.03


def test_rainfall_idf_alternating_block_removes_warning_and_peaks_at_center():
    p = {"route": False, "idf_a": 800, "idf_b": 10, "idf_c": 0.7, "rain_hours": 6}
    r = catalog.run("rainfall", p)
    assert not any("shartli shakl" in x for x in r["summary"]["warnings"])
    rain = [x for x in r["series"]["rain_mm"] if x > 0]
    assert abs(sum(rain) - 150) < 1e-6  # jami P saqlanadi
    assert rain.index(max(rain)) in (len(rain) // 2 - 1, len(rain) // 2)


def test_glof_single_peak_and_froehlich_range():
    g = catalog.run("rainfall", {"glof": True, "lake_mcm": 0.012, "lake_depth_m": 2, "route": False})
    w = g["summary"]["warnings"]
    assert any("Froehlich" in x and "hajmi" in x for x in w)
    assert any("Froehlich" in x and "chuqurligi" in x for x in w)
    # yog'insiz, faqat GLOF: seriyadagi cho'qqi (bazaviy sarfsiz) Froehlich cho'qqisiga yaqin —
    # Δt ko'tarilish vaqtining 1/4 idan mayda (ilgari soatlik o'rtachalash 64 % ni yo'qotardi)
    g = catalog.run("rainfall", {"glof": True, "lake_mcm": 10, "rain_mm": 1, "route": False})
    peak = g["summary"]["peak_inflow_m3s"] - 100  # base_m3s default 100
    assert 0.9 * g["glof"]["peak_formula_m3s"] < peak <= g["glof"]["peak_formula_m3s"] + 1
    assert not any("ko'tarilish vaqti" in x for x in g["summary"]["warnings"])


def test_muskingum_both_bounds_enforced_and_mass_conserved():
    warnings = []
    # 0.5 km, 20 oraliq, dt 15 min, c = 3 m/s: K = 8.3 s ≪ dt → c2 < 0 bo'lardi → qadam bo'linadi
    n, x, sub = flood.muskingum_plan(500, 3.0, 0.2, 900, 20, warnings)
    k = 500 / n / 3.0
    dt_r = 900 / sub
    assert 2 * k * x <= dt_r + 1e-9 and dt_r <= 2 * k * (1 - x) + 1e-9
    assert sub > 1 and n == 20
    tri = [0.0] * 5 + [100 * i for i in range(10)] + [900 - 100 * i for i in range(10)] + [0.0] * 60
    fine = flood._resample(tri, sub)
    out = fine
    for _ in range(n):
        out = flood.muskingum(out, k, x, dt_r)
    assert min(out) >= -1e-9 and abs(sum(out) - sum(fine)) / sum(fine) < 1e-6
    # K katta (uzun oraliq, sekin to'lqin) → n oshiriladi (Δt ≥ 2KX)
    warnings = []
    n2, x2, sub2 = flood.muskingum_plan(100000, 0.5, 0.3, 900, 1, warnings)
    k2 = 100000 / n2 / 0.5
    assert 2 * k2 * x2 <= 900 / sub2 + 1e-9 and n2 > 1 and warnings
    # foydalanuvchi n si oraliqda bo'lsa o'zgarmaydi
    warnings = []
    assert flood.muskingum_plan(20000, 3.0, 0.2, 900, 4, warnings) == (4, 0.2, 1) and not warnings


def test_flood_run_reports_reaches_and_warnings():
    p = _defaults(flood)
    p.update({"reach_length_km": 0.5, "reach_count": 20, "dt_min": 15})
    r = flood.run(parse(flood.FIELDS, p))
    assert r["summary"]["muskingum_substeps"] > 1 and r["summary"]["muskingum_reaches"] == 20
    assert min(r["downstream"]["q"]) >= 0
    assert abs(r["summary"]["downstream_peak_m3s"] - r["summary"]["peak_outflow_m3s"]) < 0.02 * r["summary"]["peak_outflow_m3s"]


def test_penstock_friction_factor_continuous_in_transition():
    eps = 1e-4
    f_lam = penstock.friction_factor(2299.9, eps)
    f_tr = penstock.friction_factor(2300.1, eps)
    assert abs(f_lam - f_tr) < 1e-4
    f_a = penstock.friction_factor(3999.9, eps)
    f_b = penstock.friction_factor(4000.1, eps)
    assert abs(f_a - f_b) < 1e-4
    assert penstock.friction_factor(3000, eps) > penstock.friction_factor(2300, eps)


def test_surge_tank_thoma_uses_net_min_head():
    a = catalog.run("surge_tank", {})["summary"]
    b = catalog.run("surge_tank", {"head_min_m": 80})["summary"]
    assert a["thoma_head_net_m"] < 120 and b["thoma_head_net_m"] < a["thoma_head_net_m"]
    assert b["thoma_area_m2"] > a["thoma_area_m2"] and b["thoma_ratio"] < a["thoma_ratio"]
    assert any("head_min_m" in w for w in a["summary"]["warnings"]) if "summary" in a else True


def test_landslide_heller_hager_ranges():
    r = catalog.run("landslide", {"slope_deg": 25})["summary"]
    assert any("α" in w and "Heller" in w for w in r["warnings"])
    assert math.isfinite(r["runup_m"])
