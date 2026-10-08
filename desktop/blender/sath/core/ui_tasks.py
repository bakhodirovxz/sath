"""Fon vazifalarining Blender ulagichi (K3): pompa timer (0.1 s, persistent), status bar progressi va bekor qilish,
operatorlar uchun `run_op`. Fon rejimida (blender -b) TASKS.inline — hammasi sinxron, xato op.report ga.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import bpy

from .. import session
from ..shared.server_client import ServerError, TransferCancelled
from .tasks import TASKS, Task, TaskContext

_DEFAULT_ON_ERROR = TASKS.on_error_default
PUMP_INTERVAL = 0.1
EXPECTED: tuple[type[BaseException], ...] = (ServerError, RuntimeError)
MAX_SHOWN = 3


def _msg(e: BaseException) -> str:
    return str(getattr(e, "message", None) or e)


def _scene_ges():
    sc = getattr(bpy.context, "scene", None)
    return getattr(sc, "ges", None) if sc is not None else None


def status(text: str) -> None:
    g = _scene_ges()
    if g is not None:
        g.status = text


def show_error(title: str, msg: str) -> None:
    """Asosiy oqim: holat qatori + konsol + (GUI da) popup. Operator allaqachon tugagan — report ishlamaydi."""
    status(f"✖ {title}: {msg}")
    print(f"[sath] {title}: {msg}", flush=True)
    if bpy.app.background:  # -b da oyna bor, lekin popup_menu Blender'ni qulatadi
        return
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None or not wm.windows:
        return

    def draw(self, _context):
        for line in msg.splitlines()[:8]:
            self.layout.label(text=line)

    try:
        with bpy.context.temp_override(window=wm.windows[0]):
            wm.popup_menu(draw, title=title, icon="ERROR")
    except Exception:
        import traceback

        traceback.print_exc()  # popup ixtiyoriy — holat qatori va konsol allaqachon yozilgan


def _default_error(task: Task, exc: BaseException) -> None:
    if not isinstance(exc, EXPECTED):
        import traceback

        traceback.print_exception(type(exc), exc, exc.__traceback__)
    show_error(task.title, _msg(exc))


def _print_unexpected(e: BaseException) -> None:
    if not isinstance(e, EXPECTED):
        import traceback

        traceback.print_exception(type(e), e, e.__traceback__)


def _redraw_statusbar() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == "STATUSBAR":
                area.tag_redraw()


def _pump():
    # Timer qayta chaqiruvi istisno tashlasa Blender uni o'chiradi — shuning uchun hammasi ushlanadi.
    try:
        TASKS.pump()
        _redraw_statusbar()
    except Exception:
        import traceback

        traceback.print_exc()
    return PUMP_INTERVAL if TASKS.active() else None


def ensure_pump() -> None:
    if not TASKS.inline and not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, first_interval=PUMP_INTERVAL, persistent=True)


def run_op(
    op,
    title: str,
    work: Callable[[TaskContext], Any],
    apply: Callable[[Any], None] | None = None,
    *,
    key: str | None = None,
    fail: Callable[[BaseException], str | None] | None = None,
) -> set[str]:
    """Operator ishini fon vazifasiga aylantiradi.

    work(ctx) — ishchi oqimda, bpy ga TEGMAYDI; apply(natija) — asosiy oqimda.
    fail(xato) — asosiy oqimda holatni yozadi va ko'rsatiladigan matnni qaytaradi (None → xato matni).
    Sessiya/model almashgan bo'lsa (epoch) natija qo'llanmaydi."""
    ep = session.epoch()

    def done(result) -> None:
        if session.epoch() != ep:
            status(f"{title}: natija eskirdi (sessiya yoki model almashdi) — qayta bajaring")
            return
        if apply is not None:
            apply(result)

    def error(e: BaseException) -> None:
        if isinstance(e, TransferCancelled):
            return
        if session.epoch() != ep:
            status(f"{title}: natija eskirdi (sessiya yoki model almashdi) — qayta bajaring")
            return
        _print_unexpected(e)
        msg = (fail(e) if fail is not None else None) or _msg(e)
        show_error(title, msg)

    if TASKS.inline:
        try:
            TASKS.run(title, work, done, key=key)
        except TransferCancelled:
            return {"CANCELLED"}
        except Exception as e:
            _print_unexpected(e)
            op.report({"ERROR"}, (fail(e) if fail is not None else None) or _msg(e))
            return {"CANCELLED"}
        return {"FINISHED"}
    task = TASKS.run(title, work, done, error, key=key)
    if task is None:
        op.report({"WARNING"}, f"{title}: allaqachon bajarilmoqda")
        return {"CANCELLED"}
    ensure_pump()
    return {"FINISHED"}


def draw_tasks(self, _context) -> None:
    shown = [t for t in TASKS.active() if not t.quiet][:MAX_SHOWN]
    for t in shown:
        row = self.layout.row(align=True)
        text = t.title + (f" — {t.text}" if t.text else "")
        if t.frac is None:
            row.label(text=text, icon="SORTTIME")
        else:
            row.progress(factor=t.frac, type="BAR", text=text)
        if t.cancellable:
            row.operator("sath.task_cancel", text="", icon="X", emboss=False).task_id = t.id


class SATH_OT_task_cancel(bpy.types.Operator):
    """Fon vazifasini bekor qilish (natija tashlanadi)"""

    bl_idname = "sath.task_cancel"
    bl_label = "Bekor qilish"
    bl_options = {"INTERNAL"}
    task_id: bpy.props.IntProperty()

    def execute(self, context):
        return {"FINISHED"} if TASKS.cancel(self.task_id) else {"CANCELLED"}


@bpy.app.handlers.persistent
def _on_load_pre(*_args):
    """Fayl ochish/Ctrl+N (ifc.load dan tashqari ham): eski model uchun boshlangan natijalar tashlansin."""
    session.bump_epoch()


def register():
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)
    TASKS.inline = bpy.app.background
    TASKS.on_error_default = _default_error
    bpy.utils.register_class(SATH_OT_task_cancel)
    bpy.types.STATUSBAR_HT_header.prepend(draw_tasks)


def unregister():
    TASKS.reset()
    TASKS.on_error_default = _DEFAULT_ON_ERROR
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    bpy.types.STATUSBAR_HT_header.remove(draw_tasks)
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
    bpy.utils.unregister_class(SATH_OT_task_cancel)
