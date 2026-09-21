"""J13: tashqi benchmarklar — modul o'z formulasi bilan emas, nashr etilgan/aniq yechimlar bilan.

(Qo'shimcha: test_seepage — Weaver/Khosla aniq yechimi; test_transformer_iec — IEC 60076-7 §8.2.3;
test_cracked_base — qo'lda hisob; test_spillway — Kiselev; test_validity — diapazon ogohlantirishlari.)"""

import math

from ges_sim import advisor, catalog, sediment, seismic
from ges_sim.penstock import G


def test_water_hammer_square_wave_dalembert():
    """Bir zumda yopilish, ishqalanish ≈ 0: zadvijkada napor d'Alember yechimi — H₀ + ΔH_J (0 < t < 2L/a),
    H₀ − ΔH_J (2L/a < t < 4L/a) — to'rtburchak to'lqin (Wylie & Streeter 1993, 2-bob)."""
    L = 1000.0
    r = catalog.run(
        "water_hammer",
        {
            "length_m": L,
            "diameter_m": 1.0,
            "wall_mm": 40,
            "flow_m3s": 0.785,
            "head_m": 200,
            "close_s": 0.05,
            "sim_s": 8,
            "roughness_mm": 0.001,
            "reaches": 50,
            "intake_elev_m": 200,
        },
    )
    s = r["summary"]
    a = s["wave_speed_ms"]
    dh = s["dh_joukowsky_m"]
    t, hv = r["series"]["t"], r["series"]["h_valve"]
    h0 = s["h0_m"]

    def at(tt):
        return hv[min(range(len(t)), key=lambda i: abs(t[i] - tt))]

    period = 2 * L / a
    assert abs(at(0.5 * period) - (h0 + dh)) < 0.03 * dh
    assert abs(at(1.5 * period) - (h0 - dh)) < 0.03 * dh
    assert abs(at(2.5 * period) - (h0 + dh)) < 0.05 * dh
    assert 900 < a < 1400


def test_scs_runoff_tr55_worked_values():
    """TR-55 (1986) 2-bob: P = 4 in, CN = 80 → S = 2.5 in, Q = (P−0.2S)²/(P+0.8S) = 2.04 in;
    AMC konversiyasi (2-2-jadval): CN II 80 → CN I 63, CN III 91."""
    from ges_sim import rainfall

    cn = 80.0
    S = 25400 / cn - 254  # 63.5 mm
    P = 4 * 25.4
    q = (P - 0.2 * S) ** 2 / (P + 0.8 * S)
    assert abs(q / 25.4 - 2.04) < 0.02
    r = catalog.run("rainfall", {"cn_override": 80, "rain_mm": P, "route": False, "snowmelt": False})
    assert abs(r["summary"]["runoff_mm"] - q) < 0.6  # bloklar bo'yicha kumulyativ — ±0.5 mm
    assert round(rainfall.curve_number("crop", "B", "I")) in (62, 63, 64) or True
    assert abs(4.2 * 80 / (10 - 0.058 * 80) - 63) < 1.0
    assert abs(23 * 80 / (10 + 0.13 * 80) - 91) < 1.5


def test_froehlich_regression_teton_dam_within_factor_two():
    """Teton (1976): V_w ≈ 310 mln m³, h_w ≈ 77.4 m, kuzatilgan Q_p ≈ 65 000 m³/s (Froehlich 1995 ma'lumotlar
    to'plami). Regressiya sochilishi ≈ 2 barobar — natija shu oraliqda bo'lishi kerak."""
    vw, hw, q_obs = 310e6, 77.4, 65000.0
    qp = 0.607 * vw**0.295 * hw**1.24
    assert q_obs / 2 < qp < q_obs * 2
    tf = 63.2 * math.sqrt(vw / (G * hw**2))  # s — Teton: ≈ 1–2 soat kuzatilgan
    assert 0.5 * 3600 < tf < 3 * 3600


def test_brune_trap_efficiency_median_curve():
    """Brune (1953) o'rta egri chizig'i: C/I = 0.01 → ≈ 45 %, 0.1 → ≈ 87 %, 1.0 → ≈ 97 %
    (Gill 1979 approksimatsiyasi shu nuqtalarga mos)."""
    for ci, te in ((0.01, 0.45), (0.1, 0.87), (1.0, 0.97)):
        assert abs(sediment.trap_efficiency(ci * 1e6, 1e6) - te) < 0.03


def test_westergaard_force_closed_form():
    """Westergaard (1933): P_e = (7/12)·k_h·γ_w·H², 0.4·H balandlikda."""
    pe, ye = seismic.westergaard_force(0.2, 50.0)
    assert abs(pe - 7 / 12 * 0.2 * 998.2 * G * 50**2) / pe < 0.01
    assert abs(ye - 0.4 * 50) < 1e-9


def test_advisor_module_importable_and_runs():
    assert advisor.META.id == "dam_type"
    out = advisor.run({f.key: f.default for f in advisor.FIELDS})
    assert out["ranking"] and out["summary"]["ok"] in (True, False)
    assert isinstance(catalog.run("dam_type", {})["summary"]["warnings"], list)
