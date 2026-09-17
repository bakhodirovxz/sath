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
    m = ops_import.import_mesh(bpy.context, TESTS / "Namuna.fbx")
    assert m >= 1 and any(o.type == "MESH" and o.name.startswith("FBX") for o in bpy.data.objects)
    assert hasattr(bpy.ops.sath, "import_dxf") and hasattr(bpy.ops.sath, "import_mesh")
