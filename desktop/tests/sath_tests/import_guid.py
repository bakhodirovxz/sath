"""CAD-07: Blender da sath_guid — FBX Custom Properties orqali eksport → Sath import (assimp) → GUID saqlanadi."""

import tempfile
from pathlib import Path

import bpy

GUID = "2O2Fr$t4X7Zf8NOew3FLOH"


def run(ctx):
    from sath import cad_read, ops_import
    from sath.shared import cad_common

    tmp = Path(tempfile.mkdtemp(prefix="sath-guid-"))
    me = bpy.data.meshes.new("Devor")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 1)], [], [(0, 1, 2), (0, 2, 3)])
    ob = bpy.data.objects.new("Devor", me)
    bpy.context.scene.collection.objects.link(ob)
    ob["sath_guid"] = GUID
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    fbx = tmp / "devor.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, use_custom_props=True)
    assert cad_common.fbx_info(fbx)["models"]["Devor"]["sath_guid"] == GUID  # binar FBX parser
    assert cad_read.file_guids(fbx) == {"Devor": GUID}
    n = ops_import.import_mesh(bpy.context, fbx)
    got = [o for o in bpy.data.objects if o.name.startswith("FBX_Devor")]
    assert n == 1 and got and got[0]["sath_guid"] == GUID, [o.name for o in bpy.data.objects]
    # Sath server eksporti: nom "Nom [GUID]" (OBJ)
    obj = tmp / "eksport.obj"
    obj.write_text(f"o Quvur [{GUID[:-1]}Z]\nv 0 0 0\nv 1 0 0\nv 1 1 0\nf 1 2 3\n")
    ops_import.import_mesh(bpy.context, obj)
    q = [o for o in bpy.data.objects if o.name.startswith("OBJ_Quvur")]
    assert q and q[0]["sath_guid"] == GUID[:-1] + "Z" and "[" not in q[0].name, [o.name for o in bpy.data.objects]
