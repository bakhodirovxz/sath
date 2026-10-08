"""update_representation (ifcopenshell 0.9 tez batch o'chirish): Ctrl+Z butun face set ni tiklaydi, 30k+ yuzda tez."""

import time

import bpy


def _faceset(e):
    for rep in e.Representation.Representations:
        for it in rep.Items:
            if it.is_a("IfcPolygonalFaceSet"):
                return it
    return None


def run(ctx):
    from _req import require_freecad

    require_freecad()
    from sath import ges_objects, ifc

    obj = ges_objects.add(bpy.context, "GES_Turbine", "UndoTurbina")
    f = ifc.file()
    e = ifc.entity(obj)
    ifc.update_representation(obj)  # Blender mesh (30k+ uchburchak) IFC ga yoziladi — keyingi o'chirish katta
    e = ifc.entity(obj)
    fs0 = _faceset(e)
    assert fs0 is not None, "polygonal face set kutilgan"
    n_pts = len(fs0.Coordinates.CoordList)
    n_faces, n_ent = len(fs0.Faces), len(f.by_type("IfcIndexedPolygonalFace"))
    assert len(obj.data.polygons) >= 30000 and n_faces >= 30000, (n_faces, len(obj.data.polygons))
    assert f.history_size and f.history is not None
    hist0 = len(f.history)

    t = time.time()
    ifc.update_representation(obj)
    dt = time.time() - t
    assert dt < 30.0, f"update_representation {dt:.1f}s (>30s)"
    assert len(f.history) == hist0 + 1, (len(f.history), hist0)
    fs1 = _faceset(ifc.entity(obj))
    assert len(fs1.Faces) == n_faces and len(f.by_type("IfcIndexedPolygonalFace")) == n_ent

    # Ctrl+Z (-b da bpy.ops.ed.undo emas, IFC fayl tranzaksiyasi o'zi: f.undo())
    f.undo()
    fs2 = _faceset(f.by_id(e.id()))
    assert fs2 is not None, "undo dan keyin face set yo'q"
    assert fs2.Faces is not None and fs2.Coordinates is not None, (fs2.Faces is None, fs2.Coordinates is None)
    assert len(fs2.Faces) == n_faces, (len(fs2.Faces), n_faces)
    assert len(fs2.Coordinates.CoordList) == n_pts, (len(fs2.Coordinates.CoordList), n_pts)
    assert all(face.CoordIndex for face in fs2.Faces[:50])
    assert len(f.by_type("IfcIndexedPolygonalFace")) == n_ent, "yetim yuzlar"
    print(f"UNDO_REP OK: {n_faces} yuz, update {dt:.1f}s")
