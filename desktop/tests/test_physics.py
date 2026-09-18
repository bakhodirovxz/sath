"""sath.physics — egizak vizualizatsiyasi formulalari (bpy siz)."""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import physics  # noqa: E402


def test_manning_depth_satisfies_formula():
    # b=6 m, S=0.0016, n=0.015, Q=11 m³/s → y ≈ 0.886 m; qayta qo'yganda Q qaytadi
    y = physics.manning_depth(11.0, 6.0, 0.0016, 0.015)
    assert 0.85 < y < 0.92, y
    assert physics.manning_depth(22.0, 6.0, 0.0016, 0.015) > y
    a = 6.0 * y
    q = a * (a / (6 + 2 * y)) ** (2 / 3) * math.sqrt(0.0016) / 0.015
    assert abs(q - 11.0) < 1e-3
    assert physics.manning_depth(0.0, 6.0, 0.001, 0.03) == 0.0


def test_thoma_cavitation_and_sync_speed():
    assert physics.synchronous_rpm(50, 24) == 250.0
    # Francis 25 MW, H=45 m, n=250: n_s = 250·√25000/45^1.25 ≈ 341 → σ_c ≈ 0.50; H_s=2 → σ=(10.1−0.24−2)/45=0.175 → kavitatsiya
    sp, sc, cav = physics.cavitation("Francis", 2.0, 45.0, 250.0, 25000.0)
    assert abs(sp - 0.1747) < 1e-3 and cav
    # ish g'ildiragi 6 m suv ostida → σ = 0.35 — hali ham σ_c dan kichik; H_s = −15 → yo'q
    assert not physics.cavitation("Francis", -15.0, 45.0, 250.0, 25000.0)[2]
    assert not physics.cavitation("Pelton", 5.0, 400.0, 500.0, 25000.0)[2]


def test_generator_efficiency_curve():
    assert abs(physics.generator_efficiency(30.0, 30.0) - 0.985) < 1e-9
    assert physics.generator_efficiency(3.0, 30.0) < physics.generator_efficiency(15.0, 30.0) < 0.985
    assert physics.generator_efficiency(0.0, 30.0) == 0.0


def test_penstock_path_and_samples_reach_outlet():
    p = physics.penstock_path(60.0, 40.0, 8.0, 6.0)
    dz = p["l1"] * math.sin(math.radians(40)) + 8.0 * (1 - math.cos(math.radians(40)))
    assert abs(-p["p3"][2] - dz) < 1e-9
    pts = physics.penstock_samples(60.0, 40.0, 8.0, 6.0, 25)
    assert len(pts) == 25 and pts[0] == (0.0, 0.0, 0.0)
    assert all(abs(a - b) < 1e-9 for a, b in zip(pts[-1], p["p3"], strict=True))
    # yoy nuqtalari markazdan R masofada
    a = p["alpha"]
    c = (p["p1"][1] + math.sin(a) * 8.0, p["p1"][2] + math.cos(a) * 8.0)
    for y, z in ((q[1], q[2]) for q in pts if p["l1"] < math.hypot(q[1], q[2]) < p["l1"] + 8.0 * a):
        assert abs(math.hypot(y - c[0], z - c[1]) - 8.0) < 1e-6
    straight = physics.penstock_samples(20.0, 0.0, 8.0, 6.0, 5)
    assert straight[-1] == (0.0, 0.0, 20.0)


def test_solve_penstock_hits_target():
    alpha, length = physics.solve_penstock(30.0, 50.0, 8.0, 6.0)
    p = physics.penstock_path(length, alpha, 8.0, 6.0)
    assert abs(p["p3"][1] - 50.0) < 1e-3 and abs(p["p3"][2] + 30.0) < 1e-3, p["p3"]
    assert 0 < alpha < 90


def test_seismic_displacement_and_envelope():
    # S_a = 0.5 g, T = 0.4 s → S_d = 0.5·9.81·(0.4/2π)² ≈ 19.9 mm
    assert abs(physics.spectral_displacement(0.5, 0.4) - 0.01987) < 1e-4
    assert physics.envelope(0) == 0 and physics.envelope(2) == 1.0 and physics.envelope(5) == 1.0
    assert 0 < physics.envelope(12) < 1 and physics.envelope(100) == 0.0
    assert physics.ground_motion(0.5, 0.4, 0.0) == 0.0
    assert abs(physics.ground_motion(0.5, 0.4, 2.1, scale=20)) <= 0.0199 * 20


def test_heat_color_gradient():
    assert physics.heat_color(20) == physics.heat_color(40)
    assert physics.heat_color(80)[1] > physics.heat_color(140)[1]  # yashil → qizil
    assert physics.heat_color(200) == physics.heat_color(140)
