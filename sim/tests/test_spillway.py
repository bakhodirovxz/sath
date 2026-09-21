"""J10: suv tashlagich (ε, σ_s, H₀, zatvor ostidan oqim) va ombor massa balansi."""

import math

import pytest
from ges_sim.penstock import G
from ges_sim.reservoir import ReservoirSpec, ReservoirState, SpillwaySpec, StorageCurve, step
from ges_sim.spillway import Spillway, side_contraction, submergence_factor


def test_side_contraction_kiselev():
    # ε = 1 − 0.2·[ξ_q + (n−1)·ξ_b]·H₀/(n·b): 3 oraliq × 10 m, yumaloq bykalar (0.45), qirg'oq 0.7, H₀ = 4
    eps = side_contraction(4.0, 3, 10.0, 0.45, 0.7)
    assert abs(eps - (1 - 0.2 * (0.7 + 2 * 0.45) * 4 / 30)) < 1e-12
    assert side_contraction(4.0, 0, 10.0, 0.45, 0.7) == 1.0
    # ko'p byka → ko'proq siqilish → kamroq sarf
    q1 = Spillway(100, 30, bays=1).discharge(104)
    q3 = Spillway(100, 30, bays=3).discharge(104)
    assert q3 < q1


def test_submergence_reduces_discharge():
    assert submergence_factor(-1, 4) == 1.0 and submergence_factor(0, 4) == 1.0
    assert abs(submergence_factor(2.0, 4.0) - 0.93) < 1e-9  # h_s/H₀ = 0.5
    assert submergence_factor(4.0, 4.0) == 0.0
    sp = Spillway(100, 20)
    assert sp.discharge(104, tailwater_m=99) == sp.discharge(104)
    assert sp.discharge(104, tailwater_m=102.4) < 0.9 * sp.discharge(104)
    assert sp.discharge_detail(104, 102.4)["regime"] == "bostirilgan"


def test_approach_velocity_head_increases_discharge():
    free = Spillway(100, 20).discharge(103)
    with_h0 = Spillway(100, 20, approach_area_m2=200).discharge_detail(103)
    assert with_h0["h0"] > 3.0 and with_h0["q"] > free


def test_gate_orifice_law():
    sp = Spillway(100, 20, gate_height_m=6.0)
    h = 5.0
    # a = 0.4·6 = 2.4 < 0.75·H → teshik: Q = μ·ε·b·a·√(2g(H₀ − ε_c·a))
    d = Spillway(100, 20, gate_height_m=6.0, gate_opening=0.4).discharge_detail(100 + h)
    a = 2.4
    eps = side_contraction(h, 1, 20, 0.45, 0.7)
    expected = 0.65 * eps * 20 * a * math.sqrt(2 * G * (h - 0.62 * a))
    assert d["regime"] == "zatvor ostidan" and abs(d["q"] - expected) < 1e-9
    # ochiqlik ∝ H^0.5 (chiziqli ko'paytuvchi emas): a ikki marta → sarf ~2 marta, napor 4 marta → ~2 marta
    q_a = Spillway(100, 20, gate_height_m=6.0, gate_opening=0.2).discharge(100 + h)
    q_2a = Spillway(100, 20, gate_height_m=6.0, gate_opening=0.4).discharge(100 + h)
    assert 1.8 < q_2a / q_a < 2.05
    # to'liq ochiq (a ≥ 0.75·H) → erkin oqim
    assert sp.discharge_detail(100 + h)["regime"] == "erkin"


def test_reservoir_mass_balance_closed_with_level_dependent_spill():
    c = StorageCurve((100, 120, 140), (0, 50, 200))
    spec = ReservoirSpec(c, dead_level_m=105, normal_level_m=138, max_level_m=140,
                         other_outflow_m3s=3, spillway=SpillwaySpec(137, 10))
    s = ReservoirState(136.5, c.volume(136.5))
    total_in = total_out = 0.0
    dt = 3600
    for i in range(400):
        q_in = 300 + 100 * math.sin(i / 15)
        s2, f = step(s, spec, q_in, 60, dt)
        assert abs(f["mass_residual_m3"]) < 1e-3
        total_in += q_in * dt
        total_out += (f["turbine"] + f["spill"] + f["evap"] + spec.other_outflow_m3s) * dt
        s = s2
    assert s.volume_m3 - c.volume(136.5) == pytest.approx(total_in - total_out, rel=1e-9)
    # sathga bog'liq tashlama: bir qadamda boshi/oxiri o'rtachasi — boshidagi qiymatdan farq qiladi
    s0 = ReservoirState(137.5, c.volume(137.5))
    _, f = step(s0, spec, 2000, 0, dt)
    q_start = spec.spillway.discharge(137.5)
    assert f["spill"] > q_start and f["forced_spill"] == 0


def test_negative_volume_is_an_error_not_silent_zero():
    c = StorageCurve.prismatic(100, 150, 0.01)  # kichik ombor: 0.01 km²
    spec = ReservoirSpec(c, dead_level_m=101, normal_level_m=140, other_outflow_m3s=500)
    s = ReservoirState(102, c.volume(102))
    with pytest.raises(ValueError):
        step(s, spec, inflow=0, turbine_demand=0, dt_s=86400)


def test_flood_uses_shared_spillway_module():
    from ges_sim import flood
    from ges_sim.schema import parse

    p = {f.key: f.default for f in flood.FIELDS}
    r1 = flood.run(parse(flood.FIELDS, {**p, "spill_bays": 1}))
    r6 = flood.run(parse(flood.FIELDS, {**p, "spill_bays": 6}))
    assert r6["summary"]["max_level_m"] > r1["summary"]["max_level_m"]  # ko'proq siqilish
