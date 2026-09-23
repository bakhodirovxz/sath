"""FreeCAD workbench (legacy) CAD importi — GUI siz, FreeCAD Python moduli bilan.

    <fc-py313>/python.exe desktop/tests/fc_cad.py      (GES_FC_HOME — conda-forge FreeCAD muhiti)

pytest: desktop/tests/test_freecad_cad.py shu skriptni ishga tushiradi (FreeCAD topilmasa skip).
ezdxf / assimp-py Blender addoni wheel laridan vaqtinchalik papkaga ochiladi. Oxirida "[OK] fc_cad" chiqadi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = os.environ.get("GES_FC_HOME") or os.path.join(os.path.expanduser("~"), "Tools", "fc-py313")


def _setup() -> Path:
    lib = os.path.join(HOME, "Library")
    root = lib if os.path.isdir(lib) else HOME
    for d in (os.path.join(root, "bin"), os.path.join(root, "lib")):
        if os.path.isdir(d):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
            sys.path.append(d)
    wheels = Path(tempfile.mkdtemp(prefix="sath-fc-wheels-"))
    for whl in (ROOT / "desktop" / "blender" / "sath" / "wheels").glob("*.whl"):
        with zipfile.ZipFile(whl) as z:
            z.extractall(wheels)
    sys.path.insert(0, str(wheels))
    sys.path.insert(0, str(ROOT / "desktop" / "GesWorkbench"))
    return wheels


def _normals_same_direction(shape) -> bool:
    ns = []
    for f in shape.Faces:
        u0, u1, v0, v1 = f.ParameterRange
        ns.append(f.normalAt((u0 + u1) / 2, (v0 + v1) / 2))
    return all(ns[0].dot(n) > 0 for n in ns[1:])


def check_dxf_face_order(tmp: Path) -> None:
    """CAD-02: SOLID (0-1-3-2) kvadrat va 3DFACE (0-1-2-3) — maydon to'g'ri, «kapalak» yo'q."""
    import ezdxf
    import FreeCAD
    from ges_workbench import dxf_edit

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_solid([(0, 0), (1000, 0), (0, 1000), (1000, 1000)], dxfattribs={"layer": "S"})
    msp.add_3dface([(0, 0, 0), (2000, 0, 0), (2000, 0, 3000), (0, 0, 3000)], dxfattribs={"layer": "F"})
    msp.add_3dface([(0, 0, 0), (1000, 0, 0), (1000, 1000, 500), (0, 1000, 0)], dxfattribs={"layer": "N"})
    fc = FreeCAD.newDocument("CadFaces")
    dxf_edit.build(fc, doc)
    faces = [o for o in fc.Objects if o.TypeId == "Part::Feature" and o.Shape.Faces]
    areas = sorted(round(o.Shape.Area) for o in faces)
    assert len(faces) == 3, [o.Label for o in fc.Objects]
    assert 1_000_000 in areas and 6_000_000 in areas, areas  # kvadrat 1 m², 3DFACE 6 m² (mm²)
    for o in faces:
        assert _normals_same_direction(o.Shape), o.Label
    FreeCAD.closeDocument(fc.Name)


CHECKS = [check_dxf_face_order]


def main() -> int:
    _setup()
    tmp = Path(tempfile.mkdtemp(prefix="sath-fc-cad-"))
    fails = 0
    for fn in CHECKS:
        try:
            fn(tmp)
            print(f"[ok] {fn.__name__}", flush=True)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print(f"[FAIL] {fn.__name__}", flush=True)
            fails += 1
    print("[OK] fc_cad" if not fails else f"[FAIL] fc_cad: {fails}", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
