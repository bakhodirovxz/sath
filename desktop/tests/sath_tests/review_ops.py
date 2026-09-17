"""Viewpoint capture/apply headless da ishlaydi; diff bo'yash guid bo'yicha rang beradi."""

from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def run(ctx):
    from sath import flows, ifc, viewpoint

    ifc.load(SAMPLE)
    g = next(g for g, o in ifc.guid_map().items() if ifc.entity(o).is_a("IfcWall"))
    vp = viewpoint.capture(bpy.context)
    assert vp["camera"]["space"] == "ifc"
    viewpoint.apply(
        bpy.context,
        {"camera": {"space": "ifc", "position": [1, 2, 3], "target": [1, 2, 0]}, "selected_guids": [g]},
    )
    assert ifc.object_for_guid(g).select_get()
    colors, _ = flows.diff_colors({"added": [{"guid": g}], "summary": {"added": 1}})
    assert ifc.DIFF_STATE.paint(colors) == 1
    ifc.DIFF_STATE.restore()
    for op in (
        "refresh_issues", "show_issue", "goto_view", "comment_issue", "new_issue", "refresh_crs",
        "show_cr", "decide", "merge_cr", "reject_cr", "diff", "clear_diff",
    ):  # fmt: skip
        assert hasattr(bpy.ops.sath, op), op
    assert hasattr(bpy.types, "SATH_PT_review")
