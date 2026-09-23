"""CAD-01: import qilingan mesh lar Bonsai IFC elementiga aylanadi (nom bo'yicha sinf), commit oldidan IFC ga
kirmagan obyektlar sanaladi; CAD-07: sath_guid li qayta import mavjud elementni yangilaydi (ikki barobar emas)."""

import tempfile
from pathlib import Path

import bpy

GUID = "2O2Fr$t4X7Zf8NOew3FLOH"


def _one(suffix: str):
    """Bonsai obyektni "IfcWall/Nom" deb qayta nomlaydi."""
    found = [o for o in bpy.data.objects if o.name == suffix or o.name.endswith("/" + suffix)]
    assert len(found) == 1, [o.name for o in bpy.data.objects]
    return found[0]


def run(ctx):
    from sath import ifc, ops_import, ops_server

    ifc.ensure_project()
    f = ifc.file()
    tmp = Path(tempfile.mkdtemp(prefix="sath-ifc-"))
    obj = tmp / "gs.obj"
    obj.write_text(
        f"o Togon [{GUID}]\nv 0 0 0\nv 4 0 0\nv 4 0 3\nv 0 0 3\nf 1 2 3 4\n"
        "o Kub\nv 10 0 0\nv 11 0 0\nv 11 1 0\nf 5 6 7\n"
    )
    warnings: list = []
    n = ops_import.import_mesh(bpy.context, obj, unit="m", axis="Z", report=warnings, assign_ifc=True)
    assert n == 2, (n, warnings)
    togon = _one("OBJ_Togon")
    e = ifc.entity(togon)
    assert e is not None and e.is_a("IfcWall") and e.GlobalId == GUID, e
    assert ifc.entity(_one("OBJ_Kub")).is_a("IfcBuildingElementProxy")
    count = len(f.by_type("IfcElement"))
    assert ops_server.unassigned(bpy.context) == [], ops_server.unassigned(bpy.context)

    # qayta import (masalan Sath eksportidan): shu GUID — yangi element emas, mavjudining geometriyasi
    obj2 = tmp / "gs2.obj"
    obj2.write_text(f"o Togon [{GUID}]\nv 0 0 0\nv 8 0 0\nv 8 0 3\nv 0 0 3\nf 1 2 3 4\n")
    ops_import.import_mesh(bpy.context, obj2, unit="m", axis="Z", assign_ifc=True)
    assert len(ifc.file().by_type("IfcElement")) == count
    assert abs(_one("OBJ_Togon").dimensions.x - 8.0) < 1e-6  # bitta obyekt, geometriya yangilandi

    # IFC ga kirmagan obyekt (chiziq, qo'lda qo'shilgan mesh) — commit oldidan sanaladi
    me = bpy.data.meshes.new("Qolda")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Qolda", me))
    assert ops_server.unassigned(bpy.context) == ["Qolda"]
    assert ops_import.assign_imported([bpy.data.objects["Qolda"]]) == 1
    assert ifc.entity(_one("Qolda")) is not None
    assert ops_server.unassigned(bpy.context) == []
