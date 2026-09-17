"""Bonsai: loyiha ochish/yaratish, mesh → IFC element + Pset_GES_*, guid xaritasi, rang holati, saqlash."""

import os
import tempfile
from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def _cube(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)],
    )
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def run(ctx):
    import ifcopenshell
    import ifcopenshell.util.element as ue
    from sath import ifc

    assert ifc.file() is None
    ifc.load(SAMPLE)
    f = ifc.file()
    assert f is not None and len(f.by_type("IfcProduct")) == 20
    gm = ifc.guid_map()
    assert len(gm) >= 16 and all(len(g) == 22 for g in gm)
    dam = next(o for g, o in gm.items() if ifc.entity(o).is_a("IfcWall"))
    assert ifc.guid(dam) == ifc.entity(dam).GlobalId
    assert ifc.object_for_guid(ifc.guid(dam)) is dam

    ob = _cube("Yangi_togon")
    ifc.assign_class(ob, "IfcWall", {"Pset_GES_Dam": {"Balandlik_m": 12.5, "Turi": "Tuproq"}})
    e = ifc.entity(ob)
    assert e.is_a("IfcWall")
    assert ue.get_psets(e)["Pset_GES_Dam"]["Balandlik_m"] == 12.5
    ifc.write_psets(e, {"Pset_GES_Dam": {"Balandlik_m": 13.0}})  # mavjud pset yangilanadi
    assert ue.get_psets(e)["Pset_GES_Dam"]["Balandlik_m"] == 13.0
    assert ue.get_psets(e)["Pset_GES_Dam"]["Turi"] == "Tuproq"
    ob.data.vertices[4].co.z = 3.0
    ifc.update_representation(ob)

    st = ifc.ColorState()
    n = st.paint({ifc.guid(dam): (1, 0, 0, 1), "yoq_guid": (0, 1, 0, 1)})
    assert n == 1 and tuple(dam.color)[:3] == (1.0, 0.0, 0.0)
    st.restore()
    assert tuple(dam.color) == (1.0, 1.0, 1.0, 1.0)
    assert ifc.select_guids([ifc.guid(dam)]) == 1 and dam.select_get()

    out = Path(tempfile.gettempdir()) / "sath_test.ifc"
    ifc.save(out)
    f2 = ifcopenshell.open(str(out))
    walls = {w.Name: w for w in f2.by_type("IfcWall")}
    assert "Yangi_togon" in walls
    assert ue.get_psets(walls["Yangi_togon"])["Pset_GES_Dam"]["Turi"] == "Tuproq"
    assert e.GlobalId in {p.GlobalId for p in f2.by_type("IfcProduct")}
    os.remove(out)
