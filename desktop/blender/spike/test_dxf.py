"""SPIKE S4: DWG -> DXF (libredwg) -> FreeCAD Import.readDXF (C++) -> Blender mesh/curve.
Qo'shimcha: FreeCAD site-packages ni sys.path OXIRIGA qo'shib Draft/importDXF (PySide6 kerak) sinash.

  blender -b --python test_dxf.py
"""
from __future__ import annotations

import os
import sys
import time
import traceback

SPIKE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SPIKE)
import fc_bridge  # noqa: E402  (main() ni chaqirmaydi — pastda import guard bor)

FC_HOME = fc_bridge.FC_HOME
DWG = os.environ.get("GES_TEST_DWG", r"C:\Users\uge226\Desktop\BIM\desktop\tests\Namuna.dwg")
OUT_DXF = os.path.join(os.environ.get("TEMP", "."), "ges_spike.dxf")


def main():
    FreeCAD = fc_bridge.load_freecad()
    sys.path.append(fc_bridge.GES_WB)
    import bpy
    import Part

    # ---- DWG -> DXF
    try:
        import converters

        exe = converters.find_dwg2dxf()
        assert exe, "dwg2dxf topilmadi"
        import subprocess

        t = time.perf_counter()
        r = subprocess.run([exe, "-y", "-o", OUT_DXF, DWG], capture_output=True, text=True, timeout=120)
        assert os.path.exists(OUT_DXF), r.stderr[-300:]
        fc_bridge.log("S4a dwg2dxf", True, f"{os.path.getsize(OUT_DXF)//1024} KB, {time.perf_counter()-t:.1f}s")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S4a dwg2dxf", False, repr(e))
        return

    # ---- Import.readDXF (C++ importer, PySide kerak emas)
    try:
        import Import

        doc = FreeCAD.newDocument("DXF")
        FreeCAD.setActiveDocument(doc.Name)
        t = time.perf_counter()
        Import.readDXF(OUT_DXF, doc.Name)
        doc.recompute()
        objs = [o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        n_edges = n_faces = 0
        t2 = time.perf_counter()
        for o in objs:
            sh = o.Shape
            n_faces += len(sh.Faces)
            n_edges += len(sh.Edges)
            if sh.Faces:
                fc_bridge.shape_to_blender("DXF_" + o.Name, sh)
            else:
                # 2D chiziqlar -> Blender curve (poly)
                cu = bpy.data.curves.new("DXF_" + o.Name, "CURVE")
                cu.dimensions = "3D"
                for e in sh.Edges:
                    pts = e.discretize(Deflection=0.5)
                    sp = cu.splines.new("POLY")
                    sp.points.add(len(pts) - 1)
                    for i, p in enumerate(pts):
                        sp.points[i].co = (p.x * 0.001, p.y * 0.001, p.z * 0.001, 1)
                ob = bpy.data.objects.new("DXF_" + o.Name, cu)
                bpy.context.scene.collection.objects.link(ob)
        fc_bridge.log(
            "S4b Import.readDXF->Blender",
            True,
            f"{len(doc.Objects)} obyekt, {n_edges} edge, {n_faces} face; readDXF {t2-t:.2f}s, ->Blender {time.perf_counter()-t2:.2f}s",
        )
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S4b Import.readDXF", False, repr(e))

    # ---- Draft / importDXF: FreeCAD site-packages ni OXIRIGA qo'shish (Blender numpy ustun)
    try:
        t = time.perf_counter()
        import PySide6  # noqa: F401
        from PySide6 import QtCore

        fc_bridge.log("S4c PySide6 Blender ichida", True, f"{QtCore.__version__} {time.perf_counter()-t:.2f}s")
        import numpy

        assert "blender" in numpy.__file__.lower(), numpy.__file__
        import Draft  # noqa: F401
        import importDXF  # noqa: F401

        fc_bridge.log("S4c import Draft/importDXF", True, f"{time.perf_counter()-t:.2f}s")
        d2 = FreeCAD.newDocument("DXF2")
        FreeCAD.setActiveDocument(d2.Name)
        t = time.perf_counter()
        importDXF.insert(OUT_DXF, d2.Name)
        d2.recompute()
        fc_bridge.log("S4d importDXF.insert (Draft, python)", True, f"{len(d2.Objects)} obyekt, {time.perf_counter()-t:.2f}s")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S4c/d Draft yo'li", False, repr(e).splitlines()[0][:300])

    print("\n==== NATIJA S4")
    for s, ok, note in fc_bridge.RESULTS:
        print(f"{ok:4} {s}: {note}")


main()
