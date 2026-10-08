"""DXF → Blender FreeCAD siz (ezdxf importeri): 3D yuzalar mesh, chiziqlar egri chiziq, qatlam collection."""

import tempfile
from pathlib import Path

import bpy


def run(ctx):
    from sath import ops_import
    from sath.shared import dxf_prepare

    assert dxf_prepare.ensure_ezdxf(), "ezdxf wheel yuklanmadi"
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # m
    msp = doc.modelspace()
    msp.add_3dface([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)], dxfattribs={"layer": "TOGON"})
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5)], dxfattribs={"layer": "OQ"})
    dxf = Path(tempfile.mkdtemp(prefix="sath-ezdxf-")) / "plan.dxf"
    doc.saveas(dxf)
    warnings: list = []
    n = ops_import.import_dxf(bpy.context, dxf, report=warnings)
    assert n == 2 and not warnings, (n, warnings)
    me = bpy.data.objects["DXF_TOGON"]
    assert me.type == "MESH" and len(me.data.polygons) == 2 and abs(me.dimensions.z - 3.0) < 1e-6
    cu = bpy.data.objects["DXF_OQ_chiziq"]
    xs = [p.co.x for sp in cu.data.splines for p in sp.points]
    assert cu.type == "CURVE" and abs(max(xs) - min(xs) - 10.0) < 1e-6, xs
    assert "DXF plan / TOGON" in bpy.data.collections
    # DWG ham FreeCAD siz (dwg2dxf bo'lsa)
    from sath import converters

    if converters.find_dwg2dxf():
        dwg = Path(__file__).resolve().parents[1] / "Namuna.dwg"
        assert ops_import.import_dxf(bpy.context, dwg) >= 1
