"""K3: asinxron yo'l (fon rejimida majburan): operator darhol qaytadi, natija asosiy oqimda, epoch eski natijani
tashlaydi, pompa timer Bonsai read_homefile dan omon qoladi, unregister uzoq vazifada osilmaydi."""

import threading
import time

import bpy


def run(ctx):
    from sath import session
    from sath.core import ui_tasks
    from sath.core.tasks import TASKS
    from sath.shared.server_client import ServerError, TransferCancelled

    assert TASKS.inline is True  # -b da default sinxron (boshqa headless testlar uchun)
    TASKS.inline = False
    try:
        # 1) asosiy oqimda apply
        seen = {}

        class Op:
            def report(self, level, msg):
                seen["report"] = (level, msg)

        t0 = time.perf_counter()
        r = ui_tasks.run_op(Op(), "sekin", lambda c: (time.sleep(0.3), 5)[1], lambda v: seen.update(v=v, th=threading.current_thread()), key="t.slow")
        assert r == {"FINISHED"} and time.perf_counter() - t0 < 0.1
        assert ui_tasks.run_op(Op(), "sekin", lambda c: 1, key="t.slow") == {"CANCELLED"}  # takror rad
        assert "allaqachon" in seen["report"][1]
        assert bpy.app.timers.is_registered(ui_tasks._pump)
        TASKS.drain(5)
        assert seen["v"] == 5 and seen["th"] is threading.main_thread()

        # 2) epoch: vazifa davomida sessiya almashsa natija qo'llanmaydi
        applied = []
        ui_tasks.run_op(Op(), "eski", lambda c: (time.sleep(0.2), 1)[1], applied.append)
        session.bump_epoch()
        TASKS.drain(5)
        assert applied == []
        assert "eskirdi" in bpy.context.scene.ges.status

        # 2b) cancellable=False: bekor qilib bo'lmaydi; stale matni epoch tashlanganda holatga yoziladi
        applied.clear()
        ui_tasks.run_op(Op(), "yuk", lambda c: (time.sleep(0.2), 1)[1], applied.append, key="t.nc", cancellable=False, stale="X-eskirgan")
        task = TASKS.active()[0]
        assert task.cancellable is False and TASKS.cancel(task.id) is False
        session.bump_epoch()
        TASKS.drain(5)
        assert applied == [] and "X-eskirgan" in bpy.context.scene.ges.status
        assert "qayta bajaring" not in bpy.context.scene.ges.status

        # 3) xato → scene.ges.status (fon rejimida popup yo'q)
        def boom(c):
            raise RuntimeError("server yiqildi")

        ui_tasks.run_op(Op(), "Farq", boom)
        TASKS.drain(5)
        assert "Farq: server yiqildi" in bpy.context.scene.ges.status

        # 4) persistent pompa: read_homefile dan keyin ham ro'yxatda
        ui_tasks.run_op(Op(), "uzun", lambda c: c.sleep(0.5))
        bpy.ops.wm.read_homefile(app_template="")
        assert bpy.app.timers.is_registered(ui_tasks._pump)
        TASKS.drain(5)

        # 4b) load_pre: fayl yuklash epoch ni oshiradi
        e0 = session.epoch()
        bpy.ops.wm.read_homefile(app_template="")
        assert session.epoch() > e0

        # 4c) async: epoch o'zgargach xato ko'rsatilmaydi va fail chaqirilmaydi
        called = []

        def late_fail(c):
            time.sleep(0.2)
            raise RuntimeError("eski xato")

        ui_tasks.run_op(Op(), "Eski", late_fail, fail=lambda e: called.append(e) or "x")
        session.bump_epoch()
        TASKS.drain(5)
        assert called == [] and "eskirdi" in bpy.context.scene.ges.status

        # 4d) async: TransferCancelled jim
        bpy.context.scene.ges.status = ""

        def cancelled(c):
            raise TransferCancelled()

        ui_tasks.run_op(Op(), "Bekor", cancelled)
        TASKS.drain(5)
        assert bpy.context.scene.ges.status == ""

        # 5) unregister uzoq vazifada osilmaydi (bekor qilinadi)
        ui_tasks.run_op(Op(), "juda uzun", lambda c: [c.sleep(1) for _ in range(60)])
        t0 = time.perf_counter()
        ui_tasks.unregister()
        assert time.perf_counter() - t0 < 1.0
        TASKS.drain(5)
        ui_tasks.register()

        # 6) inline yo'l: xato → op.report(ERROR) + CANCELLED (ValueError ham, fail matni ishlatiladi)
        TASKS.inline = True
        seen.clear()

        def bad(exc):
            def w(c):
                raise exc

            return w

        assert ui_tasks.run_op(Op(), "I", bad(ServerError(500, "boom"))) == {"CANCELLED"}
        assert seen["report"][0] == {"ERROR"} and "boom" in seen["report"][1]
        assert ui_tasks.run_op(Op(), "I", bad(ValueError("qiymat"))) == {"CANCELLED"}
        assert "qiymat" in seen["report"][1]
        assert ui_tasks.run_op(Op(), "I", bad(RuntimeError("x")), fail=lambda e: "maxsus") == {"CANCELLED"}
        assert seen["report"][1] == "maxsus"
        seen.clear()
        assert ui_tasks.run_op(Op(), "I", bad(TransferCancelled())) == {"CANCELLED"} and "report" not in seen
        assert ui_tasks.run_op(Op(), "I", lambda c: 1) == {"FINISHED"}
    finally:
        TASKS.inline = True
