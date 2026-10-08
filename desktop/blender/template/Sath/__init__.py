"""Sath app template: Blender ochilganda GES-BIM ish muhiti — Sath ish joylari (BIM faol; workspaces.py),
N-panel ochiq (Sath yorlig'i), viewport Object-color rejimi (diff/alarm ranglari uchun), metr birliklari,
«Standard» view transform (3D ranglar web tokenlari bilan bir xil ko'rinsin)."""

import bpy
from bpy.app.handlers import persistent

from . import workspaces

_MSGBUS = object()  # msgbus obunasi egasi
_RETRY_S = 0.2  # finish() qayta urinish oralig'i (ish joyi almashishi keyingi siklda qo'llanadi)
_RETRIES = 5
_retry_left = [0]


def _no_bonsai_workspace():
    """Bonsai ning o'z «BIM» ish joyini qurishi o'chiriladi (Sath BIM bilan to'qnashmasin). Eski (0.3.x)
    userpref.blend da True bo'lishi mumkin — shuning uchun har ishga tushishda majburlanadi. Bonsai yo'q yoki
    o'chiq bo'lishi mumkin (getattr / try)."""
    try:
        for name, addon in bpy.context.preferences.addons.items():
            if name.rsplit(".", 1)[-1] == "bonsai":
                prefs = getattr(addon, "preferences", None)
                if prefs is not None and getattr(prefs, "should_setup_workspace", False):
                    prefs.should_setup_workspace = False
    except Exception as e:  # noqa: BLE001 — ish joylarini hech qachon buzmasin
        print("[sath] bonsai should_setup_workspace:", e, flush=True)


def _setup_screens():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.show_region_ui = True
                space.shading.color_type = "OBJECT"
                space.overlay.show_relationship_lines = False


def _setup_scenes():
    for scene in bpy.data.scenes:
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.length_unit = "METERS"
        scene.unit_settings.scale_length = 1.0
        scene.view_settings.view_transform = "Standard"  # tokens.py ranglari (sRGB) web dagidek, AgX emas


def _finish_all() -> bool:
    """Har oynada finish(); True — ko'rinayotgan ish joyida yakunlanmagan qadam qoldi."""
    wm = bpy.context.window_manager
    pending = False
    for win in getattr(wm, "windows", ()):
        if not workspaces.finish(win):
            ws = win.workspace
            pending = pending or (ws is not None and bool(ws.get(workspaces.TODO)))
    return pending


def _retry():
    _retry_left[0] -= 1
    if _finish_all() and _retry_left[0] > 0:
        return _RETRY_S
    return None


def _on_workspace(*_args):
    if _finish_all():
        _retry_left[0] = _RETRIES
        if not bpy.app.timers.is_registered(_retry):
            bpy.app.timers.register(_retry, first_interval=_RETRY_S)


def _activate_bim():
    """GUI: BIM tanlovi (ensure) startup da yo'qolgan bo'lsa — qayta (bir martalik taymer)."""
    wm = bpy.context.window_manager
    bim = workspaces.tagged(bpy.data).get("BIM")
    win = wm.windows[0] if wm is not None and wm.windows else None
    if bim is not None and win is not None and win.workspace is not None and win.workspace.get(workspaces.TAG) is None:
        win.workspace = bim
    return None


def _subscribe():
    bpy.msgbus.clear_by_owner(_MSGBUS)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Window, "workspace"), owner=_MSGBUS, args=(), notify=_on_workspace)


@persistent
def load_handler(_):
    _no_bonsai_workspace()
    _setup_screens()
    _setup_scenes()
    rep = workspaces.ensure(bpy.context)
    if rep["created"] or rep["removed"]:
        print("[sath] ish joylari:", rep, flush=True)
    if not bpy.app.background and not bpy.app.timers.is_registered(_activate_bim):
        bpy.app.timers.register(_activate_bim, first_interval=0.1)


@persistent
def cancel_chain(_):
    workspaces.cancel_chain()  # boshqa fayl yuklanmoqda — tab tartibi zanjiri uning ish joylariga tegmasin


@persistent
def resubscribe(_):
    _subscribe()  # fayl yuklanganda msgbus obunalari tozalanadi
    if not bpy.app.background:
        _retry_left[0] = _RETRIES  # Simulation faol holda saqlangan fayl ham Graph editor oladi
        if not bpy.app.timers.is_registered(_retry):
            bpy.app.timers.register(_retry, first_interval=_RETRY_S)


class SATH_OT_reset_workspaces(bpy.types.Operator):
    """Sath ish joylarini (BIM, Compare, Simulation, SCADA) tiklash va zavod ish joylarini (Shading, Rendering,
    Sculpting, ...) O'CHIRISH"""

    bl_idname = "sath.reset_workspaces"
    bl_label = "Ish joylarini tiklash"
    bl_options = {"REGISTER"}

    rebuild: bpy.props.BoolProperty(
        name="Qaytadan qurish",
        description="Mavjud Sath ish joylarini o'chirib yangidan yaratish (hozir ochiq ish joyi saqlanadi)",
        default=False,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        rep = workspaces.ensure(context, rebuild=self.rebuild, activate=False)
        parts = []
        if rep["created"]:
            parts.append("yaratildi: " + ", ".join(rep["created"]))
        if rep["removed"]:
            parts.append("olib tashlandi: " + ", ".join(rep["removed"]))
        if rep["kept"]:
            parts.append("ochiq bo'lgani uchun saqlandi: " + ", ".join(rep["kept"]))
        self.report({"INFO"}, "Ish joylari: " + ("; ".join(parts) or "o'zgarish yo'q"))
        return {"FINISHED"}


_HANDLERS = (
    (bpy.app.handlers.load_factory_startup_post, load_handler),
    (bpy.app.handlers.load_post, resubscribe),
    (bpy.app.handlers.load_pre, cancel_chain),
)
_TIMERS = (_retry, _activate_bim)


def register():
    _no_bonsai_workspace()
    bpy.utils.register_class(SATH_OT_reset_workspaces)
    for lst, fn in _HANDLERS:
        if fn not in lst:
            lst.append(fn)
    _subscribe()


def unregister():
    workspaces.cancel_chain()
    bpy.msgbus.clear_by_owner(_MSGBUS)
    for fn in _TIMERS:
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    for lst, fn in _HANDLERS:
        if fn in lst:
            lst.remove(fn)
    bpy.utils.unregister_class(SATH_OT_reset_workspaces)
