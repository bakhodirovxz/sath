"""11 GES obyekt FreeCAD siz yaratiladi: mesh, IFC klass, Pset_GES_*; parametr o'zgarsa mesh va pset yangilanadi."""

import bpy


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import ges_objects, ifc

    kinds = [k for k, _, _ in ges_objects.KIND_ITEMS]
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
    h.value_float = 35.0  # update callback → faqat mesh + ifc_dirty (K4)
    bpy.context.view_layer.update()
    assert abs(dam.dimensions.z - 35.0) < 1e-3, dam.dimensions.z
    assert dam.ges.ifc_dirty and ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 20.0
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not dam.ges.ifc_dirty
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    t = next(p for p in dam.ges.params if p.name == "DamType")
    assert t.ptype == "enum" and "Arkali" in t.items.split(";")
    t.value_enum = "Arkali"
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"}
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Turi"] == "Arkali"
    # yaroqsiz parametr: mesh qurilmaydi (xato holat qatorida), sync_ifc IFC ga hech narsa yozmaydi (xato xabari)
    h.value_float = 0.0
    assert "GES qayta qurish" in bpy.context.scene.ges.status and dam.ges.ifc_dirty, bpy.context.scene.ges.status
    try:
        bpy.ops.sath.sync_ifc()
    except RuntimeError as e:  # op.report ERROR → RuntimeError (bpy.ops)
        assert "0 dan katta" in str(e), e
    else:
        raise AssertionError("sync_ifc yaroqsiz parametrni xabar qilmadi")
    assert dam.ges.ifc_dirty
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    h.value_float = 35.0
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not dam.ges.ifc_dirty
    # rebuild_object: tanlangan obyekt mesh + IFC, bitta operator
    for o in bpy.context.view_layer.objects:
        o.select_set(o is dam)
    assert bpy.ops.sath.rebuild_object() == {"FINISHED"}
    assert bpy.ops.sath.add_object(kind="GES_Turbine") == {"FINISHED"}
    assert sum(1 for o in bpy.data.objects if o.ges.kind == "GES_Turbine") == 2
    # yaroqsiz parametr: ValueError va sahnada yetim obyekt/mesh qolmaydi
    n_obj, n_me = len(bpy.data.objects), len(bpy.data.meshes)
    try:
        ges_objects.add(bpy.context, "GES_Dam", Height=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Height=0 ValueError bermadi")
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (n_obj, n_me), "yetim obyekt/mesh qoldi"
