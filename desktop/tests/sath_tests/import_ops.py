"""DWG → DXF → FreeCAD → Blender curve/mesh (qatlam collection); FBX → assimp → mesh."""

from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parents[1]


def run(ctx):
    from sath import converters, ops_import
    from sath.shared import assimp_load, dxf_prepare

    assert converters.find_dwg2dxf(), "dwg2dxf topilmadi (~/Tools/libredwg)"
    assert dxf_prepare.ensure_ezdxf(), "ezdxf wheel yuklanmadi"
    n = ops_import.import_dxf(bpy.context, TESTS / "Namuna.dwg")
    assert n >= 1, n
    names = [c.name for c in bpy.data.collections]
    assert any(c.startswith("DXF") for c in names), names
    assert any(o.type == "CURVE" for o in bpy.data.objects)
    assert assimp_load.available(), "assimp-py wheel yuklanmadi"
    warnings: list = []
    m = ops_import.import_mesh(bpy.context, TESTS / "Namuna.fbx", report=warnings)
    fbx = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("FBX")]
    assert m >= 1 and fbx and not warnings, warnings
    # CAD-04: FBX UnitScaleFactor=100 (metr), UpAxis=Y → Blender dagi o'z FBX importeri bilan bir xil o'lcham
    d = fbx[0].dimensions
    assert abs(d.x - 0.5106) < 0.01 and abs(d.y - 0.5293) < 0.01 and abs(d.z - 0.4062) < 0.01, tuple(d)
    assert hasattr(bpy.ops.sath, "import_dxf") and hasattr(bpy.ops.sath, "import_mesh")
