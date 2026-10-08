"""Blender ichida o'lchov: addon register vaqti, RSS, sintetik IFC (N element) ni Bonsai da ochish.

  blender -b --python desktop/tests/perf_blender.py -- [--n 2000]
Natija: `PERF {...}` (json) — desktop/tests/perf_baseline.py o'qiydi.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_headless  # noqa: E402


def rss_mb() -> float | None:
    if sys.platform != "win32":
        return None

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (n, ctypes.c_size_t)
            for n in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]  # fmt: skip

    c = PMC()
    c.cb = ctypes.sizeof(c)
    from ctypes import wintypes

    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE  # 64-bit handle kesilmasin
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return None
    return c.WorkingSetSize / 2**20


def synthetic_ifc(n: int, path: Path) -> Path:
    import ifcopenshell.api as api
    import numpy as np

    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="perf")
    api.run("unit.assign_unit", f)
    model = api.run("context.add_context", f, context_type="Model")
    body = api.run(
        "context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", f, relating_object=proj, products=[site])
    for i in range(n):
        el = api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy", name=f"E{i}")
        rep = api.run("geometry.add_wall_representation", f, context=body, length=1.0, height=1.0, thickness=1.0)
        api.run("geometry.assign_representation", f, product=el, representation=rep)
        m = np.eye(4)
        m[0][3], m[1][3] = (i % 100) * 2.0, (i // 100) * 2.0
        api.run("geometry.edit_object_placement", f, product=el, matrix=m)
        api.run("spatial.assign_container", f, relating_structure=site, products=[el])
    f.write(str(path))
    return path


def enable_bonsai() -> None:
    bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
    assert "bl_ext.user_default.bonsai" in bpy.context.preferences.addons, "Bonsai yoqilmadi"


def register_sath() -> float:
    """Faqat import + register vaqti (wheel ochish va yo'l sozlash taymerdan tashqarida). ms qaytaradi."""
    import importlib

    blender_headless.unpack_wheels()
    installed = "bl_ext.user_default.sath"
    if installed in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_disable(module=installed)
    sys.path.insert(0, str(blender_headless.ADDON_DIR.parent))
    t = time.perf_counter()
    importlib.import_module("sath").register()
    return round((time.perf_counter() - t) * 1000, 1)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []

    def opt(name: str, default: str | None = None) -> str | None:
        return argv[argv.index(name) + 1] if name in argv else default

    n = int(opt("--n", "2000"))
    if "--budget" in argv:  # spec §5: register vaqti va register da yangi yuklangan og'ir modullar
        if "--bonsai" in argv:
            enable_bonsai()
        before = set(sys.modules)
        ms = register_sath()
        from sath.core import budget

        heavy = budget.heavy_loaded(set(sys.modules) - before)
        print("BUDGET " + json.dumps({"register_ms": ms, "heavy": heavy}), flush=True)
        return
    if "--gen" in argv:  # alohida jarayon: IFC yaratish (RSS ni ifloslamasin)
        synthetic_ifc(n, Path(opt("--gen")))
        return
    if "--cold" in argv:  # sovuq start: Bonsai + Sath, keyin chiqish
        enable_bonsai()
        register_sath()
        return
    out: dict = {"rss_blender_mb": rss_mb()}
    enable_bonsai()
    out["rss_bonsai_mb"] = rss_mb()
    out["addon_register_ms"] = register_sath()
    out["rss_sath_mb"] = rss_mb()
    ifc = opt("--ifc")
    if ifc:
        path = Path(ifc)
        out["ifc_elements"] = n
        out["ifc_size_mb"] = round(path.stat().st_size / 2**20, 2)
        t = time.perf_counter()
        bpy.ops.bim.load_project(filepath=str(path))
        out["ifc_open_s"] = round(time.perf_counter() - t, 2)
        out["rss_ifc_mb"] = rss_mb()
    print("PERF " + json.dumps(out), flush=True)


main()
