"""7 GES obyekt yaratiladi: mesh, IFC klass, Pset_GES_*; parametr o'zgarsa mesh va pset yangilanadi."""

import bpy


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import fc_engine, ges_objects, ifc

    kinds = [k for k, _ in fc_engine.ges_kinds()]
    made = {}
    for k in kinds:
        ob = ges_objects.add(bpy.context, k)
        assert ob.ges.kind == k and len(ob.data.polygons) > 0, k
        e = ifc.entity(ob)
        assert e is not None and e.is_a().startswith("Ifc"), k
        made[k] = ob
    dam = made["GES_Dam"]
    ps = ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]
    assert ps["Balandlik_m"] == 20.0
    h = next(p for p in dam.ges.params if p.name == "Height")
    assert h.ptype == "length" and h.value_float == 20.0
    h.value_float = 35.0  # update callback → rebuild
    bpy.context.view_layer.update()
    assert abs(dam.dimensions.z - 35.0) < 1e-3, dam.dimensions.z
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    t = next(p for p in dam.ges.params if p.name == "DamType")
    assert t.ptype == "enum" and "Arkali" in t.items.split(";")
    t.value_enum = "Arkali"
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Turi"] == "Arkali"
    assert bpy.ops.sath.add_object(kind="GES_Turbine") == {"FINISHED"}
    assert sum(1 for o in bpy.data.objects if o.ges.kind == "GES_Turbine") == 2
