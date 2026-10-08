"""core.tasks (K3): ishchi oqim, asosiy oqimga navbat, kalit bo'yicha takrorni rad etish, bekor qilish, inline rejim."""

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core.tasks import Cancelled, TaskManager  # noqa: E402


def test_run_returns_immediately_and_done_on_pump_thread():
    tm = TaskManager()
    seen = {}
    t0 = time.perf_counter()
    task = tm.run("sekin", lambda ctx: (time.sleep(0.2), 42)[1], lambda r: seen.update(r=r, th=threading.current_thread()))
    assert time.perf_counter() - t0 < 0.05 and task is not None
    assert tm.active() == [task]
    tm.drain(5)
    assert seen == {"r": 42, "th": threading.main_thread()}
    assert tm.active() == []


def test_same_key_rejected_while_running():
    tm = TaskManager()
    ev = threading.Event()
    a = tm.run("a", lambda ctx: ev.wait(5), key="review.diff")
    b = tm.run("b", lambda ctx: 1, key="review.diff")
    assert a is not None and b is None and tm.running("review.diff")
    ev.set()
    tm.drain(5)
    assert not tm.running("review.diff")


def test_error_goes_to_on_error_on_main_thread():
    tm = TaskManager()
    got = {}

    def boom(ctx):
        raise ValueError("yomon")

    tm.run("x", boom, lambda r: got.update(done=True), lambda e: got.update(err=str(e), th=threading.current_thread()))
    tm.drain(5)
    assert got == {"err": "yomon", "th": threading.main_thread()}


def test_error_without_handler_uses_default():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append((task.title, str(e)))
    tm.run("x", lambda ctx: 1 / 0)
    tm.drain(5)
    assert got and got[0][0] == "x" and "division" in got[0][1]


def test_callback_exception_does_not_break_pump():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append(str(e))
    tm.run("a", lambda ctx: 1, lambda r: (_ for _ in ()).throw(RuntimeError("apply xato")))
    tm.run("b", lambda ctx: 2, lambda r: got.append(r))
    tm.drain(5)
    assert "apply xato" in got and 2 in got


def test_cancel_wakes_sleep_and_drops_result():
    tm = TaskManager()
    got = []

    def slow(ctx):
        for _ in range(100):
            ctx.sleep(0.5)
        return "tugadi"

    task = tm.run("sekin", slow, got.append, got.append)
    t0 = time.perf_counter()
    assert tm.cancel(task.id) is True
    tm.drain(5)
    assert time.perf_counter() - t0 < 1.0
    assert got == []  # bekor qilingan vazifaning natijasi ham, xatosi ham tashlanadi


def test_progress_visible_from_main():
    tm = TaskManager()
    ev = threading.Event()

    def work(ctx):
        ctx.progress(0.5, "yarmi")
        ev.wait(5)

    task = tm.run("p", work)
    for _ in range(100):
        if task.frac == 0.5:
            break
        time.sleep(0.01)
    assert (task.frac, task.text) == (0.5, "yarmi")
    ev.set()
    tm.drain(5)


def test_inline_mode_is_synchronous_and_raises_without_handler():
    tm = TaskManager()
    tm.inline = True
    got = []
    assert tm.run("i", lambda ctx: 7, got.append) is not None and got == [7]
    with pytest.raises(ZeroDivisionError):
        tm.run("i", lambda ctx: 1 / 0)
    tm.run("i", lambda ctx: 1 / 0, None, lambda e: got.append(type(e).__name__))
    assert got == [7, "ZeroDivisionError"] and tm.active() == []


def test_cancel_all():
    tm = TaskManager()
    for i in range(3):
        tm.run(f"t{i}", lambda ctx: [ctx.sleep(0.2) for _ in range(50)])
    tm.cancel_all()
    tm.drain(5)
    assert tm.active() == []


def test_cancelled_exception_is_silent():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append(e)

    def work(ctx):
        raise Cancelled()

    tm.run("c", work)
    tm.drain(5)
    assert got == []


def test_reset_clears_active_and_queue_without_callbacks():
    tm = TaskManager()
    called = []
    tm.run("u", lambda c: c.sleep(5), called.append, key="k")
    assert tm.running("k")
    tm.reset()
    assert not tm.running("k") and tm.active() == []
    assert tm.run("u2", lambda c: 1, called.append, key="k") is not None  # kalit bo'shadi
    tm.drain(5)
    tm.pump()
    assert called == [1]


def test_cancelled_task_frees_key_immediately():
    """X: vazifa ishchisi tarmoqda qotgan bo'lsa ham kalit darhol bo'shaydi; eski natija tashlanadi."""
    tm = TaskManager()
    gate = threading.Event()
    got = []
    a = tm.run("diff", lambda ctx: (gate.wait(5), "eski")[1], got.append, key="K")
    assert tm.cancel(a.id) is True
    assert not tm.running("K")
    assert a in tm.active() and a.cancelled  # ishchi hali tugamagan — pompa kutadi
    b = tm.run("diff", lambda ctx: "yangi", got.append, key="K")
    assert b is not None and tm.running("K")
    gate.set()
    tm.drain(5)
    assert got == ["yangi"]


def test_on_cancel_called_once_on_cancel_only():
    tm = TaskManager()
    calls = []
    t = tm.run("c", lambda ctx: [ctx.sleep(0.2) for _ in range(50)], calls.append, on_cancel=lambda: calls.append("x"))
    tm.cancel(t.id)
    tm.drain(5)
    tm.pump()
    assert calls == ["x"]

    calls.clear()
    tm.run("ok", lambda ctx: 5, calls.append, on_cancel=lambda: calls.append("x"))
    tm.drain(5)
    assert calls == [5]  # muvaffaqiyatda on_cancel yo'q


def test_on_cancel_called_when_worker_raises_cancelled():
    tm = TaskManager()
    calls = []

    def work(ctx):
        raise Cancelled()

    tm.run("c", work, calls.append, calls.append, on_cancel=lambda: calls.append("x"))
    tm.drain(5)
    assert calls == ["x"]
    tm.inline = True
    tm.run("i", work, calls.append, calls.append, on_cancel=lambda: calls.append("y"))
    assert calls == ["x", "y"]


def test_on_cancel_not_called_after_reset():
    tm = TaskManager()
    calls = []
    t = tm.run("u", lambda c: c.sleep(5), on_cancel=lambda: calls.append("x"))
    tm.reset()
    time.sleep(0.2)  # ishchi Cancelled bilan tugab navbatga yozadi
    tm.pump()
    assert calls == [] and t.dropped


def test_cancel_prefix_cancels_only_module_tasks():
    tm = TaskManager()
    ev = threading.Event()
    a = tm.run("a", lambda ctx: ev.wait(5), key="review.diff")
    b = tm.run("b", lambda ctx: ev.wait(5), key="sim.catalog", cancellable=False)
    c = tm.run("c", lambda ctx: ev.wait(5), key="server.open")
    assert tm.cancel_prefix("review.") == 1 and a.cancelled and not c.cancelled
    assert tm.cancel_prefix("sim.") == 1 and b.cancelled  # modul o'chirilganda cancellable=False ham
    ev.set()
    tm.drain(5)


def test_on_finished_reports_outcome():
    tm = TaskManager()
    seen = []
    tm.on_finished = lambda task, outcome: seen.append((task.title, outcome))
    tm.run("ok", lambda ctx: 1)
    tm.run("xato", lambda ctx: 1 / 0, on_error=lambda e: None)
    t = tm.run("bekor", lambda ctx: ctx.sleep(5))
    t.cancel()
    tm.drain(5)
    assert sorted(seen) == [("bekor", "cancelled"), ("ok", "done"), ("xato", "failed")]
    tm.inline = True
    tm.run("inline", lambda ctx: 2)
    assert seen[-1] == ("inline", "done")


def test_inline_callback_error_still_reports_finished():
    tm = TaskManager()
    tm.inline = True
    seen = []
    tm.on_finished = lambda task, outcome: seen.append((task.title, outcome))

    def boom(_):
        raise ValueError("callback")

    with pytest.raises(ValueError):
        tm.run("done-cb", lambda ctx: 1, on_done=boom)
    with pytest.raises(ValueError):
        tm.run("err-cb", lambda ctx: 1 / 0, on_error=boom)
    with pytest.raises(ValueError):
        tm.run("cancel-cb", lambda ctx: ctx.check() or ctx._task.cancel() or ctx.check(), on_cancel=lambda: boom(0))
    assert seen == [("done-cb", "done"), ("err-cb", "failed"), ("cancel-cb", "cancelled")]
