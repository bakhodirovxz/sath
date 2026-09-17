"""Simulyatsiya katalogi (server), forma pasport/modeldan, hisob (timer poll), natija, 3D suv sathi,
xavfsizlik tekshiruvi."""

from __future__ import annotations

import bpy

from . import flows, props, session, water
from .ops_server import _sel, guard
from .shared.server_client import ServerError

_catalog: dict = {}


def _kind(s) -> dict | None:
    k = _sel(s.sim_kinds, s.sim_kind_index)
    if k is None:
        return None
    return next((x for x in _catalog.get("kinds", []) if x["id"] == k.guid), None)


class SATH_OT_sim_catalog(bpy.types.Operator):
    """Barcha simulyatsiya turlari (server katalogi)"""

    bl_idname = "sath.sim_catalog"
    bl_label = "Katalogni yuklash"

    def execute(self, context):
        s = context.scene.ges

        def do():
            global _catalog
            _catalog = session.client().sim_catalog()
            groups = _catalog.get("groups", {})
            rows = [
                {
                    "item_id": i,
                    "name": k["title"],
                    "col2": groups.get(k["group"], k["group"]),
                    "col4": k.get("description", ""),
                    "guid": k["id"],
                }
                for i, k in enumerate(_catalog["kinds"])
                if not k.get("custom_ui")
            ]
            props.fill(s.sim_kinds, rows)
            s.sim_kind_index = 0 if rows else -1  # update → sim_pick

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class SATH_OT_sim_pick(bpy.types.Operator):
    bl_idname = "sath.sim_pick"
    bl_label = "Turni tanlash"

    @classmethod
    def poll(cls, context):
        return bool(_catalog)

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        s.sim_fields.clear()
        s.sim_results.clear()
        s.sim_water_level = -1e9
        if not k:
            return {"FINISHED"}
        for f in k["fields"]:
            it = s.sim_fields.add()
            it.key, it.ftype, it.hint = f["key"], f["type"], f.get("hint", "")
            it.label = f["label"] + (f", {f['unit']}" if f.get("unit") else "")
            d = f.get("default")
            if f["type"] == "bool":
                it.value_bool = bool(d)
            elif f["type"] == "select":
                it.options = ";".join(f"{v}={lb}" for v, lb in f.get("options", []))
                if d is not None and any(str(v) == str(d) for v, _ in f.get("options", [])):
                    it.value_sel = str(d)
            elif f["type"] == "series":
                it.value_str = ", ".join(str(x) for x in d) if isinstance(d, list) else str(d or "")
            else:
                it.value_str = "" if d is None else str(d)
        if s.model_id:
            bpy.ops.sath.sim_prefill(src="site", quiet=True)
        return {"FINISHED"}


class SATH_OT_sim_prefill(bpy.types.Operator):
    """Maydonlarni pasportdan yoki modeldan (Pset_GES_*) to'ldirish"""

    bl_idname = "sath.sim_prefill"
    bl_label = "To'ldirish"
    src: bpy.props.EnumProperty(items=[("site", "Pasportdan", ""), ("model", "Modeldan", "")])
    quiet: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        if not k or not s.model_id:
            return {"CANCELLED"}
        try:
            pf = session.client().sim_prefill(s.model_id, k["id"], s.version_id or None)
        except ServerError as e:
            if not self.quiet:
                self.report({"ERROR"}, e.message)
            return {"CANCELLED"}
        vals = pf.get(self.src) or {}
        n = 0
        for it in s.sim_fields:
            if it.key not in vals:
                continue
            v = vals[it.key]
            if it.ftype == "bool":
                it.value_bool = bool(v)
            elif it.ftype == "select":
                if any(o.split("=", 1)[0] == str(v) for o in it.options.split(";")):
                    it.value_sel = str(v)
            else:
                it.value_str = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
            n += 1
        if not self.quiet:
            s.sim_status = f"{n} maydon {'pasportdan' if self.src == 'site' else 'modeldan'}"
            if not vals and self.src == "site":
                self.report({"WARNING"}, "Maydon pasporti to'ldirilmagan — webda loyiha sahifasida kiriting")
        return {"FINISHED"}


def _raw(s) -> dict:
    out = {}
    for it in s.sim_fields:
        if it.ftype == "bool":
            out[it.key] = it.value_bool
        elif it.ftype == "select":
            out[it.key] = it.value_sel
        else:
            out[it.key] = it.value_str
    return out


def _poll_factory(kind: dict, job_id: int):
    def poll():
        s = bpy.context.scene.ges
        try:
            j = session.client().sim_job(job_id)
        except (ServerError, RuntimeError) as e:
            s.sim_status = f"Xato: {e}"
            return None
        if j["status"] == "done":
            rows, level = flows.sim_result_rows(kind, session.client().sim_result(job_id))
            props.fill(s.sim_results, rows)
            s.sim_water_level = level if level is not None else -1e9
            s.sim_status = "Tayyor"
            return None
        if j["status"] == "failed":
            s.sim_status = f"Xato: {j.get('error') or 'hisob xatosi'}"
            return None
        return 0.6

    return poll


class SATH_OT_sim_run(bpy.types.Operator):
    """Hisob serverda; natija har 0.6 s da tekshiriladi"""

    bl_idname = "sath.sim_run"
    bl_label = "Hisoblash"

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        if not k or not s.model_id:
            self.report({"ERROR"}, "Model va simulyatsiya turini tanlang")
            return {"CANCELLED"}
        try:
            job = session.client().create_sim(
                s.model_id,
                k["title"],
                s.version_id or None,
                flows.sim_values(k["fields"], _raw(s)),
                kind=k["id"],
            )
        except (ServerError, ValueError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.sim_job_id = job["id"]
        s.sim_status = "Hisoblanmoqda…"
        bpy.app.timers.register(_poll_factory(k, job["id"]), first_interval=0.6)
        return {"FINISHED"}


class SATH_OT_sim_water(bpy.types.Operator):
    """Natijadagi suv sathini 3D tekislik sifatida ko'rsatish"""

    bl_idname = "sath.sim_water"
    bl_label = "3D: suv sathi"

    @classmethod
    def poll(cls, context):
        return context.scene.ges.sim_water_level > -1e8

    def execute(self, context):
        lvl = context.scene.ges.sim_water_level
        water.place_water_plane(context, lvl)
        self.report({"INFO"}, f"Suv sathi tekisligi: {lvl:.2f} m (GES_SuvSathi)")
        return {"FINISHED"}


class SATH_OT_safety_check(bpy.types.Operator):
    """12 ssenariy: toshqin, N−1 darvoza, zilzila, barqarorlik, filtratsiya, gidrozarba… (serverda)"""

    bl_idname = "sath.safety_check"
    bl_label = "Xavfsizlik tekshiruvi"

    def execute(self, context):
        s = context.scene.ges
        if not s.model_id:
            self.report({"ERROR"}, "Avval modelni oching")
            return {"CANCELLED"}

        def do():
            res = session.client().safety_check(s.model_id, s.version_id or None)
            head, rows = flows.safety_rows(res)
            s.safety_head = head
            props.fill(s.safety_rows, rows)

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


CLASSES = (
    SATH_OT_sim_catalog, SATH_OT_sim_pick, SATH_OT_sim_prefill, SATH_OT_sim_run, SATH_OT_sim_water,
    SATH_OT_safety_check,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
