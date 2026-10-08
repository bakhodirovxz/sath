"""Fon vazifalari (K3): tarmoq/og'ir ish daemon oqimda, natija va xato asosiy oqimda (`pump()`).

bpy ga bog'liq emas — pytest bilan sinaladi. Blender ulagichi (timer, status bar, operatorlar): core/ui_tasks.py.
Qoida: `fn(ctx)` bpy ga TEGMAYDI; `on_done`/`on_error` faqat `pump()` dan (asosiy oqim) chaqiriladi.
`inline=True` (Blender -b) — hammasi sinxron: headless testlar ketma-ket ishlaydi.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

_ids = itertools.count(1)


class Cancelled(Exception):
    """Vazifa bekor qilindi (ctx.check/ctx.sleep tashlaydi; natija tashlanadi, xato ko'rsatilmaydi)."""


class Task:
    def __init__(self, title: str, key: str | None, cancellable: bool, quiet: bool):
        self.id = next(_ids)
        self.title = title
        self.key = key
        self.cancellable = cancellable
        self.quiet = quiet  # status barda ko'rsatilmaydi (masalan monitoring tiki)
        self.frac: float | None = None
        self.text = ""
        self._cancel = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()


class TaskContext:
    def __init__(self, task: Task):
        self._task = task

    @property
    def cancelled(self) -> bool:
        return self._task.cancelled

    def check(self) -> None:
        if self._task.cancelled:
            raise Cancelled()

    def progress(self, frac: float | None, text: str = "") -> None:
        self._task.frac = None if frac is None else max(0.0, min(1.0, float(frac)))
        self._task.text = text

    def sleep(self, seconds: float) -> None:
        if self._task._cancel.wait(seconds):
            raise Cancelled()


def _print_error(task: Task, exc: BaseException) -> None:
    print(f"[sath] {task.title}: {exc}", flush=True)
    traceback.print_exception(type(exc), exc, exc.__traceback__)


class TaskManager:
    def __init__(self) -> None:
        self.inline = False
        self.on_error_default: Callable[[Task, BaseException], None] = _print_error
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._active: list[Task] = []

    def run(
        self,
        title: str,
        fn: Callable[[TaskContext], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        *,
        key: str | None = None,
        cancellable: bool = True,
        quiet: bool = False,
    ) -> Task | None:
        """Vazifani boshlaydi; shu `key` bilan vazifa ishlayotgan bo'lsa None (takror rad etildi)."""
        if key is not None and self.running(key):
            return None
        task = Task(title, key, cancellable, quiet)
        if self.inline:
            try:
                result = fn(TaskContext(task))
            except Cancelled:
                return task
            except Exception as e:
                if on_error is None:
                    raise
                on_error(e)
                return task
            if on_done is not None:
                on_done(result)
            return task
        self._active.append(task)
        threading.Thread(
            target=self._work, args=(task, fn, on_done, on_error), name=f"sath:{title}", daemon=True
        ).start()
        return task

    def _work(self, task: Task, fn, on_done, on_error) -> None:
        try:
            result = fn(TaskContext(task))
        except BaseException as e:  # noqa: BLE001 — asosiy oqimga yetkaziladi
            self._q.put((task, None, on_error, None, e))
            return
        self._q.put((task, on_done, None, result, None))

    def pump(self) -> int:
        """Asosiy oqimda: tugagan vazifalarning callbacklarini chaqiradi. Qaytaradi: nechta vazifa yakunlandi."""
        n = 0
        while True:
            try:
                task, on_done, on_error, result, exc = self._q.get_nowait()
            except queue.Empty:
                return n
            n += 1
            if task in self._active:
                self._active.remove(task)
            if task.cancelled or isinstance(exc, Cancelled):
                continue
            try:
                if exc is not None:
                    if on_error is not None:
                        on_error(exc)
                    else:
                        self.on_error_default(task, exc)
                elif on_done is not None:
                    on_done(result)
            except Exception as cb_exc:  # noqa: BLE001 — bitta callback xatosi pompani to'xtatmasin
                self.on_error_default(task, cb_exc)

    def running(self, key: str) -> bool:
        return any(t.key == key for t in self._active)

    def active(self) -> list[Task]:
        return list(self._active)

    def cancel(self, task_id: int) -> bool:
        for t in self._active:
            if t.id == task_id and t.cancellable:
                t.cancel()
                return True
        return False

    def cancel_all(self) -> None:
        for t in self._active:
            t.cancel()

    def reset(self) -> None:
        """O'chirish yo'li (addon unregister): hammasini bekor qiladi, ro'yxatni tozalaydi, navbatdagi natijalarni
        callbacksiz tashlaydi — qayta yoqilganda kalitlar bloklanib qolmaydi."""
        self.cancel_all()
        self._active.clear()
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    def drain(self, timeout: float = 30.0) -> None:
        """Barcha vazifalar tugaguncha pompalaydi (headless testlar: -b da timerlar ishlamaydi)."""
        deadline = time.monotonic() + timeout
        while self._active:
            self.pump()
            if time.monotonic() > deadline:
                raise TimeoutError(f"vazifalar tugamadi: {[t.title for t in self._active]}")
            time.sleep(0.01)
        self.pump()


TASKS = TaskManager()
