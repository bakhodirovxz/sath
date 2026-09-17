"""BCF uslubidagi ko'rinish: kamera + tanlangan elementlar (IFC GUID).

Umumiy format (web bilan bir xil): camera.space = "ifc" — IFC koordinatalari, metr, Z yuqoriga.
FreeCAD ichki birligi mm, shuning uchun 1000 ga bo'linadi/ko'paytiriladi.
"""

from __future__ import annotations

import FreeCAD
import FreeCADGui

MM = 1000.0


def _ifc_guid(obj) -> str | None:
    for attr in ("GlobalId", "IfcGlobalId"):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    # NativeIFC: obyekt → ifc fayldagi entity
    try:
        try:
            from nativeifc import ifc_tools
        except ImportError:
            import ifc_tools
        el = ifc_tools.get_ifc_element(obj)
        return el.GlobalId if el is not None else None
    except (ImportError, AttributeError, RuntimeError, TypeError):
        return None


def capture() -> dict:
    view = FreeCADGui.ActiveDocument.ActiveView
    cam = view.getCameraNode()
    pos = cam.position.getValue()
    p = FreeCAD.Vector(pos[0], pos[1], pos[2])
    d = view.getViewDirection()  # kamera qaragan yo'nalish (birlik vektor)
    dist = cam.focalDistance.getValue() or 10000.0
    t = p + FreeCAD.Vector(d.x, d.y, d.z) * dist
    guids = [g for g in (_ifc_guid(o) for o in FreeCADGui.Selection.getSelection()) if g]
    return {
        "camera": {
            "space": "ifc",
            "position": [p.x / MM, p.y / MM, p.z / MM],
            "target": [t.x / MM, t.y / MM, t.z / MM],
            "projection": "Orthographic"
            if view.getCameraType() == "Orthographic"
            else "Perspective",
        },
        "selected_guids": guids,
        "section": [],
    }


def apply(vp: dict) -> None:
    view = FreeCADGui.ActiveDocument.ActiveView
    cam = vp.get("camera") or {}
    space = cam.get("space")
    if cam.get("position") and space in ("ifc", "freecad"):
        k = MM if space == "ifc" else 1.0
        p = FreeCAD.Vector(*cam["position"]) * k
        t = FreeCAD.Vector(*cam["target"]) * k
        view.setCameraType(cam.get("projection", "Perspective"))
        from pivy import coin

        node = view.getCameraNode()
        node.position.setValue(p.x, p.y, p.z)
        node.pointAt(coin.SbVec3f(t.x, t.y, t.z), coin.SbVec3f(0, 0, 1))
        node.focalDistance.setValue((t - p).Length)
    FreeCADGui.Selection.clearSelection()
    wanted = set(vp.get("selected_guids") or [])
    if wanted:
        for o in FreeCAD.ActiveDocument.Objects:
            if _ifc_guid(o) in wanted:
                FreeCADGui.Selection.addSelection(o)
        if space not in ("ifc", "freecad"):
            FreeCADGui.SendMsgToActiveView("ViewSelection")
