"""J8: IEC 60076-7:2018 ikki shoxli issiq nuqta modeli — §8.2.3 eksponensial yechimi bilan tekshiruv.

Standartning differensial (8.2.2) va eksponensial (8.2.3, (14)–(16)) shakllari ekvivalent; testda
eksponensial shakl mustaqil amalga oshirilib, raqamli integratsiya bilan solishtiriladi."""

import math

from ges_sim import catalog, transformer


def _exp_solution(K1, K2, t_min, ta, cooling="ONAF", R=6.0):
    x, y, dor, dhr, tau_o, tau_w, k11, k21, k22 = transformer.COOLING[cooling]
    oi = ((1 + R * K1**2) / (1 + R)) ** x * dor
    of = ((1 + R * K2**2) / (1 + R)) ** x * dor
    hi = K1**y * dhr
    hf = K2**y * dhr
    f1 = 1 - math.exp(-t_min / (k11 * tau_o))
    f2 = k21 * (1 - math.exp(-t_min / (k22 * tau_w))) - (k21 - 1) * (
        1 - math.exp(-t_min / (tau_o / k22))
    )
    theta_o = ta + oi + (of - oi) * f1
    d_h = hi + (hf - hi) * f2
    return theta_o, theta_o + d_h


def test_two_branch_model_matches_iec_exponential_solution():
    # 0.6 → 1.5 p.u. sakrash (soat 12 da), ONAF, 30 °C; S = 100 MVA, cos φ = 0.9 → P = K·90 MW
    prof = [0.6 * 90] * 12 + [1.5 * 90] * 12
    r = catalog.run(
        "transformer",
        {"cooling": "ONAF", "load_profile_mw": prof, "ambient_c": 30, "days": 3, "rated_mva": 100},
    )
    t = r["series"]["t"]
    th = r["series"]["hot_spot_c"]
    to = r["series"]["top_oil_c"]
    for t_after in (15, 30, 60, 120, 300):
        idx = t.index(round(12 + t_after / 60, 2))
        # seriya nuqtasi m daqiqadagi yangilanishdan keyin → sakrashdan t_after + 1 min o'tgan holat
        theta_o, theta_h = _exp_solution(0.6, 1.5, t_after + 1, 30.0)
        assert abs(to[idx] - theta_o) < 0.15, (t_after, to[idx], theta_o)
        assert abs(th[idx] - theta_h) < 0.15, (t_after, th[idx], theta_h)
    # Ikki shoxli model: issiq nuqta gradienti statsionar qiymatdan vaqtincha oshib ketadi (k21 = 2)
    _, _, _, dhr, _, _, _, k21, _ = transformer.COOLING["ONAF"]
    d_h = [h - o for h, o in zip(th, to, strict=False)]
    assert max(d_h) > 1.05 * (1.5**1.3 * dhr)
    # Roadmap holati: bir shoxli model 151 °C, IEC ikki shoxli ≈ 157 °C
    assert r["summary"]["hot_spot_max_c"] > 155


def test_life_keys_and_units():
    r = catalog.run("transformer", {})["summary"]
    assert abs(r["loss_of_life_h"] - r["aging_relative"] * 24) < 0.05
    assert r["life_hours_nominal"] == 180000
    assert "loss_of_life_days" not in r
    k = catalog.run("transformer", {"paper": "kraft"})["summary"]
    assert k["life_hours_nominal"] == 65000
    custom = catalog.run("transformer", {"life_hours": 120000})["summary"]
    assert custom["life_hours_nominal"] == 120000
    assert abs(custom["life_years_at_this_load"] - 120000 / custom["loss_of_life_h"] / 365) < 0.1
