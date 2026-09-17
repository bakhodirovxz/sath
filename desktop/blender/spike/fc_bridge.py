"""SPIKE (throwaway): FreeCAD ni Blender jarayoniga yuklash va Part shape -> Blender mesh.

Ishga tushirish:
  blender -b --python fc_bridge.py            # headless
  blender --python fc_bridge.py               # GUI, sahnada obyektlar ko'rinadi

S2: import FreeCAD (DLL/ABI), S3: 7 GES obyekt -> mesh (vaqt, uchburchak), S6: 10x takror (xotira).
"""
from __future__ import annotations

import os
import sys
import time
import traceback

FC_HOME = os.environ.get("GES_FC_HOME", r"C:\Program Files\FreeCAD 1.1")
GES_WB = os.environ.get(
    "GES_WB_DIR", r"C:\Users\uge226\Desktop\Sath-FreeCAD\src\Mod\Ges\ges_workbench"
)
RESULTS: list[tuple[str, str, str]] = []  # (qadam, OK/FAIL, izoh)


def log(step, ok, note=""):
    RESULTS.append((step, "OK" if ok else "FAIL", note))
    print(f"[{'OK' if ok else 'FAIL'}] {step}: {note}", flush=True)


def load_freecad():
    """FreeCAD.pyd ni joriy Python ga yuklaydi (Blender python 3.11 == FreeCAD 1.1 python 3.11)."""
    if os.path.isdir(os.path.join(FC_HOME, "Library", "bin")):  # conda-forge layout (pixi/micromamba)
        root = os.path.join(FC_HOME, "Library")
        site = os.path.join(FC_HOME, "Lib", "site-packages")
    else:  # rasmiy Windows installer layout
        root = FC_HOME
        site = os.path.join(FC_HOME, "bin", "Lib", "site-packages")
    fc_bin = os.path.join(root, "bin")
    fc_lib = os.path.join(root, "lib")
    for d in (fc_bin, fc_lib):
        os.add_dll_directory(d)
    # site-packages OXIRIGA: Blender numpy va Bonsai ifcopenshell ustun turadi; FreeCAD niki faqat
    # Blender da yo'q paketlar uchun (PySide6 -> Draft/importDXF, pivy...).
    for d in (fc_bin, fc_lib, os.path.join(root, "Ext"), site):
        if d not in sys.path:
            sys.path.append(d)
    # FreeCAD sys.path ni import paytida (FreeCADInit) Mod/* bilan to'ldiradi
    import FreeCAD  # noqa: F401

    return FreeCAD


def shape_to_blender(name, shape, scale=0.001, tol=0.5):
    """Part shape -> bpy mesh obyekt. FreeCAD mm, Blender m."""
    import bpy

    verts, faces = shape.tessellate(tol)
    me = bpy.data.meshes.new(name)
    me.from_pydata([(v.x * scale, v.y * scale, v.z * scale) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob, len(faces)


def rss_mb():
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        assert fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 1e6
    except Exception:  # noqa: BLE001
        return -1


def main():
    print("Python:", sys.version, flush=True)
    print("RSS boshida: %.0f MB" % rss_mb(), flush=True)

    # ---- S2: import FreeCAD
    try:
        t = time.perf_counter()
        FreeCAD = load_freecad()
        import Part

        log("S2 import FreeCAD", True, f"{'.'.join(FreeCAD.Version()[:3])} {time.perf_counter()-t:.2f}s GuiUp={FreeCAD.GuiUp}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("S2 import FreeCAD", False, repr(e))
        return

    import numpy

    log("S2 numpy", True, f"{numpy.__version__} {numpy.__file__}")

    # ---- S3a: Part.makeBox
    try:
        box = Part.makeBox(1000, 2000, 3000)
        ob, n = shape_to_blender("FC_Box", box)
        log("S3a makeBox->mesh", True, f"{n} uchburchak, dims={tuple(round(x, 3) for x in ob.dimensions)}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("S3a makeBox->mesh", False, repr(e))

    # ---- S3b: GES obyektlari
    if GES_WB not in sys.path:
        sys.path.append(GES_WB)
    try:
        import ges_objects

        doc = FreeCAD.newDocument("GES")
        rows = []
        for kind in ges_objects.COMMAND_NAMES:
            t = time.perf_counter()
            obj = ges_objects.make(kind)
            t_make = time.perf_counter() - t
            t = time.perf_counter()
            ob, n = shape_to_blender(kind, obj.Shape)
            t_mesh = time.perf_counter() - t
            psets = [k for k in (getattr(obj, "IfcProperties", {}) or {})][:2]
            rows.append((kind, n, t_make, t_mesh, getattr(obj, "IfcType", "?"), len(obj.IfcProperties) if hasattr(obj, "IfcProperties") else 0))
        for r in rows:
            print(f"    {r[0]:<16} {r[1]:>7} tri  make {r[2]*1000:6.0f} ms  mesh {r[3]*1000:6.0f} ms  {r[4]}  props={r[5]}")
        log("S3b GES obyektlari", True, f"{len(rows)} obyekt")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("S3b GES obyektlari", False, repr(e))

    # ---- S3c: boshqa dvigatel modullar
    for mod in ("Import", "Mesh", "MeshPart", "Sketcher", "Draft", "importDXF", "Spreadsheet", "TechDraw"):
        try:
            t = time.perf_counter()
            __import__(mod)
            log(f"S3c import {mod}", True, f"{time.perf_counter()-t:.2f}s")
        except Exception as e:  # noqa: BLE001
            log(f"S3c import {mod}", False, repr(e).splitlines()[0][:200])

    # ---- S6: stress
    try:
        m0 = rss_mb()
        t = time.perf_counter()
        for i in range(10):
            d = FreeCAD.newDocument(f"stress{i}")
            FreeCAD.setActiveDocument(d.Name)
            for kind in ges_objects.COMMAND_NAMES:
                o = ges_objects.make(kind)
                o.Shape.tessellate(0.5)
            FreeCAD.closeDocument(d.Name)
        log("S6 stress 10x7", True, f"{time.perf_counter()-t:.1f}s, RSS {m0:.0f} -> {rss_mb():.0f} MB")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("S6 stress", False, repr(e))

    print("\n==== NATIJA")
    for s, ok, note in RESULTS:
        print(f"{ok:4} {s}: {note}")


if __name__ == "__main__":
    main()
