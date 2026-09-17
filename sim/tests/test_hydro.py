import math

import pytest
from ges_sim import scenario
from ges_sim.penstock import RHO, G, PenstockSpec, friction_factor, head_loss, net_head
from ges_sim.reservoir import ReservoirSpec, ReservoirState, SpillwaySpec, StorageCurve, step
from ges_sim.turbine import TurbineSpec, dispatch, flow_for_power

# ---------- Quvur ----------


def test_friction_factor_matches_colebrook():
    # Colebrook ma'lumotnoma qiymati: Re=1e5, ε/D=1e-4 → f ≈ 0.0185 (Moody)
    assert friction_factor(1e5, 1e-4) == pytest.approx(0.0185, rel=0.03)
    assert friction_factor(1000, 1e-4) == pytest.approx(0.064)  # laminar 64/Re
    assert friction_factor(0, 1e-4) == 0.0


def test_head_loss_scales_with_flow_squared():
    spec = PenstockSpec(length_m=200, diameter_m=3, roughness_mm=0.1, minor_loss_k=0)
    h1, h2 = head_loss(30, spec), head_loss(60, spec)
    assert 3.6 < h2 / h1 < 4.0  # turbulent: ~Q² (f biroz kamayadi)
    assert head_loss(0, spec) == 0.0
    assert net_head(50, 60, spec) == pytest.approx(50 - h2)
    assert net_head(50, 60, None) == 50
    assert net_head(1, 1000, spec) == 0.0  # manfiy bo'lmaydi


def test_head_loss_reasonable_magnitude():
    # 180 m, D=4 m, Q=75 m³/s → v≈6 m/s; yo'qotish odatda naporning 1–3 % i
    spec = PenstockSpec(180, 4.0, 0.1, 0.6)
    assert 0.8 < head_loss(75, spec) < 3.0


# ---------- Turbina ----------


def test_power_formula_at_rated_point():
    t = TurbineSpec(rated_power_mw=40, rated_head_m=60, rated_flow_m3s=75, max_efficiency=0.92)
    expected = 0.92 * RHO * G * 75 * 60 / 1e6
    assert t.power_mw(75, 60) == pytest.approx(expected)
    assert t.efficiency(75) == pytest.approx(0.92)
    assert t.efficiency(75 * 0.2) == 0.0  # Francis min yuklama 40 %
    assert t.power_mw(75, 0) == 0.0


def test_efficiency_curve_shapes():
    fr = TurbineSpec(type="Francis", rated_flow_m3s=100)
    ka = TurbineSpec(type="Kaplan", rated_flow_m3s=100)
    assert ka.efficiency(40) > fr.efficiency(40)  # Kaplan qism yuklamada yaxshiroq
    assert fr.efficiency(100) >= fr.efficiency(70) >= fr.efficiency(45)
    with pytest.raises(KeyError):
        TurbineSpec(type="Nomalum").efficiency(50)


def test_dispatch_prefers_fewer_units_at_low_flow():
    units = [
        TurbineSpec(name=f"A{i}", rated_flow_m3s=75, rated_power_mw=40, rated_head_m=60)
        for i in range(3)
    ]
    low = dispatch(60, 60, units)
    assert [u.on for u in low.units] == [True, False, False]
    assert low.flow_m3s == pytest.approx(60)
    full = dispatch(300, 60, units)  # 3×75×1.1 = 247.5 max
    assert all(u.on for u in full.units)
    assert full.flow_m3s == pytest.approx(247.5)
    assert full.power_mw > low.power_mw
    none = dispatch(10, 60, units)  # min 30 dan kam
    assert none.power_mw == 0 and none.flow_m3s == 0
    assert dispatch(60, 60, []).power_mw == 0


def test_dispatch_with_penstock_reduces_head():
    units = [TurbineSpec(rated_flow_m3s=75, rated_power_mw=40, rated_head_m=60)]
    spec = PenstockSpec(180, 4.0)
    a, b = dispatch(75, 60, units), dispatch(75, 60, units, spec)
    assert b.head_net_m < a.head_net_m == 60
    assert b.power_mw < a.power_mw


def test_flow_for_power_inverts_dispatch():
    units = [TurbineSpec(rated_flow_m3s=75, rated_power_mw=40, rated_head_m=60)] * 2
    q = flow_for_power(30, 60, units)
    assert dispatch(q, 60, units).power_mw == pytest.approx(30, abs=0.01)
    assert flow_for_power(1000, 60, units) == pytest.approx(
        2 * 75 * 1.1
    )  # imkondan tashqari → maksimal


# ---------- Suv ombori ----------


def test_storage_curve_interp_and_extrapolation():
    c = StorageCurve((100, 110, 120), (0, 10, 30))
    assert c.volume(105) == pytest.approx(5e6)
    assert c.elevation(20e6) == pytest.approx(115)
    assert c.elevation(c.volume(117.3)) == pytest.approx(117.3)
    assert c.volume(125) == pytest.approx(40e6)  # yuqori nishab 2 mln/m
    assert c.elevation(35e6) == pytest.approx(122.5)
    assert c.volume(90) == 0.0
    with pytest.raises(ValueError):
        StorageCurve((100, 100), (0, 1))
    with pytest.raises(ValueError):
        StorageCurve((100, 110), (5, 1))


def test_prismatic_reservoir_rises_linearly():
    # Yuza 2 km², kiruvchi 100 m³/s, chiqish yo'q → 1 sutkada 100·86400/2e6 = 4.32 m
    c = StorageCurve.prismatic(100, 150, 2.0)
    spec = ReservoirSpec(c, dead_level_m=105, normal_level_m=140, max_level_m=150)
    s = ReservoirState(120, c.volume(120))
    s2, f = step(s, spec, inflow=100, turbine_demand=0, dt_s=86400)
    assert s2.elev_m == pytest.approx(124.32)
    assert f["spill"] == 0 and f["turbine"] == 0


def test_turbine_cannot_draw_below_dead_level():
    c = StorageCurve.prismatic(100, 150, 1.0)
    spec = ReservoirSpec(c, dead_level_m=110, normal_level_m=140)
    s = ReservoirState(110.5, c.volume(110.5))  # o'lik sathdan 0.5 m yuqori = 0.5 mln m³
    s2, f = step(s, spec, inflow=0, turbine_demand=100, dt_s=86400)
    assert f["turbine"] == pytest.approx(0.5e6 / 86400)
    assert f["curtailed"] > 0
    assert s2.elev_m == pytest.approx(110, abs=1e-6)


def test_spillway_discharge_formula_and_forced_spill():
    sp = SpillwaySpec(crest_m=140, width_m=20, coefficient=0.49)
    assert sp.discharge(139) == 0.0
    assert sp.discharge(142) == pytest.approx(0.49 * 20 * math.sqrt(2 * G) * 2**1.5)
    assert SpillwaySpec(140, 20, gate_opening=0).discharge(145) == 0.0
    c = StorageCurve.prismatic(100, 150, 1.0)
    spec = ReservoirSpec(c, dead_level_m=110, normal_level_m=140, max_level_m=141)
    s = ReservoirState(140.9, c.volume(140.9))
    s2, f = step(s, spec, inflow=500, turbine_demand=0, dt_s=86400)
    assert s2.elev_m == pytest.approx(141)
    assert f["forced_spill"] > 0 and f["spill"] == pytest.approx(f["forced_spill"])


def test_mass_balance_conserved():
    c = StorageCurve((100, 120, 140), (0, 50, 200))
    spec = ReservoirSpec(
        c,
        dead_level_m=105,
        normal_level_m=138,
        max_level_m=140,
        other_outflow_m3s=3,
        spillway=SpillwaySpec(137, 10),
    )
    s = ReservoirState(130, c.volume(130))
    total_in = total_out = 0.0
    dt = 3600
    for i in range(500):
        q_in = 80 + 40 * math.sin(i / 20)
        s2, f = step(s, spec, q_in, 60, dt)
        total_in += q_in * dt
        total_out += (f["turbine"] + f["spill"] + f["evap"] + spec.other_outflow_m3s) * dt
        s = s2
    assert s.volume_m3 - c.volume(130) == pytest.approx(total_in - total_out, rel=1e-9)


# ---------- Ssenariy ----------


def test_example_scenario_runs_and_is_consistent():
    out = scenario.run(scenario.example_params())
    s, sm = out["series"], out["summary"]
    assert sm["steps"] == 365 and len(s["power_mw"]) == 365
    assert 0 < sm["capacity_factor"] <= 1
    assert sm["energy_mwh"] == pytest.approx(sum(s["power_mw"]) * 24, rel=1e-6)
    assert sm["min_level_m"] >= 870 and sm["max_level_m"] <= 912
    # target_level rejimi: sath maqsadga yaqinlashadi
    assert abs(s["level"][-1] - 903) < 0.5
    assert s["t"][0] == "2026-01-01" and s["t"][1] == "2026-01-02"
    assert len(out["units"]) == 2 and len(out["units"][0]["power_mw"]) == 365


@pytest.mark.parametrize("mode", scenario.MODES)
def test_all_modes(mode):
    p = scenario.example_params()
    p["operation"] = {"mode": mode, "target_level_m": 900, "flow_m3s": 100, "power_mw": 50}
    p["inflow_m3s"] = {"constant": 150, "steps": 30}
    out = scenario.run(p)
    assert len(out["series"]["level"]) == 30
    if mode == "constant_flow":
        assert all(abs(q - 100) < 1e-6 for q in out["series"]["turbine_flow"])
    if mode == "target_power":
        assert all(abs(pw - 50) < 0.1 for pw in out["series"]["power_mw"])
    if mode == "run_of_river":
        # sarf = kiruvchi − boshqa chiqish, sath deyarli o'zgarmaydi (bug'lanish hisobiga ozgina)
        assert abs(out["series"]["level"][-1] - out["series"]["level"][0]) < 0.5


def test_energy_matches_power_formula_for_constant_case():
    p = scenario.example_params()
    p["inflow_m3s"] = {"constant": 1000, "steps": 5}  # suv yetarli → max_power
    p["operation"] = {"mode": "max_power"}
    p["penstock"] = None
    p["reservoir"]["evaporation_mm_day"] = 0
    out = scenario.run(p)
    q = 2 * 75 * 1.1
    head = out["series"]["head_gross"][0]
    eff = TurbineSpec(rated_flow_m3s=75, rated_power_mw=40, rated_head_m=60).efficiency(82.5)
    assert out["series"]["power_mw"][0] == pytest.approx(
        min(eff * RHO * G * q * head / 1e6, 2 * 42), rel=1e-3
    )


def test_parse_validation():
    p = scenario.example_params()
    p["units"] = []
    with pytest.raises(ValueError):
        scenario.run(p)
    p = scenario.example_params()
    p["operation"] = {"mode": "boshqa"}
    with pytest.raises(ValueError):
        scenario.run(p)
    p = scenario.example_params()
    p["reservoir"]["dead_level_m"] = 910
    with pytest.raises(ValueError):
        scenario.run(p)
