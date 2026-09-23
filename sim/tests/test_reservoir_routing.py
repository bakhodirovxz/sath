"""SIM-08: sath-hovuz marshrutlash (modified Puls / trapetsiya implicit) — analitik yechim va yaqinlashish."""

import math

import pytest
from ges_sim.reservoir import (
    ReservoirSpec,
    ReservoirState,
    SpillwaySpec,
    StorageCurve,
    route_step,
    step,
)


def _linear(k: float, s0: float, inflow: float, t_end: float, dt: float) -> float:
    s = s0
    for _ in range(round(t_end / dt)):
        s = route_step(s, dt, inflow, lambda v: k * v)
    return s


def test_linear_reservoir_matches_exponential():
    """Chiziqli ombor O = k·S, I = const: S(t) = I/k + (S₀ − I/k)·e^(−kt) (Chow va b. 1988, 8.4)."""
    k, s0, inflow, t_end = 1 / 36000, 5e6, 200.0, 86400.0
    exact = inflow / k + (s0 - inflow / k) * math.exp(-k * t_end)
    s = _linear(k, s0, inflow, t_end, 3600.0)
    assert s == pytest.approx(exact, rel=2e-3)


def test_linear_reservoir_second_order_convergence():
    k, s0, inflow, t_end = 1 / 36000, 5e6, 200.0, 86400.0
    exact = inflow / k + (s0 - inflow / k) * math.exp(-k * t_end)
    errs = [abs(_linear(k, s0, inflow, t_end, dt) - exact) for dt in (14400.0, 7200.0, 3600.0, 1800.0)]
    assert errs[0] > errs[1] > errs[2] > errs[3]
    orders = [math.log2(a / b) for a, b in zip(errs, errs[1:], strict=False)]
    assert all(1.8 < o < 2.2 for o in orders), orders


def test_stiff_large_step_stays_bounded():
    # Δt·k = 10 (aniq Eyler bu yerda tebranib portlardi); trapetsiya S ni muvozanat atrofida saqlaydi
    k, inflow = 1 / 3600, 100.0
    s = route_step(0.0, 36000.0, inflow, lambda v: k * v)
    assert 0 < s < 2 * inflow / k


def _spec(evap: float = 0.0):
    # Konus shaklidagi ombor: yuza sath bilan o'sadi (bug'lanish S ga bog'liq)
    curve = StorageCurve((100, 110, 120, 130), (0.0, 20.0, 60.0, 120.0))
    return ReservoirSpec(
        curve=curve,
        dead_level_m=102,
        normal_level_m=125,
        max_level_m=140,
        spillway=SpillwaySpec(crest_m=122, width_m=30, coefficient=0.49),
        evaporation_mm_day=evap,
    )


def _route(dt: float, t_end: float = 1.5 * 86400.0, evap: float = 0.0):
    spec = _spec(evap)
    st = ReservoirState(123.0, spec.curve.volume(123.0))  # ostonadan yuqori — Q(H) silliq
    res = 0.0
    for i in range(round(t_end / dt)):
        t = (i + 0.5) * dt  # qadam o'rtasidagi kirish (qadam o'rtachasiga 2-tartibli yaqinlashish)
        inflow = 800.0 + 600.0 * math.sin(math.pi * t / (4 * 86400.0))  # ko'tarilayotgan toshqin
        st, fl = step(st, spec, inflow, 150.0, dt)
        res = max(res, abs(fl["mass_residual_m3"]))
    return st, res


def test_step_converges_with_dt_and_closes_mass_balance():
    ref, _ = _route(300.0, evap=8.0)
    e = [abs(_route(dt, evap=8.0)[0].volume_m3 - ref.volume_m3) for dt in (10800.0, 5400.0, 2700.0)]
    assert e[0] > e[1] > e[2]
    assert e[0] / e[1] > 3.0 and e[1] / e[2] > 3.0  # ~2-tartib (4×)
    _, res = _route(3600.0, evap=8.0)
    assert res < 1e-3


def test_evaporation_uses_area_at_both_ends():
    spec = _spec(evap=10.0)
    st = ReservoirState(105.0, spec.curve.volume(105.0))
    _, fl = step(st, spec, 0.0, 0.0, 86400.0)
    # sath pasayadi → o'rtacha bug'lanish qadam boshidagidan biroz kichik, lekin musbat
    a0 = (spec.curve.volume(105.1) - spec.curve.volume(104.9)) / 0.2
    e0 = 10.0 / 1000 / 86400 * a0
    assert 0 < fl["evap"] <= e0 + 1e-12


def test_turbine_curtailed_exactly_at_dead_level():
    spec = _spec()
    st = ReservoirState(102.5, spec.curve.volume(102.5))
    new, fl = step(st, spec, 10.0, 500.0, 86400.0)
    assert new.elev_m == pytest.approx(102.0, abs=1e-6)
    assert 0 < fl["turbine"] < 500 and fl["curtailed"] > 0
