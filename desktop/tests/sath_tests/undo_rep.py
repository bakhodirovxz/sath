"""update_representation (ifcopenshell 0.9.0 tez batch o'chirish): Ctrl+Z butun face set ni tiklaydi, 30k+ yuzda tez;
tirik havola qiluvchi (qatlam) qayta bog'lanadi; yozuv xato bersa upstream yozuviga qaytiladi va fayl batch da qolmaydi.
FreeCAD siz (CI da ham ishlaydi): mesh bpy bilan, IFC sinf Bonsai orqali."""

import time

import bpy


def _faceset(e):
    for rep in e.Representation.Representations:
        for it in rep.Items:
            if it.is_a("IfcPolygonalFaceSet"):
                return it
    return None


def _mesh(name: str, **kw):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.ops.mesh.primitive_uv_sphere_add(**kw)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def _check_unbatched(f) -> None:
    """Fayl batch rejimida qolmagan: remove() haqiqatan o'chiradi (batch da faqat belgilanardi)."""
    import ifcopenshell.api

    p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy")
    pid = p.id()
    f.remove(p)
    try:
        f.by_id(pid)
    except RuntimeError:
        return
    raise AssertionError("fayl batch rejimida qolib ketdi: remove() o'chirmadi")


def _big(f, ifc):
    import ifcopenshell.api

    obj = _mesh("UndoSfera", segments=128, ring_count=128)  # 16k ko'pburchak → IFC da ~32.5k uchburchak yuz
    obj = ifc.object_for_guid(ifc.assign_class(obj, "IfcBuildingElementProxy").GlobalId)  # Bonsai nomni o'zgartiradi
    ifc.update_representation(obj)  # Blender mesh (30k+ yuz) IFC ga yoziladi — keyingi o'chirish katta
    e = ifc.entity(obj)
    fs0 = _faceset(e)
    assert fs0 is not None, "polygonal face set kutilgan"
    n_pts = len(fs0.Coordinates.CoordList)
    n_faces, n_ent = len(fs0.Faces), len(f.by_type("IfcIndexedPolygonalFace"))
    assert n_faces >= 30000, n_faces

    # Tirik havola qiluvchi: qatlam face set + o'chirilmaydigan nuqtaga — remove_representation qatlamni qoldiradi
    keep = f.createIfcCartesianPoint((0.0, 0.0, 0.0))
    layer = ifcopenshell.api.run("layer.add_layer", f, name="SathUndoQatlam")
    ifcopenshell.api.run("layer.assign_layer", f, items=[fs0, keep], layer=layer)
    assert {i.id() for i in layer.AssignedItems} == {fs0.id(), keep.id()}

    seen = {}
    real = ifc._record_batch_inverses

    def spy(tr, ids):
        inv = real(tr, ids)
        seen["survivor"] = layer.id() in inv and fs0.id() in ids
        return inv

    assert f.history_size and f.history is not None
    hist0 = len(f.history)
    ifc._record_batch_inverses = spy
    try:
        t = time.time()
        ifc.update_representation(obj)
        dt = time.time() - t
    finally:
        ifc._record_batch_inverses = real
    assert dt < 30.0, f"update_representation {dt:.1f}s (>30s)"
    assert seen.get("survivor"), f"qatlam tirik havola qiluvchi sifatida yozilmadi: {seen}"
    assert len(f.history) == hist0 + 1, (len(f.history), hist0)
    fs1 = _faceset(ifc.entity(obj))
    assert len(fs1.Faces) == n_faces and len(f.by_type("IfcIndexedPolygonalFace")) == n_ent
    assert fs0.id() not in {i.id() for i in f.by_id(layer.id()).AssignedItems}

    # Ctrl+Z (-b da bpy.ops.ed.undo emas, IFC fayl tranzaksiyasi o'zi: f.undo())
    f.undo()
    fs2 = _faceset(f.by_id(e.id()))
    assert fs2 is not None, "undo dan keyin face set yo'q"
    assert fs2.Faces is not None and fs2.Coordinates is not None, (fs2.Faces is None, fs2.Coordinates is None)
    assert len(fs2.Faces) == n_faces, (len(fs2.Faces), n_faces)
    assert len(fs2.Coordinates.CoordList) == n_pts, (len(fs2.Coordinates.CoordList), n_pts)
    assert all(face.CoordIndex for face in fs2.Faces[:50])
    assert len(f.by_type("IfcIndexedPolygonalFace")) == n_ent, "yetim yuzlar"
    items = {i.id() for i in f.by_id(layer.id()).AssignedItems}
    assert items == {fs2.id(), keep.id()}, ("qatlam tiklangan face set ga qayta bog'lanmadi", items, fs2.id())
    _check_unbatched(f)
    return n_faces, dt


def _fallback(f, ifc):
    """Chiziqli yozuv xato bersa: upstream (element bo'yicha) yozuv, update tugaydi, fayl batch da qolmaydi, undo ishlaydi.
    Kichik mesh — upstream yozuvi kvadratik."""
    obj = _mesh("UndoKichik", segments=8, ring_count=6)
    obj = ifc.object_for_guid(ifc.assign_class(obj, "IfcBuildingElementProxy").GlobalId)
    ifc.update_representation(obj)
    e = ifc.entity(obj)
    fs0 = _faceset(e)
    assert fs0 is not None, "polygonal face set kutilgan"
    n_faces, n_pts = len(fs0.Faces), len(fs0.Coordinates.CoordList)
    hist0 = len(f.history)

    calls = {"n": 0}
    real = ifc._record_batch_inverses

    def boom(tr, ids):  # birinchi chaqiruvda xato (update ichida bir nechta batch bo'lishi mumkin)
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("kutilmagan element (sinov)")
        return real(tr, ids)

    ifc._record_batch_inverses = boom
    try:
        ifc.update_representation(obj)
    finally:
        ifc._record_batch_inverses = real
    assert calls["n"] >= 1, calls
    assert len(f.history) == hist0 + 1, (len(f.history), hist0)
    assert f.transaction is None or not f.transaction.is_batched
    _check_unbatched(f)
    fs1 = _faceset(ifc.entity(obj))
    assert fs1 is not None and fs1.id() != fs0.id()

    f.undo()
    fs2 = _faceset(f.by_id(e.id()))
    assert fs2 is not None and fs2.Faces is not None and fs2.Coordinates is not None
    assert len(fs2.Faces) == n_faces and len(fs2.Coordinates.CoordList) == n_pts, (len(fs2.Faces), n_faces)
    assert all(face.CoordIndex for face in fs2.Faces)


def run(ctx):
    from sath import ifc

    ifc.ensure_project()
    f = ifc.file()
    _fallback(f, ifc)
    n_faces, dt = _big(f, ifc)
    print(f"UNDO_REP OK: {n_faces} yuz, update {dt:.1f}s; fallback va qatlam (tirik havola) tiklandi")
