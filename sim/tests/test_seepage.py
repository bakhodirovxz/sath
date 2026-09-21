"""J7: oqim to'ri (chekli farqlar) — aniq yechim bilan, Lane jadvali, filtr mezonlari, drenaj gradiyenti."""

import math

import pytest
from ges_sim import catalog, seepage


def test_flow_net_matches_exact_single_sheet_pile():
    # Bitta shpunt (d = 10 m), cheksiz chuqur asos: chiqish gradiyenti tubda i(x) = H/(π√(x²+d²))
    # (konform akslantirish ζ = √(z²+d²), Ω = (H/π)·arccos(ζ/d)); toe da H/(πd)
    H, d = 60.0, 10.0
    n = seepage.flow_net(H, 1.0, d, 150.0, 0.0, True, dx=1.0)
    assert abs(n["i_exit"] - H / (math.pi * d)) / (H / (math.pi * d)) < 0.03
    for k, g in enumerate(n["toe_gradients"][:4]):
        exact = H / (math.pi * math.sqrt((k * 1.0) ** 2 + d**2))
        assert abs(g - exact) / exact < 0.03


def test_flow_net_matches_khosla_for_floor_with_downstream_pile():
    # Xosla (1936): G_E = (H/d)/(π√λ) — pol b = 30, shpunt d = 10, chuqur asos
    H, b, d = 60.0, 30.0, 10.0
    n = seepage.flow_net(H, b, d, 300.0, 0.0, True, dx=1.0)
    ge = seepage.khosla_exit_gradient(H, b, d)
    assert abs(n["i_exit"] - ge) / ge < 0.03


def test_flow_net_depends_on_geometry():
    H = 60.0
    base = seepage.flow_net(H, 64, 12, 30, 40, True)
    deeper = seepage.flow_net(H, 64, 20, 30, 40, True)
    no_apron = seepage.flow_net(H, 64, 12, 30, 0, True)
    upstream = seepage.flow_net(H, 64, 12, 30, 40, False)
    assert deeper["q_over_kH"] < base["q_over_kH"] and deeper["i_exit"] < base["i_exit"]
    assert no_apron["q_over_kH"] > base["q_over_kH"]  # ponur yo'lni uzaytiradi → kam sarf
    assert upstream["i_exit"] > base["i_exit"]  # yuqori shpunt chiqish gradiyentini kamaytirmaydi
    assert 0 < base["q_over_kH"] < 1


def test_run_concrete_uses_net_not_user_nf_nd():
    keys = {f.key for f in seepage.FIELDS}
    assert "nf" not in keys and "nd" not in keys and "stratum_depth_m" in keys
    r = catalog.run("seepage", {})
    s = r["summary"]
    assert s["shape_factor"] > 0 and s["exit_gradient_khosla"] is not None
    assert "net" in r and len(r["series"]["cutoff_m"]) == 9
    assert all(b <= a for a, b in zip(r["series"]["exit_gradient"], r["series"]["exit_gradient"][1:], strict=False))
    r2 = catalog.run("seepage", {"cutoff_m": 24})["summary"]
    assert r2["q_l_s_m"] < s["q_l_s_m"] and r2["exit_gradient"] < s["exit_gradient"]


def test_lane_table_and_rock_excluded():
    assert seepage.SOILS["fine_sand"][1] == 7.0 and seepage.SOILS["very_fine_sand"][1] == 8.5
    assert seepage.SOILS["medium_sand"][1] == 6.0 and seepage.SOILS["coarse_gravel"][1] == 3.0
    assert "rock" not in seepage.SOILS
    with pytest.raises(ValueError, match="qoya"):
        catalog.run("seepage", {"soil": "rock"})


def test_filter_criteria_terzaghi():
    assert seepage.filter_check(1.0, 0.5, 0.1) == []  # 2 ≤ 4, 10 ≥ 4
    bad = seepage.filter_check(3.0, 0.5, 0.1)  # 6 > 4
    assert len(bad) == 1 and "d85b" in bad[0]
    bad2 = seepage.filter_check(0.3, 0.5, 0.1)  # 0.6 < 4 → 3 ≥ 4 emas
    assert len(bad2) == 1 and "d15b" in bad2[0]
    r = catalog.run("seepage", {"filter_d15_mm": 3.0, "base_d85_mm": 0.5})["summary"]
    assert any("D15f/d85b" in x for x in r["verdict"].split("; "))


def test_earth_dam_toe_drain_gradient():
    r = catalog.run("seepage", {"dam_type": "earth"})["summary"]
    p = {f.key: f.default for f in seepage.FIELDS}
    q = p["k_m_s"] * (p["h1_m"] ** 2 - p["h2_m"] ** 2) / (2 * p["seep_length_m"])
    assert abs(r["exit_gradient"] - q / (p["k_m_s"] * p["drain_length_m"])) < 1e-4
    assert abs(r["critical_gradient"] - (2.65 - 1) / 1.7) < 1e-3
    # uzunroq drenaj → kichik gradiyent → katta zaxira
    r2 = catalog.run("seepage", {"dam_type": "earth", "drain_length_m": 60})["summary"]
    assert r2["fs_piping"] > r["fs_piping"]
    short = catalog.run("seepage", {"dam_type": "earth", "seep_length_m": 80})["summary"]
    assert any("Dyupyui" in w for w in short["warnings"])
