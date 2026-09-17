"""SPIKE S5: Bonsai (IFC) + FreeCAD bir Blender jarayonida.

  blender -b --python test_bonsai.py
Tartib real hayotdagidek: avval Bonsai addoni yoqiladi, keyin FreeCAD yuklanadi.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

SPIKE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SPIKE)
import fc_bridge  # noqa: E402

IFC = os.environ.get("GES_TEST_IFC", r"C:\Users\uge226\Desktop\BIM\docs\samples\namuna_ges_v1.ifc")


def main():
    import bpy

    # ---- Bonsai yoqish
    try:
        t = time.perf_counter()
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
        import ifcopenshell

        fc_bridge.log("S5a Bonsai enable", True, f"{time.perf_counter()-t:.1f}s ifcopenshell {ifcopenshell.version} @ {ifcopenshell.__file__}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S5a Bonsai enable", False, repr(e)[:300])
        return
    ios_before = ifcopenshell.__file__

    # ---- FreeCAD yuklash (Bonsai dan keyin)
    try:
        FreeCAD = fc_bridge.load_freecad()
        import Part  # noqa: F401

        sys.path.append(os.path.join(fc_bridge.FC_HOME, "bin", "Lib", "site-packages"))
        import ifcopenshell as ios2

        same = ios2.__file__ == ios_before
        fc_bridge.log("S5b FreeCAD Bonsai dan keyin", same, f"FreeCAD {'.'.join(FreeCAD.Version()[:3])}; ifcopenshell o'zgarmadi={same}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S5b FreeCAD Bonsai dan keyin", False, repr(e)[:300])
        return

    # ---- IFC ni Bonsai bilan ochish
    try:
        t = time.perf_counter()
        bpy.ops.bim.load_project(filepath=IFC)
        import bonsai.tool as tool

        f = tool.Ifc.get()
        n_prod = len(f.by_type("IfcProduct"))
        n_obj = len([o for o in bpy.data.objects if o.type == "MESH"])
        fc_bridge.log("S5c Bonsai load_project", True, f"{n_prod} IfcProduct, {n_obj} mesh obyekt, {time.perf_counter()-t:.1f}s, schema {f.schema}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S5c Bonsai load_project", False, repr(e)[:300])
        return

    # ---- Pset_GES_* o'qish
    try:
        import ifcopenshell.util.element as ue

        found = {}
        for p in f.by_type("IfcProduct"):
            for name, props in ue.get_psets(p).items():
                if name.startswith("Pset_GES_"):
                    found.setdefault(name, 0)
                    found[name] += 1
                    if found[name] == 1:
                        print(f"    {name}: {p.is_a()} {p.Name!r} -> {dict(list(props.items())[:4])}")
        fc_bridge.log("S5d Pset_GES_*", bool(found), str(found))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S5d Pset_GES_*", False, repr(e)[:300])

    # ---- FreeCAD geometriya Bonsai sahnasiga qo'shish (yonma-yon yashash)
    try:
        sys.path.append(fc_bridge.GES_WB)
        import ges_objects

        FreeCAD.newDocument("G")
        obj = ges_objects.make("GES_Dam")
        ob, n = fc_bridge.shape_to_blender("FC_Dam_side_by_side", obj.Shape)
        fc_bridge.log("S5e FreeCAD shape Bonsai sahnasida", True, f"{n} tri, jami obyekt {len(bpy.data.objects)}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fc_bridge.log("S5e FreeCAD shape Bonsai sahnasida", False, repr(e)[:300])

    # ---- FreeCAD BIM (nativeifc) ham shu ifcopenshell bilan ishlaydimi
    try:
        import nativeifc.ifc_tools as it  # FreeCAD Mod/BIM

        f2 = it.ifcopenshell.open(IFC)
        fc_bridge.log("S5f FreeCAD nativeifc + Bonsai ifcopenshell", True, f"{it.ifcopenshell.__file__ == ios_before}, {len(f2.by_type('IfcProduct'))} product")
    except Exception as e:  # noqa: BLE001
        fc_bridge.log("S5f FreeCAD nativeifc", False, repr(e)[:300])

    print("\n==== NATIJA S5")
    for s, ok, note in fc_bridge.RESULTS:
        print(f"{ok:4} {s}: {note}")


main()
