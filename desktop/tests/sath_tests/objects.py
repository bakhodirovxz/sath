"""11 GES obyekt FreeCAD siz yaratiladi: mesh, IFC klass, Pset_GES_*; parametr o'zgarsa mesh va pset yangilanadi.
Geometrik bo'lmagan parametr — faqat pset (representation o'zgarmaydi); Bonsai representation ni yozmasa obyekt
«sinxronlanmagan» bo'lib qoladi; IFC loyiha yo'q — sath.sync_ifc o'chiq."""

import bpy


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import ges_objects, ifc

    assert ifc.file() is None and not bpy.ops.sath.sync_ifc.poll(), "loyiha yo'q — sync_ifc o'chiq bo'lishi kerak (M6)"
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
    _non_geometric_and_refused(made)


def _reps(o):
    from sath import ifc

    return [r.id() for r in ifc.entity(o).Representation.Representations]


def _non_geometric_and_refused(made):
    import ifcopenshell.guid
    import ifcopenshell.util.element as ue
    from sath import ifc

    # I1: geometrik bo'lmagan parametr — mesh va representation tegilmaydi, faqat pset
    tb = made["GES_Turbine"]
    reps, nv = _reps(tb), len(tb.data.vertices)
    next(p for p in tb.ges.params if p.name == "Efficiency").value_float = 0.9
    assert tb.ges.ifc_dirty and not tb.ges.geom_dirty
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and _reps(tb) == reps and len(tb.data.vertices) == nv
    assert ue.get_psets(ifc.entity(tb))["Pset_GES_Turbine"]["FIK"] == 0.9  # M3: float32 shovqini yo'q
    # M2: chegaradan tashqari (FIK > 1) — IFC ga yozilmaydi
    next(p for p in tb.ges.params if p.name == "Efficiency").value_float = 1.5
    try:
        bpy.ops.sath.sync_ifc()
    except RuntimeError as e:
        assert "FIK" in str(e), e
    else:
        raise AssertionError("FIK > 1 xato bermadi")
    assert tb.ges.ifc_dirty and ue.get_psets(ifc.entity(tb))["Pset_GES_Turbine"]["FIK"] == 0.9
    next(p for p in tb.ges.params if p.name == "Efficiency").value_float = 0.9
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"}

    # C1: Bonsai representation ni yozmaydigan element (material qatlam to'plami) — ifc_dirty qoladi, xatoda obyekt nomi
    dam = made["GES_Dam"]
    f = ifc.file()
    mset = f.createIfcMaterialLayerSet(MaterialLayers=[f.createIfcMaterialLayer(f.createIfcMaterial("Beton"), 1.0)])
    rel = f.createIfcRelAssociatesMaterial(ifcopenshell.guid.new(), RelatedObjects=[ifc.entity(dam)], RelatingMaterial=mset)
    reps = _reps(dam)
    next(p for p in dam.ges.params if p.name == "Height").value_float = 24.0
    try:
        bpy.ops.sath.sync_ifc()
    except RuntimeError as e:
        assert dam.name in str(e) and "IfcMaterialLayerSet" in str(e), e
    else:
        raise AssertionError("material qatlam to'plamli element jim o'tkazildi")
    assert dam.ges.ifc_dirty and dam.ges.geom_dirty and _reps(dam) == reps
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    f.remove(rel)
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not dam.ges.ifc_dirty and _reps(dam) != reps
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 24.0
