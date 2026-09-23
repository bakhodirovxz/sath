"""SIM-01: kritik Toma soni — yagona formula (ges_sim.cavitation), server va Blender bir xil."""

import filecmp
import importlib.util
from pathlib import Path

import pytest
from ges_sim import cavitation as cav

ROOT = Path(__file__).resolve().parents[2]


def test_francis_ns200_bansal():
    # 0.625·(200/380.78)² = 0.1724 (eski server formulasi 0.0173 — 10× past edi)
    assert cav.sigma_critical("Francis", 200) == pytest.approx(0.1724, abs=1e-3)
    # 0.0432·(n_s/100)² bilan ekvivalent (Blenderdagi eski ko'rinish)
    assert cav.sigma_critical("Francis", 341) == pytest.approx(0.0432 * 3.41**2, rel=0.01)


def test_kaplan_includes_one_over_7_5():
    # 0.28 + (600/380.78)³/7.5 = 0.28 + 3.912/7.5 = 0.8016
    assert cav.sigma_critical("Kaplan", 600) == pytest.approx(0.8016, abs=2e-3)
    assert cav.sigma_critical("Bulb", 600) == cav.sigma_critical("kaplan", 600)
    # de Siervo & de Leva (1977): 6.40e-5·600^1.46 ≈ 0.73 — ±15 % ichida
    assert abs(cav.sigma_critical("Kaplan", 600) / (6.40e-5 * 600**1.46) - 1) < 0.15


def test_pelton_and_degenerate():
    assert cav.sigma_critical("Pelton", 30) == 0.0
    assert cav.sigma_critical("Francis", 0) == 0.0
    assert cav.specific_speed(0, 1000, 50) == 0.0


def test_specific_speed_metric():
    # n=250 ayl/min, P=25 MVt, H=45 m → 250·√25000/45^1.25 ≈ 339
    assert cav.specific_speed(250, 25000, 45) == pytest.approx(339.15, abs=0.1)


def test_francis_within_literature_scatter():
    # de Siervo & de Leva (1976) bilan ±20 %…2× oralig'ida; USBR Monograph 20 dan yuqori (konservativ)
    for ns in (100, 200, 300):
        s = cav.sigma_critical("Francis", ns)
        assert 7.54e-5 * ns**1.41 * 0.8 < s < 2 * 7.54e-5 * ns**1.41
        assert ns**1.64 / 50327 < s


def test_blender_copy_identical_and_server_uses_same():
    shared = ROOT / "desktop" / "blender" / "sath" / "shared" / "cavitation.py"
    assert filecmp.cmp(ROOT / "sim" / "ges_sim" / "cavitation.py", shared, shallow=False), (
        "python desktop/build/sync_blender.py"
    )
    spec = importlib.util.spec_from_file_location("blender_cav", shared)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from ges_server.monitoring import health

    for t, ns in (("Francis", 200), ("Kaplan", 600), ("Pelton", 20), ("Francis", 380)):
        assert mod.sigma_critical(t, ns) == health.thoma_critical(t, ns) == cav.sigma_critical(t, ns)
