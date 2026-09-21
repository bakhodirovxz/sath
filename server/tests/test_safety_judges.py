"""J1: xavfsizlik bahosi — ikkala sirpanish koeffitsienti, seysmik mezon, konyunktiv umumiy baho."""

from ges_server.sim import safety
from ges_sim import catalog


def test_stab_judge_fails_on_friction_only_even_if_cohesive_passes():
    # Roadmap holati: fs_sliding (c bilan) = 1.10 ≥ 1.1 o'tadi, faqat ishqalanish 0.81 — sirpanadi
    s = {"fs_overturning": 1.5, "fs_sliding": 1.10, "fs_sliding_friction_only": 0.81}
    p = {"req_overturning": 1.1, "req_sliding": 1.3, "req_sliding_friction": 1.1, "cohesion_kpa": 200}
    status, msg = safety._stab_judge(s, p)
    assert status == "fail" and "ishqalanish" in msg and "0.81" in msg
    # c = 0: ilashishli qiymat tekshirilmaydi, ishqalanish o'tsa ok
    s2 = {"fs_overturning": 2.0, "fs_sliding": 1.6, "fs_sliding_friction_only": 1.6}
    assert safety._stab_judge(s2, {**p, "cohesion_kpa": 0, "req_sliding_friction": 1.5})[0] == "ok"
    # c > 0 va ilashishli qiymat yuqori talabdan past → fail
    s3 = {"fs_overturning": 2.0, "fs_sliding": 1.8, "fs_sliding_friction_only": 1.6}
    st, m = safety._stab_judge(s3, {**p, "req_sliding": 2.0, "req_sliding_friction": 1.5})
    assert st == "fail" and "c = 200" in m


def test_seismic_judge_has_real_criterion():
    assert safety._seismic_judge({"pga_g": 2.0, "kh": 0.9, "ground": "A"}, {}, {"kh_critical": 0.3})[0] == "fail"
    assert safety._seismic_judge({"pga_g": 0.1, "kh": 0.1, "ground": "A"}, {}, {"kh_critical": 0.3})[0] == "ok"
    st, msg = safety._seismic_judge({"pga_g": 0.3, "kh": 0.2, "ground": "D"}, {}, {"kh_critical": 0.5})
    assert st == "warn" and "EC8" in msg
    assert safety._seismic_judge({"pga_g": 0.1, "kh": 0.1, "ground": "A"}, {}, {})[0] == "warn"


def _prefill_all(kind):
    return {"site": {}, "model": {}}


def test_run_all_incomplete_when_scenarios_skip():
    # Pasport bo'sh: toshqin ssenariylari sath–hajm egri chizig'isiz skip → umumiy baho yo'q
    res = safety.run_all(_prefill_all, {"normal_level_m": 900})
    assert res["counts"]["skip"] >= 4
    assert res["overall"] == "incomplete" and res["score"] is None
    assert "hisoblanmadi" in res["verdict"]
    seismic = next(r for r in res["rows"] if r["id"] == "seismic")
    assert seismic["status"] in ("ok", "warn", "fail") and "PGA" in seismic["message"]
    assert all("warnings" in r for r in res["rows"])


def test_run_all_conjunctive_fail():
    curve_e = [850, 870, 890, 910, 930]
    curve_v = [0, 50e6, 200e6, 500e6, 900e6]

    def prefill(kind):
        site = {"curve_elev": curve_e, "curve_vol": curve_v, "crest_m": 925, "initial_level_m": 900}
        if kind == "dam_stability":
            site = {"friction": 0.3, "cohesion_kpa": 0}  # sirpanadi
        return {"site": site, "model": {}}

    res = safety.run_all(prefill, {"normal_level_m": 900, "max_level_m": 910, "flood_01_m3s": 3000})
    if res["counts"]["skip"] == 0:
        assert res["overall"] == "fail" and res["score"] is not None
    assert any(r["id"] == "stab_static" and r["status"] == "fail" for r in res["rows"])


def test_dam_stability_default_cohesion_zero_and_both_requirements():
    r = catalog.run("dam_stability", {})["summary"]
    assert r["fs_sliding"] == r["fs_sliding_friction_only"]
    assert not r["warnings"]
    r2 = catalog.run("dam_stability", {"cohesion_kpa": 200})["summary"]
    assert r2["fs_sliding"] > r2["fs_sliding_friction_only"]
    assert any("sinov" in w for w in r2["warnings"])
