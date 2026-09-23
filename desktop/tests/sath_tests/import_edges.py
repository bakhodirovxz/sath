"""Degenerat (0/1 nuqtali) qirralar egri chiziq yaratishda yiqitmaydi; bo'sh bo'lsa obyekt yaratilmaydi."""

import bpy


def run(ctx):
    from sath import ops_import

    coll = bpy.context.scene.collection
    ob = ops_import._polylines_to_curve("T_egri", [[], [(0, 0, 0)], [(0, 0, 0), (1, 0, 0)]], coll)
    assert ob is not None and len(ob.data.splines) == 1 and len(ob.data.splines[0].points) == 2
    assert ops_import._polylines_to_curve("T_bosh", [[], [(1, 1, 1)]], coll) is None
    assert "T_bosh" not in bpy.data.objects
