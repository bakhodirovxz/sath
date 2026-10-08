"""SCADA monitoring: 5 s da sensorlar (REST), obyektlar alarm/sog'liq rangi, suv sathi tekisligi, sensor → 3D;
raqamli egizak (kutilgan/o'lchangan quvvat, xavfsizlik) va sog'liq indeksi; vaqt mashinasi (historian sathi)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bpy

from . import flows, ifc, props, session, water
from .core.tasks import TASKS
from .core.ui_tasks import ensure_pump
from .ops_server import _sel
from .shared.server_client import ServerError

INTERVAL = 5.0


def _fetch(project_id: int, model_id: int, hours: float) -> dict:
    """Ishchi oqim (bpy siz): sensorlar, egizak, sog'liq, vaqt mashinasi uchun sath tarixi."""
    c = session.client()
    if not project_id:
        project_id = c.model(model_id)["project_id"]
    out: dict = {"project_id": project_id, "sensors": c.sensors(project_id, model_id), "twin": None, "health": None,
                 "twin_err": None, "level_sensor": None, "level_pts": None, "level_err": None}  # fmt: skip
    try:
        out["twin"] = c.twin(project_id)
        out["health"] = c.plant_health(project_id)
    except (ServerError, RuntimeError, KeyError, TypeError) as e:
        out["twin_err"] = str(e)
    if hours > 0:
        ls = next((x for x in out["sensors"] if x.get("kind") == "level" and x.get("enabled")), None)
        out["level_sensor"] = ls
        if ls is not None:
            try:
                out["level_pts"] = c.readings(ls["id"], hours=hours + 1)
            except ServerError as e:
                out["level_err"] = str(e)
    return out


def _apply(d: dict, hours: float) -> None:
    s = bpy.context.scene.ges
    if not s.monitor_on:
        return
    s.project_id = d["project_id"]
    sensors = d["sensors"]
    alarms = [x for x in sensors if x.get("enabled") and x.get("alarm") != "ok"]
    s.monitor_status = f"{len(sensors)} sensor · {len(alarms)} alarm · yangilanish {INTERVAL:.0f} s"
    sel = s.sensors_index
    props.fill(s.sensors, flows.sensor_rows(sensors))
    s.sensors_index = min(sel, len(s.sensors) - 1)
    health_assets: list[dict] = []
    if d["twin_err"] is None:
        try:  # noto'g'ri shakldagi javob monitoringni to'xtatmasin
            tw, h = d["twin"], d["health"]
            s.twin_head = flows.twin_head(tw)
            props.fill(s.twin_rows, flows.twin_rows(tw))
            props.fill(s.twin_safety, flows.twin_safety_rows(tw.get("safety") or []))
            s.health_head = flows.health_head(h)
            props.fill(s.health_rows, flows.health_rows(h))
            health_assets = h.get("assets", [])
        except (KeyError, TypeError, AttributeError) as e:
            health_assets = []
            s.twin_head = f"Egizak: {e}"
    else:
        s.twin_head = f"Egizak: {d['twin_err']}"
    ifc.ALARM_STATE.restore()
    if s.monitor_color:
        colors = flows.health_colors(health_assets) if s.monitor_color_mode == "health" else flows.alarm_colors(sensors)
        ifc.ALARM_STATE.paint(colors)
    if s.monitor_water:
        lvl = flows.water_sensor_level(sensors) if hours <= 0 else _level_from(d, hours)
        if lvl is not None:
            water.place_water_plane(bpy.context, lvl)


def _level_from(d: dict, hours_ago: float) -> float | None:
    """Vaqt mashinasi: sath sensori tarixidan N soat oldingi qiymat."""
    s = bpy.context.scene.ges
    ls = d["level_sensor"]
    if ls is None:
        s.time_note = "sath sensori yo'q"
        return None
    if d["level_err"] is not None:
        s.time_note = f"tarix xatosi: {d['level_err']}"
        return None
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    v = flows.reading_at(d["level_pts"] or [], ts)
    s.time_note = f"{hours_ago:.1f} soat oldin: {'—' if v is None else f'{v:.2f} m'} ({ls['name']})"
    return v


def _tick():
    s = bpy.context.scene.ges
    if not s.monitor_on or not session.is_logged_in():
        ifc.ALARM_STATE.restore()
        return None
    pid, mid, hours, ep = s.project_id, s.model_id, s.time_hours, session.epoch()

    def apply(d):
        if session.epoch() == ep:
            _apply(d, hours)

    def error(e):
        sc = bpy.context.scene.ges
        if session.epoch() != ep or not sc.monitor_on:
            return
        sc.monitor_status = f"Xato: {e}"

    # K3: tarmoq ishchi oqimda; oldingi tik hali tugamagan bo'lsa bu tik o'tkazib yuboriladi (key)
    TASKS.run("Monitoring", lambda ctx: _fetch(pid, mid, hours), apply, error, key="monitor.tick", cancellable=False, quiet=True)
    ensure_pump()
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


class SATH_OT_show_asset(bpy.types.Operator):
    """Sog'liq ro'yxatidagi aktiv elementini 3D da tanlash"""

    bl_idname = "sath.show_asset"
    bl_label = "Aktivni ko'rsatish"

    def execute(self, context):
        s = context.scene.ges
        it = _sel(s.health_rows, s.health_index)
        if it is None or not it.guid:
            self.report({"INFO"}, "Aktiv elementga bog'lanmagan (webda aktiv kartasida bog'lang)")
            return {"CANCELLED"}
        if ifc.select_guids([it.guid]) == 0:
            self.report({"INFO"}, "Element sahnada topilmadi")
            return {"CANCELLED"}
        if context.area is not None and context.area.type == "VIEW_3D":
            bpy.ops.view3d.view_selected()
        return {"FINISHED"}


class SATH_OT_monitor_refresh(bpy.types.Operator):
    """Hozir yangilash (timer kutmasdan)"""

    bl_idname = "sath.monitor_refresh"
    bl_label = "Yangilash"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.monitor_on

    def execute(self, context):
        _tick()
        return {"FINISHED"}


CLASSES = (SATH_OT_monitor_toggle, SATH_OT_show_sensor, SATH_OT_show_asset, SATH_OT_monitor_refresh)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
