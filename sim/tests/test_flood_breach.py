"""J6: to'g'on yorilishi ombor balansiga ulangan, qayir, indikativ quyi byef natijalari."""

from ges_sim import catalog, flood


def _breach(**kw):
    return catalog.run("flood", {"peak_m3s": 12000, "gate_opening": 0.0, "breach": "auto", **kw})


def test_breach_drains_reservoir_and_is_superposed_in_time():
    r = _breach()
    s, lv, br = r["summary"], r["series"]["level"], r["series"]["breach"]
    assert s["overtopped"] and s["breach_start_h"] is not None
    i0 = next(i for i, b in enumerate(br) if b > 0)
    assert abs(r["series"]["t"][i0] - s["breach_start_h"]) <= 0.5
    assert lv[-1] < lv[0] - 20 and lv[-1] <= r["breach"]["height_m"] + 850 + 0.5  # bo'shaydi
    assert max(lv) == s["max_level_m"] and lv.index(max(lv)) <= i0 + 12
    # ombor chiqimi = tashlama + yorilish + ... — quyi byef shu umumiy seriyani oladi
    assert max(r["series"]["outflow"]) >= max(br)
    assert s["breach_peak_m3s"] == round(max(br), 0)
    # regressiya bilan solishtirish va noaniqlik oralig'i
    assert r["breach"]["peak_range_m3s"][0] * 4 == r["breach"]["peak_range_m3s"][1]
    assert s["breach_peak_froehlich_m3s"] > 0


def test_no_breach_keeps_level_and_not_indicative():
    r = catalog.run("flood", {"breach": "none"})
    assert r["summary"]["downstream_indicative"] is False and max(r["series"]["breach"]) == 0
    assert r["summary"]["breach_start_h"] is None


def test_downstream_results_are_indicative_two_significant_figures():
    s = _breach()["summary"]
    assert s["downstream_indicative"] is True
    assert float(f"{s['downstream_peak_m3s']:.2g}") == s["downstream_peak_m3s"]
    assert float(f"{s['downstream_max_depth_m']:.2g}") == s["downstream_max_depth_m"]
    assert any("INDIKATIV" in w for w in s["warnings"])


def test_froehlich_range_warnings():
    # kichik ombor: V_w < 0.0139 mln m³
    r = catalog.run(
        "flood",
        {
            "curve_elev": [850, 852, 854],
            "curve_vol": [0, 3000, 8000],
            "initial_level_m": 853.5,
            "crest_m": 854,
            "spill_crest_m": 853.9,
            "spill_width_m": 1,
            "peak_m3s": 200,
            "breach": "force",
            "breach_bottom_m": 850,
        },
    )
    assert any("Froehlich" in w for w in r["summary"]["warnings"])


def test_floodplain_reduces_depth_and_compound_section_monotonic():
    d0 = _breach()["summary"]["downstream_max_depth_m"]
    d1 = _breach(fp_width_m=400)["summary"]["downstream_max_depth_m"]
    assert d1 < d0
    q = [flood.compound_discharge(y, 80, 3, 0.002, 0.035, 5, 400, 0.06) for y in (1, 4, 5, 6, 8, 12)]
    assert all(b > a for a, b in zip(q, q[1:], strict=False))
    # qayirsiz kompaund = oddiy trapetsiya
    y = flood.compound_depth(3000, 80, 3, 0.002, 0.035)
    assert abs(y - flood.manning_depth(3000, 80, 3, 0.002, 0.035)) < 1e-3
    assert not any("qayir" in w for w in _breach(fp_width_m=400)["summary"]["warnings"])
