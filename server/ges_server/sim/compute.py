"""Analitik simulyatsiyani alohida jarayonda, vaqt chegarasi bilan bajarish (J12).

Sof Python sikli thread dan to'xtatilmaydi (GIL) — shuning uchun hisob `multiprocessing` (spawn)
jarayonida bajariladi; muddat o'tsa jarayon o'ldiriladi. Bu modul faqat `ges_sim` ni import qiladi
(bola jarayon tez ishga tushsin). `isolate=False` — shu jarayonda (testlar, GES_SIM_ISOLATE=false).

SIM-02: bola jarayonga xotira chegarasi qo'yiladi (`GES_SIM_MEM_MB`, default 4096; 0 — o'chiq):
POSIX — `resource.setrlimit(RLIMIT_AS)`, Windows — Job Object (`JOB_OBJECT_LIMIT_PROCESS_MEMORY`).
Oshib ketsa ajratish muvaffaqiyatsiz → `MemoryError` → ish xato bilan tugaydi, server jarayoni tirik qoladi.
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import sys

log = logging.getLogger(__name__)
DEFAULT_MEM_MB = 4096


def default_mem_mb() -> int:
    try:
        return max(0, int(os.environ.get("GES_SIM_MEM_MB", DEFAULT_MEM_MB)))
    except ValueError:
        return DEFAULT_MEM_MB


def _limit_memory_windows(limit: int) -> bool:
    """Joriy jarayonni xotira limitli Job Object ga biriktiradi (Windows 8+ ichma-ich job ruxsat)."""
    import ctypes
    from ctypes import wintypes

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXT(ctypes.Structure):
        _fields_ = [
            ("Basic", BASIC),
            ("Io", IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = EXT()
    info.Basic.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = limit
    ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = Extended
    if not ok:
        return False
    # handle ataylab yopilmaydi — jarayon tugaguncha job yashaydi
    return bool(k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()))


def limit_memory(mem_mb: int) -> bool:
    """Joriy (bola) jarayonga xotira chegarasi; qo'yilgan bo'lsa True."""
    if mem_mb <= 0:
        return False
    limit = int(mem_mb) * 1024 * 1024
    try:
        if sys.platform == "win32":
            return _limit_memory_windows(limit)
        import resource

        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
        return True
    except Exception:  # noqa: BLE001 — chegara qo'yilmasa ham hisob davom etadi (log)
        log.warning("sim: xotira chegarasini qo'yib bo'lmadi", exc_info=True)
        return False


class SimTimeout(Exception):
    pass


def compute(kind: str, params: dict) -> dict:
    """Bola jarayonda ham, to'g'ridan-to'g'ri ham chaqiriladi."""
    from ges_sim import catalog, custom, scenario

    if kind == "hydro":
        return scenario.run(params)
    if kind == "custom":
        return custom.run(params["template"], params.get("inputs") or {})
    if kind in catalog.REGISTRY:
        return catalog.run(kind, params)
    if kind == "_sleep":  # test: vaqt chegarasi
        import time

        time.sleep(float(params.get("seconds", 1)))
        return {"summary": {}}
    if kind == "_alloc":  # test: xotira chegarasi
        buf = bytearray(int(params.get("mb", 1)) * 1024 * 1024)
        return {"summary": {"bytes": len(buf)}}
    raise ValueError(f"Noma'lum simulyatsiya turi: {kind}")


def _child(conn, kind: str, params: dict, mem_mb: int = 0) -> None:
    try:
        limit_memory(mem_mb)
        out = compute(kind, params)
        conn.send(("ok", json.dumps(out)))
    except Exception as e:  # noqa: BLE001 — xato matni ota jarayonga
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def run_isolated(kind: str, params: dict, timeout_s: float, mem_mb: int | None = None) -> dict:
    """Alohida jarayonda; muddat o'tsa SimTimeout, xato (shu jumladan xotira limiti — MemoryError)
    bo'lsa RuntimeError."""
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    mem = default_mem_mb() if mem_mb is None else mem_mb
    proc = ctx.Process(target=_child, args=(child, kind, params, mem), daemon=True)
    proc.start()
    child.close()
    try:
        if parent.poll(timeout_s):
            try:
                status, payload = parent.recv()
            except EOFError:  # bola jarayon javobsiz tugadi (masalan, xotira chegarasi)
                status, payload = "err", "hisob jarayoni kutilmaganda tugadi (xotira chegarasi?)"
        else:
            proc.kill()
            raise SimTimeout(
                f"hisob {timeout_s:.0f} s ichida tugamadi — parametrlarni (davomiylik, qadam, "
                "oraliqlar soni) kamaytiring"
            )
    finally:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        parent.close()
    if status != "ok":
        raise RuntimeError(payload)
    return json.loads(payload)
