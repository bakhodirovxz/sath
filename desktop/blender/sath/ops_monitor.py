"""SCADA monitoring: 5 s da sensorlar (REST), obyektlar alarm rangi, suv sathi tekisligi, sensor → 3D."""

from __future__ import annotations

import bpy

from . import flows, ifc, props, session, water
from .ops_server import _sel
from .shared.server_client import ServerError

INTERVAL = 5.0


def _tick():
    s = bpy.context.scene.ges
    if not s.monitor_on or not session.is_logged_in():
        ifc.ALARM_STATE.restore()
        return None
    try:
        sensors = session.client().sensors(s.project_id, s.model_id)
    except (ServerError, RuntimeError) as e:
        s.monitor_status = f"Xato: {e}"
        return INTERVAL
    alarms = [x for x in sensors if x.get("enabled") and x.get("alarm") != "ok"]
    s.monitor_status = f"{len(sensors)} sensor · {len(alarms)} alarm · yangilanish {INTERVAL:.0f} s"
    sel = s.sensors_index
    props.fill(s.sensors, flows.sensor_rows(sensors))
    s.sensors_index = min(sel, len(s.sensors) - 1)
    if s.monitor_color:
        ifc.ALARM_STATE.paint(flows.alarm_colors(sensors))
    else:
        ifc.ALARM_STATE.restore()
    if s.monitor_water:
        lvl = flows.water_sensor_level(sensors)
        if lvl is not None:
            water.place_water_plane(bpy.context, lvl)
    return INTERVAL


class SATH_OT_monitor_toggle(bpy.types.Operator):
    """Monitoringni yoqish/o'chirish (jonli qiymatlar)"""

    bl_idname = "sath.monitor_toggle"
    bl_label = "Monitoring"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def execute(self, context):
        s = context.scene.ges
        s.monitor_on = not s.monitor_on
        if s.monitor_on:
            if not s.project_id:
                s.project_id = session.client().model(s.model_id)["project_id"]
            if not bpy.app.timers.is_registered(_tick):
                bpy.app.timers.register(_tick, first_interval=0.0)
        else:
            ifc.ALARM_STATE.restore()
            s.monitor_status = ""
        return {"FINISHED"}


class SATH_OT_show_sensor(bpy.types.Operator):
    """Tanlangan sensor elementini 3D da tanlash"""

    bl_idname = "sath.show_sensor"
    bl_label = "3D da ko'rsatish"

    def execute(self, context):
        s = context.scene.ges
        it = _sel(s.sensors, s.sensors_index)
        if it is None:
            return {"CANCELLED"}
        if not it.guid:
            self.report({"INFO"}, "Bu sensor elementga bog'lanmagan (webda «Tanlanganga bog'lash»)")
            return {"CANCELLED"}
        if ifc.select_guids([it.guid]) == 0:
            self.report({"INFO"}, "Element sahnada topilmadi")
            return {"CANCELLED"}
        if context.area is not None and context.area.type == "VIEW_3D":
            bpy.ops.view3d.view_selected()
        return {"FINISHED"}


CLASSES = (SATH_OT_monitor_toggle, SATH_OT_show_sensor)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
