"""Simulyatsiya katalogi (server), forma pasport/modeldan, hisob (fon vazifasi), natija, 3D suv sathi,
xavfsizlik tekshiruvi."""

from __future__ import annotations

import time

import bpy

from . import flows, props, session, sim_anim, water
from .core import ui_tasks
from .core.tasks import TASKS, Cancelled
from .core.ui_tasks import ensure_pump, run_op, show_error
from .ops_server import _sel
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
        def apply(cat):
            global _catalog
            _catalog = cat
            s = bpy.context.scene.ges
            groups = _catalog.get("groups", {})
            rows = [
                {"item_id": i, "name": k["title"], "col2": groups.get(k["group"], k["group"]),
                 "col4": k.get("description", ""), "guid": k["id"]}
                for i, k in enumerate(_catalog["kinds"])
                if not k.get("custom_ui")
            ]  # fmt: skip
            props.fill(s.sim_kinds, rows)
            s.sim_kind_index = 0 if rows else -1  # update → sim_pick

        return run_op(self, "Sim katalogi", lambda ctx: session.client().sim_catalog(), apply, key="sim.catalog")


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


POLL_S = 0.6
WAIT_MAX_S = 2 * 3600  # navbatda qotib qolgan ish: kutish cheksiz emas


def wait_job(meta: dict, job_id: int, on_done=None, title: str = "Simulyatsiya"):
    """Sim ishini ishchi oqimda kutadi (K3; avval timer ichida bloklovchi so'rov edi); natija asosiy oqimda.
    TASKS.run run_op dan tashqarida — epoch himoyasi shu yerda: model almashgan bo'lsa natija sahnaga yozilmaydi.
    Kutish bekor qilinadi: X (status bar), sessiya/model almashishi (epoch — logout dan keyin eski klient so'ramaydi)
    yoki WAIT_MAX_S. Serverdagi hisob to'xtatilmaydi."""
    ep = session.epoch()

    def work(ctx):
        c = session.client()
        deadline = time.monotonic() + WAIT_MAX_S
        while True:
            if session.epoch() != ep:
                raise Cancelled()
            if time.monotonic() > deadline:
                return {"ok": False, "error": "kutish muddati tugadi"}
            j = c.sim_job(job_id)
            if j["status"] == "done":
                return {"ok": True, "result": c.sim_result(job_id)}
            if j["status"] == "failed":
                return {"ok": False, "error": j.get("error") or "hisob xatosi"}
            ctx.progress(None, j["status"])
            ctx.sleep(POLL_S)

    def stale() -> bool:
        if session.epoch() == ep:
            return False
        ui_tasks.status("Simulyatsiya: natija eskirdi (model almashdi)")
        return True

    def apply(res):
        if stale():
            return
        s = bpy.context.scene.ges
        if not res["ok"]:
            s.sim_status = f"Xato: {res['error']}"
            return
        result = res["result"]
        rows, level = flows.sim_result_rows(meta, result)
        props.fill(s.sim_results, rows)
        s.sim_water_level = level if level is not None else -1e9
        s.sim_status = "Tayyor"
        if on_done is not None:
            try:
                on_done(result)
            except sim_anim.TwinBindingError as e:  # K2: rol bog'lanmadi — natija bor, egizak sababi aniq
                s.sim_status = f"Tayyor, lekin egizak bog'lanmadi: {e}"
            except Exception as e:  # noqa: BLE001 — animatsiya xatosi natijani yo'qotmasin
                s.sim_status = f"Tayyor (animatsiya xatosi: {e})"

    def error(e):
        if stale():
            return
        bpy.context.scene.ges.sim_status = f"Xato: {e}"
        show_error(title, str(e))

    def cancelled():
        if session.epoch() == ep:
            bpy.context.scene.ges.sim_status = "Bekor qilindi (serverdagi hisob davom etishi mumkin)"

    task = TASKS.run(title, work, apply, error, key=f"sim.job.{job_id}", on_cancel=cancelled)
    ensure_pump()
    return task


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
        wait_job(k, job["id"], title=k["title"])
        return {"FINISHED"}


HYDRO_META = {
    "outputs": [
        {"key": "energy_mwh", "label": "Ishlab chiqarish", "unit": "MWh"},
        {"key": "mean_power_mw", "label": "O'rtacha quvvat", "unit": "MW"},
        {"key": "spill_volume_mcm", "label": "Tashlama", "unit": "mln m³"},
        {"key": "min_level_m", "label": "Min sath", "unit": "m"},
        {"key": "max_level_m", "label": "Max sath", "unit": "m"},
    ],
    "viz": {"water_level": "level"},
}


def hydro_params(client, version_id: int | None, s) -> dict:
    """Server namunasi + modeldagi Pset_GES_* (agregatlar, quvur, suv tashlagich) + panel maydonlari."""
    p = client.sim_example()
    if version_id:
        g = client.ges_params(version_id)
        if g.get("units"):
            keys = ("name", "type", "rated_power_mw", "rated_head_m", "rated_flow_m3s", "max_efficiency", "guid")
            p["units"] = [{k: u[k] for k in keys if k in u} for u in g["units"]]
        if g.get("penstocks"):
            pen = g["penstocks"][0]
            p.setdefault("penstock", {}).update(
                {k: pen[k] for k in ("length_m", "diameter_m", "roughness_mm") if k in pen}
            )
        r = p["reservoir"]
        if g.get("spillways"):
            sp = g["spillways"][0]
            crest = sp.get("crest_m") or 0.0
            # model ostonasi ombor sathlariga mos kelmasa (masalan 0) — NPU (web «Modeldan» kabi)
            if not (r["dead_level_m"] <= crest <= (r.get("max_level_m") or r["normal_level_m"] + 2)):
                crest = r["normal_level_m"]
            r["spillway"] = {
                "crest_m": crest, "width_m": sp["width_m"] or r.get("spillway", {}).get("width_m", 24),
                "coefficient": sp.get("coefficient") or 0.49, "gate_opening": 1.0,
            }  # fmt: skip
            p["spillway_guid"] = sp.get("guid", "")
        # Model 0 belgisi: to'g'on gerbi absolyut belgisi bo'lmasa — NPU + 3 m gerb deb, tag = gerb − balandlik
        if s.hydro_zero == 0 and g.get("dams"):
            d = g["dams"][0]
            if not d.get("crest_elevation_m"):
                s.hydro_zero = float(r["normal_level_m"]) + 3.0 - float(d.get("height_m") or 20.0)
        # Gerb belgisi bor: namunaviy ombor sathlarini geometriyaga suramiz (NPU = gerb − 3 m); quyi byef — kanal
        # pasportidagi hisobiy sath (bo'lsa)
        crest = g["dams"][0].get("crest_elevation_m") if g.get("dams") else None
        if crest:
            shift = float(crest) - 3.0 - float(r["normal_level_m"])
            r["curve"]["elevations_m"] = [round(e + shift, 2) for e in r["curve"]["elevations_m"]]
            for k in ("dead_level_m", "normal_level_m", "max_level_m", "initial_level_m", "tailwater_m"):
                if k in r:
                    r[k] = round(float(r[k]) + shift, 2)
            if r.get("spillway") and not (r["dead_level_m"] <= r["spillway"]["crest_m"] <= r["max_level_m"]):
                r["spillway"]["crest_m"] = r["normal_level_m"]
        tr = g["tailraces"][0] if g.get("tailraces") else None
        if tr and tr.get("design_tailwater_m"):
            r["tailwater_m"] = float(tr["design_tailwater_m"])
    p["inflow_m3s"] = {"constant": float(s.hydro_inflow), "steps": int(s.hydro_days)}
    p["dt_hours"] = 24
    if s.hydro_level0 > 0:
        p["reservoir"]["initial_level_m"] = float(s.hydro_level0)
    p["operation"] = {"mode": s.hydro_mode}
    if s.hydro_mode == "target_level":
        p["operation"]["target_level_m"] = p["reservoir"]["normal_level_m"]
    p["model_zero_elevation_m"] = float(s.hydro_zero)
    return p


class SATH_OT_sim_hydro(bpy.types.Operator):
    """Suv ombori rejimi va energiya (serverda) — natija Blender timeline animatsiyasi: suv sathi, agregatlar rangi"""

    bl_idname = "sath.sim_hydro"
    bl_label = "Suv ombori / energiya"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def execute(self, context):
        s = context.scene.ges
        try:
            params = hydro_params(session.client(), s.version_id or None, s)
            job = session.client().create_sim(
                s.model_id, "Suv ombori/energiya (Blender)", s.version_id or None, params, kind="hydro"
            )
        except (ServerError, ValueError, KeyError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.sim_job_id = job["id"]
        s.sim_status = "Hisoblanmoqda…"

        def done(result: dict):
            sc = bpy.context.scene.ges
            n = sim_anim.animate_hydro(bpy.context, result, params, zero_m=float(sc.hydro_zero))
            sc.hydro_note = f"{n} kun → {n} kadr: Space bilan ijro (suv sathi, agregatlar rangi)"

        wait_job(HYDRO_META, job["id"], done)
        return {"FINISHED"}


class SATH_OT_sim_clear_anim(bpy.types.Operator):
    """Simulyatsiya animatsiyasini (keyframelar) olib tashlash"""

    bl_idname = "sath.sim_clear_anim"
    bl_label = "Animatsiyani tozalash"

    def execute(self, context):
        sim_anim.clear_animation(context)
        context.scene.ges.hydro_note = ""
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
        model_id, version_id = s.model_id, s.version_id or None

        def apply(res):
            sc = bpy.context.scene.ges
            head, rows = flows.safety_rows(res)
            sc.safety_head = head
            props.fill(sc.safety_rows, rows)

        return run_op(
            self, "Xavfsizlik tekshiruvi", lambda ctx: session.client().safety_check(model_id, version_id), apply,
            key="sim.safety",
        )  # fmt: skip


CLASSES = (
    SATH_OT_sim_catalog, SATH_OT_sim_pick, SATH_OT_sim_prefill, SATH_OT_sim_run, SATH_OT_sim_water,
    SATH_OT_safety_check, SATH_OT_sim_hydro, SATH_OT_sim_clear_anim,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
