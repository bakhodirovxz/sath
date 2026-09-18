"""FreeCAD yuklanadi, GES sxemasi va build ishlaydi, mesh metrda, hujjat bo'sh qoladi."""

import bpy


def run(ctx):
    from sath import fc_engine

    assert fc_engine.available(), "FreeCAD topilmadi (GES_FC_HOME)"
    assert fc_engine.load().Version()[0] == "1"
    kinds = dict(fc_engine.ges_kinds())
    assert set(kinds) == {
        "GES_Dam", "GES_Penstock", "GES_Turbine", "GES_Spillway",
        "GES_Powerhouse", "GES_Transformer", "GES_Intake",
        "GES_Generator", "GES_DraftTube", "GES_ControlRoom", "GES_Tailrace",
    }  # fmt: skip
    assert fc_engine.ges_build("GES_Generator", {"Poles": 48}).psets["Pset_GES_Generator"]["Aylanish_rpm"] == 125.0
    egri = fc_engine.ges_build("GES_Penstock", {"Length": 60.0, "Inclination": 40.0})
    zs = [v[2] for v in egri.verts]
    assert min(zs) < -30 and egri.ifc_class == "IfcPipeSegment", min(zs)  # egri quvur pastga tushadi
    schema = {f["name"]: f for f in fc_engine.ges_schema("GES_Dam")}
    assert schema["Height"]["type"] == "length" and abs(schema["Height"]["default"] - 20.0) < 1e-6
    assert schema["DamType"]["type"] == "enum" and "Gravitatsion" in schema["DamType"]["items"]
    b = fc_engine.ges_build("GES_Dam", {"Height": 30.0, "Length": 100.0})
    assert b.ifc_class == "IfcWall"
    assert b.psets["Pset_GES_Dam"]["Balandlik_m"] == 30.0
    assert b.psets["Pset_GES_Dam"]["Uzunlik_m"] == 100.0
    assert abs(max(v[2] for v in b.verts) - 30.0) < 1e-6
    me = bpy.data.meshes.new("t")
    fc_engine.shape_to_mesh(fc_engine.last_shape(), me)
    assert len(me.polygons) == len(b.faces)
    for kind in kinds:
        bb = fc_engine.ges_build(kind, {})
        assert bb.verts and bb.faces and bb.ifc_class.startswith("Ifc"), kind
    assert len(fc_engine.doc().Objects) == 0
