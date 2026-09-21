"""J2/J11: yorilgan poydevor tahlili, bosh kuchlanishlar, dam_stability ↔ cracking izchilligi."""

import math

from ges_sim import catalog, cracking, dam_stability
from ges_sim.dam_stability import GAMMA_W, principal_stress, uplift


def _rect_dam(h1: float, B: float = 30.0, H: float = 60.0, gc: float = 24.0) -> dict:
    p = {f.key: f.default for f in dam_stability.FIELDS}
    p.update(
        {
            "height_m": H,
            "crest_width_m": B,
            "upstream_slope": 0.0,
            "downstream_slope": 0.0,
            "concrete_kn_m3": gc,
            "base_elev_m": 0.0,
            "headwater_m": h1,
            "tailwater_m": 0.0,
            "silt_m": 0.0,
            "ice_kn_m": 0.0,
            "drain_eff": 0.0,
            "cohesion_kpa": 0.0,
            "kh": 0.0,
            "kv": 0.0,
        }
    )
    return p


def _hand_crack(h1: float, B: float, H: float, gc: float) -> float:
    """Mustaqil hisob: to'g'ri to'rtburchak to'g'on, drenajsiz, yoriq ichida to'liq h₁,
    yorilmagan qismda uchburchak h₁→0. Shart: x_r = (B − L_c)/3 (yoriq uchida σ = 0)."""
    W = gc * B * H
    P = GAMMA_W * h1**2 / 2

    def x_r(lc: float) -> float:
        u_rect = GAMMA_W * h1 * lc
        u_tri = GAMMA_W * h1 * (B - lc) / 2
        V = W - u_rect - u_tri
        M = W * B / 2 - u_rect * (B - lc / 2) - u_tri * 2 * (B - lc) / 3 - P * h1 / 3
        return M / V

    lo, hi = 0.0, B
    for _ in range(200):
        mid = (lo + hi) / 2
        if x_r(mid) - (B - mid) / 3 > 0:
            hi = mid  # x_r katta → yoriq qisqaroq
        else:
            lo = mid
    return (lo + hi) / 2


def test_cracked_base_matches_hand_calculation():
    B, H, gc = 30.0, 60.0, 24.0
    p = _rect_dam(h1=58.0, B=B, H=H, gc=gc)
    r = dam_stability.analyze(p)
    assert r["s_heel_uncracked"] < 0  # yorilmagan holatda cho'zilish bor
    lc_hand = _hand_crack(58.0, B, H, gc)
    assert lc_hand > 1.0
    assert abs(r["crack_len"] - lc_hand) < 0.05, (r["crack_len"], lc_hand)
    assert abs(r["x_r"] - (B - r["crack_len"]) / 3) < 1e-3  # yoriq uchida σ = 0
    assert r["s_heel"] == 0.0 and r["s_toe"] > 0
    # ko'tarish bosimi yoriq bilan kattaroq, sirpanish zaxirasi kichikroq
    r0 = dam_stability.uplift(B, 58.0, 0.0, 0.0, 0.0, 0.0)[0]
    assert r["U"] > r0
    # ilashish faqat yorilmagan qismda
    p2 = {**p, "cohesion_kpa": 100.0}
    r2 = dam_stability.analyze(p2)
    assert abs(r2["fs_s"] - (100.0 * (B - r2["crack_len"]) + r2["sum_v"] * p["friction"]) / r2["sum_h"]) < 1e-6


def test_no_crack_when_resultant_in_middle_third():
    r = dam_stability.analyze(_rect_dam(h1=20.0))
    assert r["crack_len"] == 0.0 and r["s_heel"] > 0


def test_crack_beyond_drain_disables_drain():
    U_ok, _, pts = uplift(60.0, 50.0, 5.0, 6.0, 0.5, 0.0)
    U_cr, _, pts_cr = uplift(60.0, 50.0, 5.0, 6.0, 0.5, 10.0)
    assert U_cr > U_ok
    assert all(abs(h - 50.0) < 1e-9 for x, h in pts_cr if x <= 10.0)
    assert len(pts_cr) == 3  # drenaj nuqtasi yo'q (samarasiz)
    # yoriq drenajgacha yetmasa drenaj nuqtasi qoladi va h3 (B−L_c) bilan hisoblanadi
    _, _, pts_p = uplift(60.0, 50.0, 5.0, 6.0, 0.5, 3.0)
    assert len(pts_p) == 4 and abs(pts_p[2][1] - (5 + 0.5 * 45 * (60 - 6) / (60 - 3))) < 1e-9


def test_principal_stress_at_toe_exceeds_vertical_on_sloped_face():
    r = catalog.run("dam_stability", {})["summary"]
    d = {f.key: f.default for f in dam_stability.FIELDS}
    md = d["downstream_slope"]
    h2 = max(min(d["tailwater_m"] - d["base_elev_m"], d["height_m"]), 0.0)
    expected = principal_stress(r["sigma_toe_mpa"], md, GAMMA_W * h2 / 1000)
    assert abs(r["sigma_principal_toe_mpa"] - expected) < 0.01
    assert r["sigma_principal_toe_mpa"] > 1.4 * r["sigma_toe_mpa"]  # roadmap: +50 %


def test_dam_stability_and_cracking_agree_at_base():
    """Bir xil to'g'on (loyqa/muzsiz): cracking ning tag kesimi va dam_stability bir xil U va σ beradi."""
    common = {"silt_m": 0.0, "ice_kn_m": 0.0, "headwater_m": 905.0, "tailwater_m": 840.0}
    d = catalog.run("dam_stability", common)["summary"]
    c = catalog.run("cracking", {"headwater_m": 905.0, "tailwater_m": 840.0})
    cp = {f.key: f.default for f in cracking.FIELDS}
    dp = {f.key: f.default for f in dam_stability.FIELDS}
    for k in ("height_m", "crest_width_m", "upstream_slope", "downstream_slope", "drain_eff", "drain_x_m"):
        assert cp[k] == dp[k], k
    su0, spd0 = c["series"]["sigma_up"][0], c["series"]["sigma_principal_down"][0]
    assert abs(su0 - d["sigma_heel_mpa"]) < 0.03 * abs(d["sigma_heel_mpa"]) + 0.01
    assert abs(spd0 - d["sigma_principal_toe_mpa"]) < 0.03 * d["sigma_principal_toe_mpa"] + 0.01
    assert "sigma_principal_up" in c["series"] and c["field"]["illustrative"] is True


def test_jci_probability_formula():
    for idx, expected in ((1.5, 12), (1.2, 27), (1.0, 50)):
        p = 100 * (1 - math.exp(-((idx / 0.92) ** -4.29)))
        assert abs(p - expected) < 1.5
    th = cracking._thermal(
        {**{f.key: f.default for f in cracking.FIELDS}, "cement_kg_m3": 300, "restraint": 0.8},
        {"E": 30000, "Rbtn": 1.8},
    )
    exp = 100 * (1 - math.exp(-((th["index"] / 0.92) ** -4.29)))
    assert abs(th["probability_pct"] - exp) < 1.0
