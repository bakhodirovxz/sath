"""Yangi simulyatsiya modullari: analitik tekshiruvlar va katalog."""

import math

import pytest
from ges_sim import catalog, custom, dam_stability, flood, seismic, water_hammer
from ges_sim.penstock import G


def test_catalog_lists_all_kinds_with_fields():
    items = catalog.catalog()
    ids = {i["id"] for i in items}
    assert {
        "water_hammer",
        "surge_tank",
        "dam_stability",
        "seepage",
        "seismic",
        "flood",
        "landslide",
        "sediment",
        "hydro",
        "cfd",
        "custom",
    } <= ids
    for it in items:
        assert it["title"] and it["group"] in catalog.GROUPS
        if not it["custom_ui"]:
            assert it["fields"], it["id"]
            for f in it["fields"]:
                assert f["key"] and f["label"] and f["type"]


def test_every_kind_runs_with_defaults():
    for k in catalog.REGISTRY:
        r = catalog.run(k, {})
        assert "summary" in r and "verdict" in r["summary"] and "ok" in r["summary"], k
        assert "series" in r and all(isinstance(v, list) for v in r["series"].values()), k


def test_parse_validates_ranges_and_types():
    with pytest.raises(ValueError, match="kamida"):
        catalog.run("water_hammer", {"length_m": 1})
    with pytest.raises(ValueError, match="son"):
        catalog.run("water_hammer", {"length_m": "abc"})
    with pytest.raises(ValueError):
        catalog.run("seismic", {"ground": "Z"})
    with pytest.raises(ValueError, match="Noma'lum"):
        catalog.run("nope", {})


# --- Gidravlik zarba ---
def test_wave_speed_korteweg():
    # Po'lat D=1 m, e=10 mm: a = 1466 / sqrt(1 + 2.15e9/2.07e11 * 100) ≈ 1023 m/s
    a = water_hammer.wave_speed(1.0, 0.01, 2.07e11)
    assert 1010 < a < 1035


def test_water_hammer_instant_closure_matches_joukowsky():
    """Juda tez yopilish (T_c ≪ 2L/a), ishqalanishsiz deyarli: MOC maksimal ΔH ≈ a·V0/g."""
    r = catalog.run(
        "water_hammer",
        {
            "length_m": 1000,
            "diameter_m": 1.0,
            "wall_mm": 10,
            "flow_m3s": 0.785,
            "head_m": 200,
            "close_s": 0.1,
            "sim_s": 6,
            "roughness_mm": 0.001,
            "reaches": 40,
        },
    )
    s = r["summary"]
    assert s["closure"].startswith("tez")
    assert abs(s["dh_max_m"] - s["dh_joukowsky_m"]) / s["dh_joukowsky_m"] < 0.05
    # Halqa kuchlanish = p·D/(2e)
    p_pa = 998.2 * G * s["h_max_m"]
    assert abs(s["stress_mpa"] - p_pa * 1.0 / (2 * 0.01) / 1e6) < 0.5


def test_water_hammer_slow_closure_below_michaud():
    r = catalog.run("water_hammer", {"length_m": 500, "close_s": 20, "flow_m3s": 30})
    s = r["summary"]
    assert s["closure"].startswith("sekin")
    assert 0 < s["dh_max_m"] <= s["dh_theory_m"] * 1.05
    assert len(r["profile"]["x"]) == 21


# --- Minora ---
def test_surge_tank_frictionless_upsurge_close_to_theory():
    r = catalog.run(
        "surge_tank", {"roughness_mm": 0.001, "minor_k": 0.0, "change_s": 0.5, "sim_s": 400}
    )
    s = r["summary"]
    assert abs(s["z_max_m"] - s["z_max_theory_m"]) / s["z_max_theory_m"] < 0.05
    assert s["thoma_ratio"] > 1


# --- To'g'on ---
def test_dam_stability_hand_calc():
    p = {f.key: f.default for f in dam_stability.FIELDS}
    p.update(
        {
            "height_m": 80,
            "crest_width_m": 8,
            "upstream_slope": 0.0,
            "downstream_slope": 0.8,
            "concrete_kn_m3": 24,
            "base_elev_m": 0,
            "headwater_m": 75,
            "tailwater_m": 0,
            "silt_m": 0,
            "drain_eff": 0.0,
            "kh": 0.0,
            "cohesion_kpa": 0.0,
            "friction": 0.75,
        }
    )
    r = dam_stability.analyze(p)
    B = 8 + 0.8 * 80  # 72
    W = 24 * (8 + B) / 2 * 80
    U = 9.81 * 75 * B / 2  # uchburchak epyura
    Pw = 9.81 * 75**2 / 2
    assert abs(r["B"] - B) < 1e-9
    assert abs(r["W"] - W) < 1e-6
    assert abs(r["U"] - U) < 1e-6
    assert abs(r["sum_h"] - Pw) < 1e-6
    assert abs(r["fs_s"] - (W - U) * 0.75 / Pw) < 1e-6
    # Ag'darilish: momentlar mos
    assert 1 < r["fs_o"] < 5
    out = dam_stability.run(p)
    assert out["summary"]["ok"] in (True, False)
    assert len(out["series"]["level"]) == 41 and len(out["seismic_scan"]["kh"]) == 26


def test_dam_stability_seismic_reduces_safety():
    a = catalog.run("dam_stability", {"kh": 0.0})["summary"]
    b = catalog.run("dam_stability", {"kh": 0.2})["summary"]
    assert b["fs_sliding"] < a["fs_sliding"] and b["fs_overturning"] < a["fs_overturning"]
    c = catalog.run("dam_stability", {"headwater_m": 930})["summary"]  # gerbdan yuqori
    assert "gerbdan" in c["verdict"]


# --- Zilzila ---
def test_ec8_spectrum_plateau_and_period():
    assert abs(seismic.spectrum(0.3, 0.2, "A") - 0.2 * 2.5) < 1e-9
    assert seismic.spectrum(1.0, 0.2, "A") < seismic.spectrum(0.3, 0.2, "A")
    # Chopra: H=100 m, E=25 GPa → T1 ≈ 0.24 s (bo'sh ombor)
    assert abs(seismic.dam_period(100, 25000) - 0.24) < 0.01
    assert seismic.pga_from_intensity(9) == 0.4
    r = catalog.run("seismic", {"intensity": "9"})["summary"]
    assert r["pga_g"] == 0.4 and 0.2 < r["kh"] <= 0.25


# --- Toshqin ---
def test_flood_mass_balance_and_attenuation():
    r = catalog.run("flood", {"breach": "none"})
    s = r["summary"]
    assert s["peak_outflow_m3s"] < s["peak_inflow_m3s"]
    assert s["max_level_m"] > 905 and s["freeboard_m"] > 0
    # Hajm balansi: ΣI·dt − ΣO·dt ≈ ΔS
    ser = r["series"]
    dt = (ser["t"][1] - ser["t"][0]) * 3600
    from ges_sim.reservoir import StorageCurve

    c = StorageCurve((850, 870, 890, 905, 915), (0, 60, 220, 480, 700))
    ds = c.volume(ser["level"][-1]) - c.volume(905)
    net = (sum(ser["inflow"]) - sum(ser["outflow"])) * dt
    assert abs(net - ds) / max(abs(ds), 1) < 0.05


def test_flood_overtopping_triggers_breach_and_downstream_wave():
    r = catalog.run("flood", {"peak_m3s": 12000, "gate_opening": 0.0, "breach": "auto"})
    s = r["summary"]
    assert s["overtopped"] and s["breach_peak_m3s"] > 0 and r["breach"]["width_m"] > 0
    assert s["downstream_peak_m3s"] > s["peak_outflow_m3s"] * 0.5
    assert s["downstream_max_depth_m"] > 5


def test_manning_depth_roundtrip():
    y = flood.manning_depth(500, 50, 2, 0.001, 0.03)
    a = (50 + 2 * y) * y
    pw = 50 + 2 * y * math.sqrt(5)
    q = a * (a / pw) ** (2 / 3) * math.sqrt(0.001) / 0.03
    assert abs(q - 500) < 0.5


# --- Ko'chki ---
def test_landslide_impulse_wave_scaling():
    small = catalog.run("landslide", {"volume_m3": 50000})["summary"]
    big = catalog.run("landslide", {"volume_m3": 2000000})["summary"]
    assert big["a_max_m"] > small["a_max_m"]
    far = catalog.run("landslide", {"distance_m": 5000})["summary"]
    near = catalog.run("landslide", {"distance_m": 800})["summary"]
    assert far["a_at_dam_m"] < near["a_at_dam_m"]
    with pytest.raises(ValueError, match="harakatlanmaydi"):
        catalog.run("landslide", {"friction_deg": 40, "slope_deg": 30})


# --- Loyqa ---
def test_sediment_life_decreases_with_load():
    a = catalog.run("sediment", {"concentration_kg_m3": 0.5})["summary"]
    b = catalog.run("sediment", {"concentration_kg_m3": 3.0})["summary"]
    assert (a["years_dead"] or 999) > (b["years_dead"] or 0)
    assert 0 < a["te0_pct"] <= 100


# --- Maxsus ---
def test_custom_safe_evaluator_rejects_dangerous():
    for bad in (
        "__import__('os')",
        "open('x')",
        "a.__class__",
        "[x for x in range(3)]",
        "lambda: 1",
        "'abc'",
    ):
        with pytest.raises(ValueError):
            custom.compile_expr(bad)


def test_custom_template_runs_and_checks():
    t = custom.example_template()
    r = custom.run(t, {"Q_in": 50, "Q_turb": 100})
    assert r["summary"]["H_min"] < 880 and not r["summary"]["ok"]
    assert len(r["series"]["H"]) == 365
    t2 = {
        "inputs": [{"key": "k", "default": 0.1}],
        "steps": 10,
        "dt": 1,
        "init": {"x": "1"},
        "step": [{"target": "x", "expr": "x * exp(-k*dt)"}],
        "outputs": ["x"],
        "summary": {"x_end": "last(series.x)"},
    }
    r2 = custom.run(t2, {})
    assert abs(r2["summary"]["x_end"] - math.exp(-1.0)) < 1e-6
    with pytest.raises(ValueError):
        custom.validate_template({"steps": 10**9})


# --- Materiallar, yorilish, maslahatchi ---
def test_materials_catalog():
    from ges_sim import materials

    c = materials.catalog()
    assert any(x["id"] == "B25" and x["Rb"] == 14.5 for x in c["concrete"])
    assert materials.steel("s355")["yield"] == 345 and materials.concrete("nope")["name"] == "B20"
    assert len(c["zones"]) >= 5


def test_cracking_tension_appears_with_seismic_and_high_water():
    a = catalog.run("cracking", {})["summary"]
    b = catalog.run("cracking", {"kh": 0.35, "headwater_m": 912})
    assert a["max_tension_mpa"] == 0 and b["summary"]["max_tension_mpa"] > 0
    assert any("tovon" in x["where"] for x in b["prone"])
    assert len(b["series"]["level"]) == len(b["series"]["sigma_up"]) > 30
    # issiqlik: sement ko'p → indeks tushadi
    hi = catalog.run("cracking", {"cement_kg_m3": 320, "cement_type": "cem1"})["thermal"]
    lo = catalog.run("cracking", {"cement_kg_m3": 150, "cement_type": "lowheat"})["thermal"]
    assert hi["index"] < 1.2 < lo["index"]
    e = catalog.run(
        "cracking", {"dam_type": "earth", "settlement_pct": 2.5, "abutment_slope_deg": 70}
    )
    assert "cho'kish" in e["summary"]["verdict"] and any(
        "abutment" in x["where"] for x in e["prone"]
    )


def test_dam_type_advisor_rules():
    narrow_rock = catalog.run(
        "dam_type", {"foundation": "rock_hard", "crest_length_m": 150, "height_m": 120}
    )
    assert narrow_rock["ranking"][0]["type"] == "arch"
    wide_clay = catalog.run(
        "dam_type", {"foundation": "clay", "crest_length_m": 1500, "height_m": 30}
    )
    assert wide_clay["ranking"][0]["type"] in ("earth", "rockfill")
    assert all(k in wide_clay["ranking"][0] for k in ("good", "bad", "cracks", "reasons"))
    gravity_on_sand = next(r for r in wide_clay["ranking"] if r["type"] == "gravity")
    assert gravity_on_sand["verdict"] == "tavsiya etilmaydi"


def test_site_maps_materials_into_cracking():
    from ges_sim import site

    st = {**site.defaults(), "concrete_class": "B30", "soil": "rock", "dam_length_m": 200}
    v = catalog.site_values("cracking", st)
    assert v["concrete_class"] == "B30"
    assert catalog.site_values("dam_type", st)["foundation"] == "rock_hard"


# --- Regulyator dinamikasi, dispatch ---
def test_governor_load_step_and_rejection():
    a = catalog.run("governor", {})["summary"]
    assert a["stable"] and 0 < a["freq_max_dev_pct"] < 10 and a["settling_s"] is not None
    rej = catalog.run("governor", {"event": "rejection", "p0_pu": 1.0})["summary"]
    assert rej["overspeed_pct"] > 10  # yuk tashlashda tezlik oshadi
    bad = catalog.run("governor", {"r_temp": 0.05, "tr": 1})["summary"]
    assert not bad["stable"] and "Hovey" in bad["verdict"]
    sp = catalog.run("governor", {"event": "setpoint", "step_pu": 0.1})
    assert sp["summary"]["stable"] and abs(sp["series"]["p_mech"][-1] - 0.9) < 0.05


def test_dispatch_optimal_vs_equal():
    r = catalog.run("dispatch", {"target_mw": 25})
    assert r["summary"]["units_on"] == 1 and r["units"][0]["power_mw"] == 25
    # Turli quvvatli agregatlar: optimal ≤ teng taqsimot
    r2 = catalog.run("dispatch", {"target_mw": 70, "unit_ratings": [40, 30, 20], "rated_mw": 40})
    s = r2["summary"]
    assert (
        s["equal_share_flow_m3s"] is None or s["total_flow_m3s"] <= s["equal_share_flow_m3s"] + 1e-6
    )
    assert abs(sum(u["power_mw"] for u in r2["units"]) - 70) < 0.01
    with pytest.raises(ValueError, match="erishib"):
        catalog.run("dispatch", {"target_mw": 500})
    day = catalog.run(
        "dispatch", {"daily_profile": [40] * 24, "reservoir_area_km2": 20, "inflow_m3s": 100}
    )
    assert day["summary"]["daily_energy_mwh"] == 960 and len(day["series"]["t"]) == 24


# --- Yog'ingarchilik ---
def test_rainfall_scs_runoff_and_routing():
    from ges_sim import rainfall

    assert abs(rainfall.curve_number("pasture", "C", "II") - 74) < 1e-9
    assert (
        rainfall.curve_number("pasture", "C", "III")
        > 74
        > rainfall.curve_number("pasture", "C", "I")
    )
    dry = catalog.run("rainfall", {"rain_mm": 60, "route": False})["summary"]
    wet = catalog.run(
        "rainfall", {"rain_mm": 300, "amc": "III", "soil_group": "D", "land_cover": "bare_rock"}
    )["summary"]
    assert dry["runoff_mm"] < 30 and wet["runoff_mm"] > 250
    assert wet["overtopped"] and wet["breach_peak_m3s"] > 0
    # Hajm balansi: oqim qatlami × maydon ≈ gidrograf hajmi (±3 %)
    r = catalog.run("rainfall", {"route": False})
    vol_mm = r["summary"]["runoff_mm"] / 1000 * 1200e6 / 1e6
    assert abs(r["summary"]["volume_mcm"] - vol_mm) / vol_mm < 0.03
    g = catalog.run("rainfall", {"glof": True, "lake_mcm": 10, "route": False})
    assert (
        g["glof"]["peak_m3s"] > 1000
        and g["summary"]["peak_inflow_m3s"] > r["summary"]["peak_inflow_m3s"]
    )
    s = catalog.run("rainfall", {"snowmelt": True, "air_temp": 10, "route": False})["summary"]
    assert s["snowmelt_mm_day"] > 0 and s["volume_mcm"] > r["summary"]["volume_mcm"]


# --- Transformator ---
def test_transformer_iec60076_thermal():
    from ges_sim import transformer

    base = catalog.run("transformer", {})["summary"]
    assert base["ok"] and 85 < base["hot_spot_max_c"] < 105 and base["aging_relative"] < 1
    over = catalog.run("transformer", {"power_mw": 120, "ambient_c": 40, "gen_rated_mva": 110})[
        "summary"
    ]
    assert not over["ok"] and over["hot_spot_max_c"] > 140 and over["gen_load_pct"] > 100
    # qarish 110 °C da = 1 (termik yaxshilangan), 98 °C da = 1 (kraft)
    assert (
        abs(transformer.aging_rate(110, "upgraded") - 1) < 1e-6
        and abs(transformer.aging_rate(98, "kraft") - 1) < 1e-9
    )
    prof = catalog.run(
        "transformer",
        {
            "load_profile_mw": [40] * 6 + [100] * 12 + [60] * 6,
            "ambient_profile": [20] * 6 + [35] * 12 + [25] * 6,
        },
    )
    assert len(prof["series"]["t"]) == 96 and max(prof["series"]["load_factor"]) > 1.0
