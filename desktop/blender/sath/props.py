"""Sahna holati: joriy model/versiya, ro'yxat keshlari (loyihalar, modellar, versiyalar, ...)."""

from __future__ import annotations

import bpy

from . import session


def _on_project(self, context):
    if session.is_logged_in():
        bpy.ops.sath.refresh_models()


def _on_model(self, context):
    if session.is_logged_in():
        bpy.ops.sath.refresh_versions()


def _on_issue(self, context):
    if session.is_logged_in():
        bpy.ops.sath.show_issue()


def _on_cr(self, context):
    if session.is_logged_in():
        bpy.ops.sath.show_cr()


def _on_sim_kind(self, context):
    if bpy.ops.sath.sim_pick.poll():
        bpy.ops.sath.sim_pick()


def _sel_items(self, context):
    return [(v.split("=", 1)[0], v.split("=", 1)[-1], "") for v in self.options.split(";") if v]


class GesListItem(bpy.types.PropertyGroup):
    """Universal ro'yxat elementi: server obyekti id + ustunlar."""

    item_id: bpy.props.IntProperty()
    name: bpy.props.StringProperty()
    col2: bpy.props.StringProperty()
    col3: bpy.props.StringProperty()
    col4: bpy.props.StringProperty()
    guid: bpy.props.StringProperty()
    state: bpy.props.StringProperty()
    number: bpy.props.IntProperty()


class GesSimField(bpy.types.PropertyGroup):
    """Simulyatsiya forma maydoni (server katalogidan)."""

    key: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ftype: bpy.props.StringProperty()  # number | int | bool | select | series | text
    hint: bpy.props.StringProperty()
    options: bpy.props.StringProperty()  # "val=label;val=label"
    value_str: bpy.props.StringProperty()
    value_bool: bpy.props.BoolProperty()
    value_sel: bpy.props.EnumProperty(items=_sel_items)


class GesScene(bpy.types.PropertyGroup):
    status: bpy.props.StringProperty(name="Holat", default="")
    update_version: bpy.props.StringProperty(default="")  # serverda yangiroq paket bo'lsa
    project_id: bpy.props.IntProperty(default=0)
    model_id: bpy.props.IntProperty(default=0)
    version_id: bpy.props.IntProperty(default=0)
    version_number: bpy.props.IntProperty(default=0)
    model_name: bpy.props.StringProperty(default="")
    password: bpy.props.StringProperty(name="Parol", subtype="PASSWORD", default="")
    projects: bpy.props.CollectionProperty(type=GesListItem)
    projects_index: bpy.props.IntProperty(default=-1, update=_on_project)
    models: bpy.props.CollectionProperty(type=GesListItem)
    models_index: bpy.props.IntProperty(default=-1, update=_on_model)
    versions: bpy.props.CollectionProperty(type=GesListItem)
    versions_index: bpy.props.IntProperty(default=-1)
    commit_message: bpy.props.StringProperty(name="Izoh", default="")
    submit_after_commit: bpy.props.BoolProperty(name="Darhol tasdiqqa yuborish", default=False)
    new_model_name: bpy.props.StringProperty(name="Yangi model nomi", default="")
    notifications: bpy.props.CollectionProperty(type=GesListItem)
    notifications_index: bpy.props.IntProperty(default=-1)
    issues: bpy.props.CollectionProperty(type=GesListItem)
    issues_index: bpy.props.IntProperty(default=-1, update=_on_issue)
    issue_detail: bpy.props.StringProperty(default="")
    crs: bpy.props.CollectionProperty(type=GesListItem)
    crs_index: bpy.props.IntProperty(default=-1, update=_on_cr)
    cr_detail: bpy.props.StringProperty(default="")
    comment_text: bpy.props.StringProperty(name="Izoh", default="")
    my_role: bpy.props.StringProperty(default="")
    diff_note: bpy.props.StringProperty(default="")
    sim_kinds: bpy.props.CollectionProperty(type=GesListItem)
    sim_kind_index: bpy.props.IntProperty(default=-1, update=_on_sim_kind)
    sim_fields: bpy.props.CollectionProperty(type=GesSimField)
    sim_status: bpy.props.StringProperty(default="")
    sim_results: bpy.props.CollectionProperty(type=GesListItem)
    sim_water_level: bpy.props.FloatProperty(default=-1e9)
    sim_job_id: bpy.props.IntProperty(default=0)
    safety_head: bpy.props.StringProperty(default="")
    safety_rows: bpy.props.CollectionProperty(type=GesListItem)
    sensors: bpy.props.CollectionProperty(type=GesListItem)
    sensors_index: bpy.props.IntProperty(default=-1)
    monitor_on: bpy.props.BoolProperty(default=False)
    monitor_status: bpy.props.StringProperty(default="")
    monitor_color: bpy.props.BoolProperty(name="3D alarm rangi", default=True)
    monitor_water: bpy.props.BoolProperty(name="Suv sathi sensoridan 3D tekislik", default=True)


CLASSES = (GesListItem, GesSimField, GesScene)


LIST_FIELDS = ("item_id", "name", "col2", "col3", "col4", "guid", "state", "number")


def snapshot(s) -> dict:
    """Scene.ges ni oddiy dict ga (Bonsai fresh session — read_homefile — dan oldin)."""
    out = {}
    for prop in s.bl_rna.properties:
        name = prop.identifier
        if name in ("rna_type", "name", "password"):
            continue
        v = getattr(s, name)
        if prop.type == "COLLECTION":
            out[name] = [
                {f: getattr(it, f) for f in (LIST_FIELDS if hasattr(it, "guid") else _sim_fields(it))}
                for it in v
            ]
        elif prop.type in ("STRING", "INT", "FLOAT", "BOOLEAN"):
            out[name] = v
    return out


def _sim_fields(it) -> tuple:
    return ("key", "label", "ftype", "hint", "options", "value_str", "value_bool", "value_sel")


def restore(s, snap: dict) -> None:
    """snapshot() natijasini yangi Scene.ges ga (indekslar oxirida — update callbacklar uchun)."""
    idx = {}
    for name, v in snap.items():
        if isinstance(v, list):
            coll = getattr(s, name)
            coll.clear()
            for row in v:
                it = coll.add()
                for k, val in row.items():
                    try:
                        setattr(it, k, val)
                    except (TypeError, ValueError):  # value_sel: options hali yo'q edi
                        pass
        elif name.endswith("_index"):
            idx[name] = v
        else:
            setattr(s, name, v)
    for name, v in idx.items():
        setattr(s, name, v)


def fill(coll, rows: list[dict]) -> None:
    """CollectionProperty ni qayta to'ldiradi."""
    coll.clear()
    for r in rows:
        it = coll.add()
        for k, v in r.items():
            setattr(it, k, v)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.ges = bpy.props.PointerProperty(type=GesScene)


def unregister():
    del bpy.types.Scene.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
