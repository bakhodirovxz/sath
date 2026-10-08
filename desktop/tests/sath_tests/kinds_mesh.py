"""ges_kinds → Blender mesh (numpy foreach_set), FreeCAD siz: 11 tur, mesh yaroqli (validate), manifold, bmesh hajmi
analitik hajmga mos; generator sinxron tezligi; egri quvur pastga tushadi (avvalgi `engine` testi o'rnida)."""

import time

import bmesh
import bpy


def run(ctx):
    from sath import ges_objects
    from sath.shared import ges_kinds

    assert [k for k, _, _ in ges_objects.KIND_ITEMS] == list(ges_kinds.ORDER)
    t0 = time.perf_counter()
    for kind in ges_kinds.ORDER:
        v, f = ges_kinds.build(kind, {})
        me = bpy.data.meshes.new(kind)
        ges_objects.set_mesh(me, v, f)
        assert (len(me.vertices), len(me.polygons)) == (len(v), len(f)), kind
        assert not me.validate(), f"{kind}: mesh yaroqsiz edi (validate tuzatdi)"
        bm = bmesh.new()
        bm.from_mesh(me)
        vol = bm.calc_volume(signed=True)
        bad = [e for e in bm.edges if not e.is_manifold]
        bm.free()
        q = ges_kinds.quantities(kind)["volume_m3"]
        assert not bad and abs(vol - q) / q < 5e-3, (kind, len(bad), vol, q)
    ms = (time.perf_counter() - t0) * 1000
    assert ms < 3000, f"11 tur {ms:.0f} ms"
    assert ges_kinds.psets("GES_Generator", {"Poles": 48})["Pset_GES_Generator"]["Aylanish_rpm"] == 125.0
    v, _ = ges_kinds.build("GES_Penstock", {"Length": 60.0, "Inclination": 40.0})
    assert v[:, 2].min() < -30, v[:, 2].min()
    print(f"KINDS_MESH: 11 tur {ms:.0f} ms", flush=True)
