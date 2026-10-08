"""K4: GES obyekt qo'shish, parametr sinxroni va «Namuna GES» — har biri bitta IFC tranzaksiyasi (Blender undo
qadami); orqaga qaytarilgach yetim entity qolmaydi (`ifc.orphans() == []`). Headless da Blender undo steki yo'q —
`ifc_ops.undo_to` (GUI da Ctrl+Z dan keyin Bonsai undo_post aynan IfcStore.undo ni chaqiradi) + yaratilgan Blender
obyektlarini o'chirish (Blender undo emulyatsiyasi). Qo'lda o'chirilgan obyektning IFC elementi — purge_orphans.
add() IFC element yaratilgandan keyin yiqilsa — element ham qaytariladi (yetim qolmaydi)."""

import bpy


def _counts(f) -> tuple:
    return tuple(len(f.by_type(t)) for t in ("IfcElement", "IfcPropertySet", "IfcShapeRepresentation"))


def _undo(key: str, created: set) -> None:
    from sath.core import ifc_ops

    ifc_ops.undo_to(key)
    for n in created:
        o = bpy.data.objects.get(n)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)
    ifc_ops.rebuild_maps()


def _add_fails_after_assign(f, base) -> None:
    """Task 6 minor: assign_class dan keyin xato (psetlar yozilmadi) → operator xato xabari (CANCELLED), Blender
    obyekti/mesh va IFC element qolmaydi."""
    from sath import ifc

    n_obj, n_me = len(bpy.data.objects), len(bpy.data.meshes)
    real = ifc.write_psets

    def boom(*a, **kw):
        raise RuntimeError("pset yozilmadi (sinov)")

    ifc.write_psets = boom
    try:
        bpy.ops.sath.add_object(kind="GES_Intake")
    except RuntimeError as e:  # bpy.ops: operator ERROR xabari → RuntimeError (traceback emas, aniq matn)
        assert "pset yozilmadi" in str(e), e
    else:
        raise AssertionError("add_object xatoni xabar qilmadi")
    finally:
        ifc.write_psets = real
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (n_obj, n_me), "yetim obyekt/mesh qoldi"
    assert ifc.orphans() == [] and _counts(f) == base, (ifc.orphans(), _counts(f), base)


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import ges_objects, ifc
    from sath.core import ifc_ops

    ifc.ensure_project()
    f = ifc.file()
    base = _counts(f)
    assert ifc.orphans() == [], ifc.orphans()

    # 1) qo'shish → orqaga: element, psetlar, representation qolmaydi
    key0, names0 = ifc_ops.last_key(), set(bpy.data.objects.keys())
    assert key0, "ensure_project tranzaksiyasi kaliti bo'sh"
    assert bpy.ops.sath.add_object(kind="GES_Spillway") == {"FINISHED"}
    sp = bpy.context.view_layer.objects.active
    ps = ue.get_psets(ifc.entity(sp))
    assert "Pset_GES_Spillway" in ps and ps["Pset_SathParametric"]["Kind"] == "GES_Spillway", ps.keys()
    assert ifc_ops.last_key() != key0, "add_object IFC tranzaksiyasi yozilmadi"
    _undo(key0, set(bpy.data.objects.keys()) - names0)
    assert ifc.orphans() == [], ifc.orphans()
    assert _counts(f) == base, (_counts(f), base)

    # 1b) add() IFC element yaratilgandan keyin yiqildi → element ham qaytariladi
    _add_fails_after_assign(f, base)

    # 2) Blender obyekti qo'lda o'chirildi, IFC qoldi → orphans topadi, purge tozalaydi
    assert bpy.ops.sath.add_object(kind="GES_Dam") == {"FINISHED"}
    bpy.data.objects.remove(bpy.context.view_layer.objects.active, do_unlink=True)
    ifc_ops.rebuild_maps()
    orph = ifc.orphans()
    assert any(o["class"] == "IfcWall" for o in orph), orph
    assert bpy.ops.sath.purge_orphans() == {"FINISHED"}
    assert ifc.orphans() == [] and _counts(f) == base, (ifc.orphans(), _counts(f), base)
    # commit dialogi yetimlarni o'zi o'chirmaydi (Bonsai yuklamagan GES elementi jim o'chmasin) — foydalanuvchi tanlaydi
    assert bpy.ops.sath.commit.get_rna_type().properties["purge_orphans"].default is False

    # 3) parametr → faqat mesh + dirty; sync_ifc → IFC; orqaga → eski pset, yetim representation yo'q
    assert bpy.ops.sath.add_object(kind="GES_Tailrace") == {"FINISHED"}
    tr = bpy.context.view_layer.objects.active
    after3 = _counts(f)
    next(p for p in tr.ges.params if p.name == "Depth").value_float = 9.0
    bpy.context.view_layer.update()
    assert tr.ges.ifc_dirty and abs(tr.dimensions.z - 9.8) < 1e-3, tr.dimensions.z  # Depth + WallThickness
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 6.0  # IFC hali yozilmagan
    assert ges_objects.dirty_objects() == [tr]
    key1 = ifc_ops.last_key()
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not tr.ges.ifc_dirty
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 9.0
    _undo(key1, set())
    assert ue.get_psets(ifc.entity(tr))["Pset_GES_Tailrace"]["Chuqurlik_m"] == 6.0
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)

    # 3b) sath.assign_ifc (commit dagi «IFC ga kirmaganlarni qo'shish» qadami) — bitta tranzaksiya, orqaga yetimsiz
    keyA, namesA = ifc_ops.last_key(), set(bpy.data.objects.keys())
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.view_layer.objects.active
    cube.name = "Blok_qolda"
    assert bpy.ops.sath.assign_ifc(names=f"{cube.name};yo'q_obyekt") == {"FINISHED"}
    assert ifc.entity(cube) is not None and ifc_ops.last_key() != keyA
    assert _counts(f)[0] == after3[0] + 1, (_counts(f), after3)
    _undo(keyA, set(bpy.data.objects.keys()) - namesA)
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)

    # 4) Namuna GES (16 element, ichki bim.* operatorlari) → bitta qadam bilan orqaga
    key2, names2 = ifc_ops.last_key(), set(bpy.data.objects.keys())
    assert bpy.ops.sath.build_demo_plant() == {"FINISHED"}
    assert len(ges_objects.by_kind_all()) == 17
    _undo(key2, set(bpy.data.objects.keys()) - names2)
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)

    # 5) import operatorlari ham IfcOperator: xato — aniq xabar (SathOpError), traceback/yarim holat yo'q
    try:
        bpy.ops.sath.import_dxf(filepath="C:/yo'q/fayl.dxf", assign_ifc=False)
    except RuntimeError as e:
        assert "Import xatosi" in str(e), e
    else:
        raise AssertionError("import_dxf xatoni xabar qilmadi")
    assert ifc.orphans() == [] and _counts(f) == after3, (ifc.orphans(), _counts(f), after3)
    print("UNDO_IFC OK", _counts(f), flush=True)
