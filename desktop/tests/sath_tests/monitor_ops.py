"""Alarm ranglari va suv sathi flows dan sahnaga tushadi (server siz)."""

from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def run(ctx):
    from sath import flows, ifc, water

    ifc.load(SAMPLE)
    g = next(g for g, o in ifc.guid_map().items() if ifc.entity(o).is_a("IfcWall"))
    sensors = [
        {"id": 1, "name": "S", "key": "k", "kind": "level", "last_value": 4.0, "alarm": "high",
         "enabled": True, "element_guid": g},
    ]  # fmt: skip
    assert ifc.ALARM_STATE.paint(flows.alarm_colors(sensors)) == 1
    got = ifc.object_for_guid(g).color
    assert all(abs(a - b) < 1e-5 for a, b in zip(got, flows.ALARM_COLORS["high"], strict=True)), tuple(got)
    ifc.ALARM_STATE.restore()
    lvl = flows.water_sensor_level(sensors)
    assert water.place_water_plane(bpy.context, lvl).location.z == 4.0
    assert hasattr(bpy.ops.sath, "monitor_toggle") and hasattr(bpy.ops.sath, "show_sensor")
    assert bpy.ops.sath.monitor_toggle.poll() is False  # login yo'q
    assert hasattr(bpy.types, "SATH_PT_monitor")
