"""sath addonining bpy siz qismlari: sync, pset guruhlash, IFC klass xaritasi, viewpoint matematikasi."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "build"))
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

import sync_blender  # noqa: E402


def test_shared_is_synced():
    assert sync_blender.check() == [], "python desktop/build/sync_blender.py ni ishga tushiring"

from sath import fc_engine  # noqa: E402


def test_parse_props_groups_by_pset_and_casts():
    raw = {
        "Balandlik_m": "Pset_GES_Dam;;IfcReal;;20.0",
        "Turi": "Pset_GES_Dam;;IfcLabel;;Gravitatsion",
        "Soni": "Pset_GES_Turbine;;IfcInteger;;3",
        "Buzuq": "faqat-bitta-qism",
    }
    assert fc_engine._parse_props(raw) == {
        "Pset_GES_Dam": {"Balandlik_m": 20.0, "Turi": "Gravitatsion"},
        "Pset_GES_Turbine": {"Soni": 3},
    }


def test_ifc_class_from_freecad_type():
    assert fc_engine.ifc_class("Pipe Segment") == "IfcPipeSegment"
    assert fc_engine.ifc_class("Wall") == "IfcWall"
    assert fc_engine.ifc_class("Building Element Proxy") == "IfcBuildingElementProxy"

from sath import flows, viewpoint  # noqa: E402


def test_viewpoint_from_view_ifc_space_metres():
    vp = viewpoint.from_view(
        position=(10.0, 20.0, 5.0), direction=(0.0, 1.0, 0.0), distance=4.0, is_ortho=False, guids=["a"]
    )
    assert vp["camera"]["space"] == "ifc"
    assert vp["camera"]["position"] == [10.0, 20.0, 5.0]
    assert vp["camera"]["target"] == [10.0, 24.0, 5.0]
    assert vp["camera"]["projection"] == "Perspective"
    assert vp["selected_guids"] == ["a"] and vp["section"] == []


def test_viewpoint_view_params_from_camera():
    loc, d, dist = viewpoint.view_params({"position": [0, 0, 0], "target": [0, 0, -3]})
    assert loc == (0.0, 0.0, -3.0) and dist == 3.0
    assert tuple(round(x, 6) for x in d) == (0.0, 0.0, -1.0)


def test_diff_colors_maps_added_changed_and_summary():
    colors, text = flows.diff_colors(
        {
            "added": [{"guid": "A"}],
            "changed": [{"guid": "B"}],
            "deleted": [{"guid": "C", "name": "Devor"}],
            "summary": {"added": 1, "changed": 1, "deleted": 1},
        }
    )
    assert colors == {"A": flows.DIFF_COLORS["added"], "B": flows.DIFF_COLORS["changed"]}
    assert "+1" in text and "~1" in text and "Devor" in text


def test_addon_version_from_manifest():
    import re

    assert re.match(r"\d+\.\d+\.\d+", flows.ADDON_VERSION)


def test_sim_values_casts_by_field_type():
    fields = [
        {"key": "q", "type": "number"}, {"key": "n", "type": "int"}, {"key": "b", "type": "bool"},
        {"key": "s", "type": "series"}, {"key": "sel", "type": "select"}, {"key": "t", "type": "text"},
    ]  # fmt: skip
    raw = {"q": "12,5", "n": "3", "b": True, "s": "1, 2;3", "sel": "x", "t": " ab "}
    assert flows.sim_values(fields, raw) == {
        "q": 12.5, "n": 3.0, "b": True, "s": [1.0, 2.0, 3.0], "sel": "x", "t": "ab",
    }  # fmt: skip


def test_sim_result_rows_and_water_level():
    kind = {
        "outputs": [{"key": "max_level", "label": "Maks sath", "unit": "m"}],
        "viz": {"water_level": "level"},
    }
    rows, lvl = flows.sim_result_rows(
        kind,
        {"summary": {"verdict": "OK", "ok": True, "max_level": 101.234}, "series": {"level": [99.0, 101.2]}},
    )
    assert rows[0] == {"name": "Xulosa", "col2": "OK", "state": "ok"}
    assert rows[1] == {"name": "Maks sath", "col2": "101.23 m", "state": ""}
    assert lvl == 101.2


def test_safety_rows():
    head, rows = flows.safety_rows(
        {
            "score": 80, "verdict": "yaxshi",
            "counts": {"ok": 10, "warn": 1, "fail": 1, "skip": 0},
            "rows": [{"title": "Toshqin", "status": "warn", "message": "chegara", "metrics": {"k": 1.234}}],
        }  # fmt: skip
    )
    assert head.startswith("80 / 100") and rows[0]["state"] == "ogohlantirish"
    assert "k = 1.23" in rows[0]["col3"]


def test_sensor_rows_alarm_colors_and_water():
    sensors = [
        {"id": 1, "name": "Sath", "key": "lvl", "kind": "level", "unit": "m", "last_value": 101.5,
         "alarm": "ok", "enabled": True, "element_guid": "G1", "last_ts": "2026-09-17T10:00:00"},
        {"id": 2, "name": "Bosim", "key": "p", "kind": "pressure", "unit": "bar", "last_value": None,
         "alarm": "stale", "enabled": True, "element_guid": "G2"},
        {"id": 3, "name": "O'chiq", "key": "x", "kind": "level", "last_value": 5.0, "alarm": "high",
         "enabled": False, "element_guid": "G3"},
    ]  # fmt: skip
    rows = flows.sensor_rows(sensors)
    assert rows[0]["col2"] == "101.50 m" and rows[0]["state"] == "normal" and rows[0]["guid"] == "G1"
    assert rows[0]["col3"] == "2026-09-17 10:00"
    assert rows[1]["col2"] == "—" and rows[1]["state"] == "uzilgan"
    assert flows.alarm_colors(sensors) == {
        "G1": flows.ALARM_COLORS["ok"], "G2": flows.ALARM_COLORS["stale"],
    }  # fmt: skip
    assert flows.water_sensor_level(sensors) == 101.5


def test_twin_rows_head_and_health():
    state = {
        "status": "ok", "head_gross_m": 45.25, "expected_total_mw": 50.0, "measured_total_mw": 47.5,
        "units": [
            {"name": "Agregat 1", "running": True, "measured_mw": 25.0, "expected_mw": 26.0, "deviation_pct": -3.85, "efficiency": 0.91},
            {"name": "Agregat 2", "running": False, "measured_mw": None, "expected_mw": 24.0, "deviation_pct": None, "efficiency": None},
        ],
        "safety": [{"name": "Gerb zaxirasi", "value": 2.5, "unit": "m", "ok": True}, {"name": "Sirpanish", "value": 1.2, "unit": "", "ok": False}],
    }  # fmt: skip
    assert flows.twin_head(state) == "Napor 45.25 m · 47.5 / 50.0 MW (o'lchangan / kutilgan)"
    rows = flows.twin_rows(state)
    assert rows[0]["name"] == "Agregat 1" and rows[0]["col2"] == "25.0 / 26.0 MW" and rows[0]["col3"] == "−3.9 %" and rows[0]["state"] == "ok"
    assert rows[1]["col2"] == "— / 24.0 MW" and rows[1]["state"] == "stop"
    srows = flows.twin_safety_rows(state["safety"])
    assert srows[0] == {"name": "Gerb zaxirasi", "col2": "2.5 m", "state": "ok"}
    assert srows[1]["state"] == "fail"
    h = {"plant_score": 72, "assets": [
        {"asset_id": 1, "name": "Agregat 1", "element_guid": "G1", "score": 85, "level": "yaxshi", "problems": []},
        {"asset_id": 2, "name": "Agregat 2", "element_guid": None, "score": 35, "level": "kritik", "problems": ["tebranish D zona"]},
    ]}  # fmt: skip
    assert flows.health_head(h) == "Stansiya sog'lig'i: 72 / 100"
    hr = flows.health_rows(h)
    assert hr[0]["col2"] == "85" and hr[0]["state"] == "yaxshi" and hr[0]["guid"] == "G1"
    assert hr[1]["col3"] == "tebranish D zona"
    assert flows.health_colors(h["assets"]) == {"G1": flows.HEALTH_COLORS["yaxshi"]}


def test_reading_at_picks_latest_before_ts():
    pts = [{"ts": "2026-09-17T10:00:00+00:00", "value": 1.0}, {"ts": "2026-09-17T11:00:00+00:00", "value": 2.0}, {"ts": "2026-09-17T12:00:00+00:00", "value": 3.0}]
    assert flows.reading_at(pts, "2026-09-17T11:30:00+00:00") == 2.0
    assert flows.reading_at(pts, "2026-09-17T09:00:00+00:00") is None
    assert flows.reading_at([], "2026-09-17T09:00:00+00:00") is None
