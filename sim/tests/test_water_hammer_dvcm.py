"""SIM-05: suv ustuni uzilishi — DVCM (Wylie & Streeter 1993, 8-bob; Bergant va b. 2006).

Benchmark: ishqalanishsiz gorizontal quvur, zadvijka bir zumda yopiladi, ΔH_J > H₀ − H_v. Zadvijka oldida
bitta bo'shliq t = 2L/a da ochiladi; to'lqin tahlili (d'Alember) bilan aniq yechim:
  zadvijkaga n-oraliqda (n·T … (n+1)·T, T = 2L/a) keladigan holat (H₀, q_n), q_n = 2(n−1)·ΔQ − Q₀,
  ΔQ = (H₀ − H_v)/B;  bo'shliq bo'lganda zadvijka tomondagi sarf Qu_n = ΔQ + q_n,
  d∀/dt = −Qu_n = Q₀ − (2n−1)·ΔQ;  ∀ = 0 bo'lganda yopiladi (m-oraliqda, t_c),
  keyin zadvijkada H = H₀ + B·q_m (t_c … (m+1)T) va H₀ + B·q_{m+1} ((m+1)T … t_c + T).
"""

import math

import pytest
from ges_sim import catalog, water_hammer
from ges_sim.penstock import G

L = 600.0


def _params(**kw):
    p = catalog.parse(
        "water_hammer",
        {
            "length_m": L,
            "diameter_m": 1.0,
            "wall_mm": 40,
            "flow_m3s": 0.785,
            "head_m": 20,
            "close_s": 0.05,
            "sim_s": 8,
            "roughness_mm": 0.001,
            "reaches": 60,
            "profile_z": [0, 0],
            "valve_elev_m": 0,
        },
    )
    p.update(kw)
    return p


def _analytic(h0: float, a: float, q0: float):
    area = math.pi / 4
    b = a / (G * area)
    hv = water_hammer.H_VAPOR - water_hammer.H_ATM
    T = 2 * L / a
    dq = (h0 - hv) / b
    vol, t, n, vmax = 0.0, T, 1, 0.0
    while True:
        rate = q0 - (2 * n - 1) * dq
        if vol + rate * T <= 0:
            tc = t + vol / (-rate)
            break
        vol += rate * T
        vmax = max(vmax, vol)
        t += T
        n += 1
    q = [None] + [2 * (k - 1) * dq - q0 for k in range(1, n + 3)]
    return {"T": T, "hv": hv, "vmax": vmax, "tc": tc, "m": n, "h1": h0 + b * q[n], "h2": h0 + b * q[n + 1]}


def test_dvcm_matches_wave_analysis_frictionless(monkeypatch):
    monkeypatch.setattr(water_hammer, "friction_factor", lambda *a: 0.0)
    p = _params(close_s=1e-4)  # bir qadamdan tez — keskin front
    r = water_hammer.run(p)
    s = r["summary"]
    an = _analytic(s["h0_m"], s["wave_speed_ms"], 0.785)
    t, hv = r["series"]["t"], r["series"]["h_valve"]
    dt = t[1] - t[0]
    # birinchi uzilish — zadvijkada, t = 2L/a da
    assert s["column_separation"] is True
    assert s["column_sep_x_m"] == pytest.approx(L)
    assert abs(s["column_sep_t_s"] - an["T"]) <= 1.5 * dt
    # bo'shliqning maksimal hajmi va yopilish vaqti
    assert s["cavity_max_m3"] == pytest.approx(an["vmax"], rel=0.01)
    i_c = next(i for i, tt in enumerate(t) if tt > an["T"] + 0.1 and hv[i] > an["hv"] + 1.0)
    assert abs(t[i_c] - an["tc"]) <= 2 * dt
    # yopilishdan keyingi bosim platolari (ustunlar qo'shilishi)
    mid1 = (an["tc"] + (an["m"] + 1) * an["T"]) / 2
    mid2 = ((an["m"] + 1) * an["T"] + an["tc"] + an["T"]) / 2

    def at(tt):
        return hv[min(range(len(t)), key=lambda i: abs(t[i] - tt))]

    assert at(mid1) == pytest.approx(an["h1"], rel=0.01)
    assert at(mid2) == pytest.approx(an["h2"], rel=0.01)
    # bug' bosimidan past napor yo'q (eski — elastik — yechim −240 m gacha tushardi)
    assert min(hv) >= an["hv"] - 1e-6
    assert s["p_abs_min_m"] == pytest.approx(water_hammer.H_VAPOR, abs=0.01)


def test_column_separation_warning_structured():
    r = catalog.run("water_hammer", _params())
    s = r["summary"]
    assert s["column_separation"] and s["cavitation_risk"] and not s["ok"]
    w = [x for x in s["warnings"] if x.startswith("suv ustuni uzilishi")]
    assert len(w) == 1 and "natija bu nuqtadan keyin ishonchsiz" in w[0]
    assert f"t = {s['column_sep_t_s']:.3f} s" in w[0]
    assert s["cavity_max_m3"] > 0 and s["column_sep_nodes"] >= 1


def test_no_separation_default_case_unchanged():
    s = catalog.run("water_hammer", {})["summary"]
    assert s["column_separation"] is False and s["column_sep_t_s"] is None
    assert s["cavity_max_m3"] == 0.0
    assert not any(w.startswith("suv ustuni") for w in s["warnings"])
    # DVCM dan oldingi elastik yechim bilan bir xil (uzilish bo'lmasa algoritm o'zgarmaydi)
    assert s["h_max_m"] == pytest.approx(124.22, abs=0.01)
    assert s["h_min_m"] == pytest.approx(55.86, abs=0.01)


def test_high_point_profile_separates_at_summit():
    s = catalog.run(
        "water_hammer",
        {"profile_z": [950, 948, 960, 930, 900], "valve_elev_m": 900, "head_m": 80, "close_s": 2},
    )["summary"]
    assert s["column_separation"] is True
    # quvur 300 m, profil nuqtalari 75 m oraliqda — cho'qqi (960 m) x = 150 m atrofida
    assert 75 <= s["column_sep_x_m"] <= 225
