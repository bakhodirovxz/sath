"""Monitoring (SCADA) moduli: sensorlar (5 s tik), 3D alarm/sog'liq ranglari, suv sathi tekisligi. Har tikda
`scada.snapshot` hodisasi (2-quyi-loyihada manba WebSocket ga almashadi)."""

from __future__ import annotations

import bpy

from ... import ifc, ops_monitor
from ...core.panels import SathPanel, draw_list


class SATH_PT_monitor(SathPanel, bpy.types.Panel):
    bl_label = "Monitoring (SCADA)"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        row = lay.row(align=True)
        row.operator(
            "sath.monitor_toggle",
            text="To'xtatish" if s.monitor_on else "Boshlash",
            icon="PAUSE" if s.monitor_on else "PLAY",
            depress=s.monitor_on,
        )
        row.operator("sath.monitor_refresh", text="", icon="FILE_REFRESH")
        row = lay.row(align=True)
        row.prop(s, "monitor_color")
        row.prop(s, "monitor_color_mode", text="")
        lay.prop(s, "monitor_water")
        if s.monitor_status:
            lay.label(text=s.monitor_status, icon="INFO")
        draw_list(lay, s, "sensors", "sensors_index", 5)
        row = lay.row(align=True)
        row.operator("sath.show_sensor", icon="RESTRICT_SELECT_OFF")
        row.operator("sath.open_web", text="Webda (HMI)", icon="URL").tab = "mon"


def _menu(layout, context):
    layout.operator("sath.monitor_toggle")


def register(api):
    api.adopt("scada", ops_monitor)  # ops_monitor.unregister _tick timerini ham to'xtatadi
    api.register_classes("scada", [SATH_PT_monitor])
    api.ui.main_menu("scada", _menu)


def unregister(api):
    for sc in getattr(bpy.data, "scenes", ()):  # faqat faol sahna emas (cheklangan kontekstda — hech biri)
        sc.ges.monitor_on = False
        sc.ges.monitor_status = ""
    ifc.ALARM_STATE.restore()  # o'chirilgan monitoringning 3D ranglari qolmasin
