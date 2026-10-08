"""Simulyatsiya moduli: suv ombori rejimi → timeline, server katalogidagi hisoblar, xavfsizlik tekshiruvi."""

from __future__ import annotations

import bpy

from ... import ops_sim
from ...core.panels import SathPanel, cur, draw_list


class SATH_PT_sim(SathPanel, bpy.types.Panel):
    bl_label = "Simulyatsiya"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        box = lay.box()
        box.label(text="Suv ombori rejimi va energiya → timeline", icon="MOD_FLUIDSIM")
        box.prop(s, "hydro_inflow")
        row = box.row(align=True)
        row.prop(s, "hydro_days")
        row.prop(s, "hydro_level0")
        box.prop(s, "hydro_mode", text="")
        box.prop(s, "hydro_zero")
        row = box.row(align=True)
        row.operator("sath.sim_hydro", icon="PLAY")
        row.operator("sath.sim_clear_anim", text="", icon="X")
        if s.hydro_note:
            box.label(text=s.hydro_note, icon="INFO")
        box = lay.box()
        box.label(text="Egizak simulyatsiyalari → timeline (namuna GES: «GES obyektlari»)", icon="OUTLINER_OB_GROUP_INSTANCE")
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(s, "hammer_close_s")
        row.operator("sath.sim_hammer", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "gov_event", text="")
        row.prop(s, "gov_step")
        row.operator("sath.sim_governor", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "tr_load")
        row.prop(s, "tr_days")
        row.operator("sath.sim_transformer", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "seis_intensity", text="")
        row.prop(s, "seis_ground", text="")
        row.prop(s, "seis_scale")
        row.operator("sath.sim_seismic", icon="PLAY")
        if s.twin_note:
            box.label(text=s.twin_note, icon="INFO")
        row = lay.row(align=True)
        row.operator("sath.sim_catalog", icon="FILE_REFRESH")
        row.operator("sath.safety_check", icon="CHECKMARK")
        draw_list(lay, s, "sim_kinds", "sim_kind_index", 4)
        k = cur(s.sim_kinds, s.sim_kind_index)
        if k and k.col4:
            lay.label(text=k.col4[:90])
        for f in s.sim_fields:
            if f.ftype == "bool":
                lay.prop(f, "value_bool", text=f.label)
            elif f.ftype == "select":
                lay.prop(f, "value_sel", text=f.label)
            else:
                lay.prop(f, "value_str", text=f.label)
        row = lay.row(align=True)
        row.operator("sath.sim_prefill", text="Pasportdan").src = "site"
        row.operator("sath.sim_prefill", text="Modeldan").src = "model"
        row.operator("sath.sim_run", icon="PLAY")
        if s.sim_status:
            lay.label(text=s.sim_status, icon="INFO")
        for r in s.sim_results:
            icon = "CHECKMARK" if r.state == "ok" else "ERROR" if r.state == "fail" else "DOT"
            lay.label(text=f"{r.name}: {r.col2}", icon=icon)
        row = lay.row(align=True)
        row.operator("sath.sim_water", icon="MOD_FLUIDSIM")
        row.operator("sath.open_web", text="Webda (grafik, hisobot)", icon="URL").tab = "sim"
        if s.safety_head:
            box = lay.box()
            box.label(text=s.safety_head, icon="FAKE_USER_ON")
            for r in s.safety_rows:
                box.label(text=f"{r.name} — {r.state}: {r.col2}"[:100])


def _menu(layout, context):
    layout.operator("sath.sim_catalog")
    layout.operator("sath.safety_check")


def register(api):
    api.adopt("sim", ops_sim)
    api.register_classes("sim", [SATH_PT_sim])
    api.ui.main_menu("sim", _menu)
