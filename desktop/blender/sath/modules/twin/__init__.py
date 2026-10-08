"""Raqamli egizak moduli: jonli egizak holati (monitoring tikidan), sog'liq indeksi, vaqt mashinasi va egizak
simulyatsiyalari (gidrozarba, rostlagich, transformator, seysmik) → timeline."""

from __future__ import annotations

import bpy

from ... import ops_twin
from ...core.panels import SathPanel, draw_list


class SATH_PT_twin(SathPanel, bpy.types.Panel):
    bl_label = "Raqamli egizak"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        if not s.monitor_on:
            lay.label(text="Monitoringni yoqing — egizak jonli holatdan hisoblanadi", icon="INFO")
        if s.twin_head:
            lay.label(text=s.twin_head, icon="LIGHT_SUN")
        box = lay.box()
        box.label(text="Agregatlar: o'lchangan / kutilgan, og'ish", icon="MOD_BUILD")
        for r in s.twin_rows:
            icon = "CHECKMARK" if r.state == "ok" else "ERROR" if r.state == "warn" else "PAUSE"
            box.label(text=f"{r.name}: {r.col2} {r.col3} {r.col4}".strip(), icon=icon)
        if len(s.twin_safety):
            box = lay.box()
            box.label(text="Xavfsizlik (jonli)", icon="FAKE_USER_ON")
            for r in s.twin_safety:
                box.label(text=f"{r.name}: {r.col2}", icon="CHECKMARK" if r.state == "ok" else "ERROR")
        box = lay.box()
        box.label(text=s.health_head or "Sog'liq indeksi", icon="HEART")
        draw_list(box, s, "health_rows", "health_index", 4)
        box.operator("sath.show_asset", icon="RESTRICT_SELECT_OFF")
        box = lay.box()
        box.label(text="Vaqt mashinasi", icon="TIME")
        box.prop(s, "time_hours")
        if s.time_note:
            box.label(text=s.time_note)
        lay.operator("sath.open_web", text="Dispetcher paneli (web)", icon="URL").tab = "mon"


class SATH_PT_twin_sims(SathPanel, bpy.types.Panel):
    bl_label = "Egizak simulyatsiyalari"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 51
    sath_needs = frozenset({"login", "model"})
    sath_perm = "sim.run"

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.label(text="Natija → timeline (namuna GES: «GES obyektlari»)", icon="OUTLINER_OB_GROUP_INSTANCE")
        col = lay.column(align=True)
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
            lay.label(text=s.twin_note, icon="INFO")


def register(api):
    api.adopt("twin", ops_twin)
    api.register_classes("twin", [SATH_PT_twin, SATH_PT_twin_sims])
