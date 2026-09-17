"""BCF uslubidagi ko'rinish: kamera + tanlangan IFC GUID lar. Format web bilan bir xil: space="ifc", metr,
Z yuqoriga."""

from __future__ import annotations

import math


def from_view(position, direction, distance: float, is_ortho: bool, guids: list[str]) -> dict:
    """Sof: kamera pozitsiyasi (m), yo'nalish (birlik vektor), fokus masofasi → viewpoint dict."""
    p = [float(x) for x in position]
    t = [p[i] + float(direction[i]) * float(distance) for i in range(3)]
    return {
        "camera": {
            "space": "ifc",
            "position": p,
            "target": t,
            "projection": "Orthographic" if is_ortho else "Perspective",
        },
        "selected_guids": list(guids),
        "section": [],
    }


def view_params(cam: dict) -> tuple[tuple, tuple, float]:
    """Sof: camera dict → (view_location=target, yo'nalish birlik vektor, masofa)."""
    p, t = [float(x) for x in cam["position"]], [float(x) for x in cam["target"]]
    d = [t[i] - p[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in d)) or 1.0
    return tuple(t), tuple(x / n for x in d), n


def _selected(context):
    """Tanlangan obyektlar — 3D area kontekstisiz (skript/timer) ham ishlaydi."""
    sel = getattr(context, "selected_objects", None)
    return sel if sel is not None else [o for o in context.view_layer.objects if o.select_get()]


def _region3d(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return None
    for area in screen.areas:
        if area.type == "VIEW_3D":
            return area.spaces.active.region_3d
    return None


def capture(context) -> dict:
    from . import ifc

    r3d = _region3d(context)
    guids = [g for g in (ifc.guid(o) for o in _selected(context)) if g]
    if r3d is None:  # headless
        return from_view((0, 0, 0), (0, 1, 0), 10.0, False, guids)
    from mathutils import Vector

    inv = r3d.view_matrix.inverted()
    direction = (inv.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    return from_view(
        tuple(inv.translation),
        tuple(direction),
        float(r3d.view_distance),
        r3d.view_perspective == "ORTHO",
        guids,
    )


def apply(context, vp: dict) -> None:
    from . import ifc

    cam = (vp or {}).get("camera") or {}
    r3d = _region3d(context)
    if r3d is not None and cam.get("position") and cam.get("space") in ("ifc", "freecad"):
        from mathutils import Vector

        k = 1.0 if cam.get("space") == "ifc" else 0.001
        c = {"position": [x * k for x in cam["position"]], "target": [x * k for x in cam["target"]]}
        loc, d, dist = view_params(c)
        r3d.view_location = Vector(loc)
        r3d.view_rotation = Vector((0.0, 0.0, -1.0)).rotation_difference(Vector(d))
        r3d.view_distance = dist
        r3d.view_perspective = "ORTHO" if cam.get("projection") == "Orthographic" else "PERSP"
    ifc.select_guids(list(vp.get("selected_guids") or []))
