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
        self.dropped = False  # reset() dan keyin: hech qanday callback chaqirilmaydi
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
        self.on_finished: Callable[[Task, str], None] | None = None  # task.* hodisalari (ui_tasks ulaydi)

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
        on_cancel: Callable[[], None] | None = None,
    ) -> Task | None:
        """Vazifani boshlaydi; shu `key` bilan (bekor qilinmagan) vazifa ishlayotgan bo'lsa None (takror rad etildi).
        on_cancel() — vazifa bekor qilingan holda tugaganda (Cancelled ham) asosiy oqimda bir marta; reset() dan keyin
        chaqirilmaydi."""
        if key is not None and self.running(key):
            return None
        task = Task(title, key, cancellable, quiet)
        if self.inline:
            outcome = "failed"
            try:  # callback xato bersa ham on_finished chaqiriladi (pump() bilan bir xil); xato chaqiruvchiga o'tadi
                try:
                    result = fn(TaskContext(task))
                except Cancelled:
                    outcome = "cancelled"
                    if on_cancel is not None:
                        on_cancel()
                    return task
                except Exception as e:
                    if on_error is None:
                        raise
                    on_error(e)
                    return task
                outcome = "done"
                if on_done is not None:
                    on_done(result)
                return task
            finally:
                self._finished(task, outcome)
        self._active.append(task)
        threading.Thread(
            target=self._work, args=(task, fn, on_done, on_error, on_cancel), name=f"sath:{title}", daemon=True
        ).start()
        return task

    def _work(self, task: Task, fn, on_done, on_error, on_cancel) -> None:
        try:
            result = fn(TaskContext(task))
        except BaseException as e:  # noqa: BLE001 — asosiy oqimga yetkaziladi
            self._q.put((task, None, on_error, on_cancel, None, e))
            return
        self._q.put((task, on_done, None, on_cancel, result, None))

    def pump(self) -> int:
        """Asosiy oqimda: tugagan vazifalarning callbacklarini chaqiradi. Qaytaradi: nechta vazifa yakunlandi."""
        n = 0
        while True:
            try:
                task, on_done, on_error, on_cancel, result, exc = self._q.get_nowait()
            except queue.Empty:
                return n
            n += 1
            if task in self._active:
                self._active.remove(task)
            if task.dropped:
                continue
            if task.cancelled or isinstance(exc, Cancelled):
                outcome = "cancelled"
            elif exc is not None:
                outcome = "failed"
            else:
                outcome = "done"
            try:
                if outcome == "cancelled":
                    if on_cancel is not None:
                        on_cancel()
                elif outcome == "failed":
                    if on_error is not None:
                        on_error(exc)
                    else:
                        self.on_error_default(task, exc)
                elif on_done is not None:
                    on_done(result)
            except Exception as cb_exc:  # noqa: BLE001 — bitta callback xatosi pompani to'xtatmasin
                self.on_error_default(task, cb_exc)
            self._finished(task, outcome)

    def _finished(self, task: Task, outcome: str) -> None:
        if self.on_finished is None:
            return
        try:
            self.on_finished(task, outcome)
        except Exception as e:  # noqa: BLE001 — hodisa obunachisi pompani to'xtatmasin
            self.on_error_default(task, e)

    def running(self, key: str) -> bool:
        """Bekor qilingan vazifa hisoblanmaydi: X bosilgach shu kalit bilan darhol qayta boshlash mumkin (eski ishchi
        tugaguncha `active()` da qoladi, natijasi tashlanadi; status bar uni ko'rsatmaydi)."""
        return any(t.key == key and not t.cancelled for t in self._active)

    def active(self) -> list[Task]:
        """Barcha ishchisi hali tugamagan vazifalar (bekor qilinganlari ham — pompa ularni kutadi)."""
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

    def cancel_prefix(self, prefix: str, *, drop: bool = False) -> int:
        """Kaliti `prefix` bilan boshlanadigan vazifalarni bekor qiladi (modul o'chirilganda: `<mod_id>.`).
        cancellable=False ham — modul kodi endi ro'yxatda emas, natijasi qo'llanmasligi kerak. Qaytaradi: nechta
        yangi bekor qilindi. drop=True (core/host.py — modul o'chirilganda): bu vazifalar (oldin bekor qilinganlari
        ham) `dropped` — pump() ularning on_cancel/on_done/on_error va on_finished ini chaqirmaydi (o'chirilgan modul
        yopilmalari ishlamaydi); ishchi tugaguncha active() da qoladi."""
        n = 0
        for t in self._active:
            if t.key is None or not t.key.startswith(prefix):
                continue
            if drop:
                t.dropped = True
            if not t.cancelled:
                t.cancel()
                n += 1
        return n

    def reset(self) -> None:
        """O'chirish yo'li (addon unregister): hammasini bekor qiladi, ro'yxatni tozalaydi, navbatdagi natijalarni
        callbacksiz tashlaydi — qayta yoqilganda kalitlar bloklanib qolmaydi."""
        self.cancel_all()
        for t in self._active:
            t.dropped = True
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
