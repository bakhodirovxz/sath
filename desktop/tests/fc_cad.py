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


def check_dxf_insunits_scale(tmp: Path) -> None:
    """CAD-04: tahrirlanadigan DXF import `$INSUNITS` ni hisobga oladi (metr → ×1000 mm); birliksiz — mm + ogohlantirish."""
    import ezdxf
    import FreeCAD
    from ges_workbench import dxf_edit

    def make(name: str, insunits: int) -> Path:
        d = ezdxf.new("R2018")
        d.header["$INSUNITS"] = insunits
        msp = d.modelspace()
        msp.add_line((0, 0), (2, 0), dxfattribs={"layer": "L"})
        msp.add_circle((5, 5), 1.5, dxfattribs={"layer": "C"})
        msp.add_lwpolyline([(0, 0), (0, 3), (4, 3)], dxfattribs={"layer": "P"})
        p = tmp / name
        d.saveas(p)
        return p

    cases = {"m.dxf": (6, 1000.0), "mm.dxf": (4, 1.0), "cm.dxf": (5, 10.0), "none.dxf": (0, 1.0)}
    for name, (code, factor) in cases.items():
        path = make(name, code)
        scale, warn = dxf_edit.unit_scale(str(path))
        assert abs(scale - factor) < 1e-9 and bool(warn) == (code == 0), (name, scale, warn)
        doc, stats = dxf_edit.import_file(str(path))
        line = next(o for o in doc.Objects if o.Label == "Chiziq")
        circle = next(o for o in doc.Objects if o.Label == "Aylana")
        wire = next(o for o in doc.Objects if o.Label == "Polilinya")
        assert abs(line.Shape.Length - 2 * factor) < 1e-6, (name, line.Shape.Length)
        assert abs(float(circle.Radius) - 1.5 * factor) < 1e-6, (name, circle.Radius)
        assert abs(wire.Shape.Length - 7 * factor) < 1e-6, (name, wire.Shape.Length)
        assert stats.get("birlik_mm", 1.0) == factor, stats
        FreeCAD.closeDocument(doc.Name)
    assert dxf_edit._scale == 1.0  # build() dan keyin tiklanadi


def check_mesh_open_units_axis(tmp: Path) -> None:
    """CAD-04: FBX (Blender eksporti, UnitScaleFactor=100 → metr, UpAxis=Y) → FreeCAD mm, Z yuqoriga."""
    import FreeCAD
    from ges_workbench import mesh_open

    fbx = ROOT / "server" / "tests" / "samples" / "box.fbx"
    factor, y_up, warnings = mesh_open.units_and_axis(str(fbx))
    assert (factor, y_up, warnings) == (1000.0, True, []), (factor, y_up, warnings)
    assert mesh_open.units_and_axis(str(fbx), unit="mm")[0] == 1.0
    doc = FreeCAD.newDocument("CadMesh")
    objs = mesh_open.load_into(doc, str(fbx))
    bb = objs[0].Mesh.BoundBox
    # Blender dagi o'lcham: 0.51 × 0.53 × 0.41 m (Z yuqoriga) → mm
    assert abs(bb.XLength - 510.6) < 2 and abs(bb.YLength - 529.3) < 2 and abs(bb.ZLength - 406.2) < 2, bb
    FreeCAD.closeDocument(doc.Name)


def check_meshes_become_shapes_for_ifc(tmp: Path) -> None:
    """CAD-01: FBX/3DS dan kelgan Mesh::Feature IFC eksportidan oldin Part ga aylanadi (jimgina tushib qolmaydi)."""
    import FreeCAD
    import Mesh
    from ges_workbench import ifc_io, mesh_open

    doc = FreeCAD.newDocument("CadIfc")
    label = mesh_open.load_into(doc, str(ROOT / "server" / "tests" / "samples" / "box.fbx"))[0].Label
    bad = doc.addObject("Mesh::Feature", "Bosh")
    bad.Mesh = Mesh.Mesh()
    bad.Label = "Bo'sh mesh"
    made, failed = ifc_io.meshes_to_shapes(doc)
    assert len(made) == 1 and made[0].Shape.Faces and made[0].Shape.isValid(), made
    assert made[0].Label == label, (made[0].Label, label)
    assert len(failed) == 1 and failed[0].startswith("Bo'sh mesh"), failed
    assert not [o for o in doc.Objects if o.TypeId == "Mesh::Feature" and o.Name != "Bosh"]
    assert abs(made[0].Shape.BoundBox.ZLength - 406.2) < 2  # o'lcham saqlandi (mm)
    FreeCAD.closeDocument(doc.Name)


CHECKS = [check_dxf_face_order, check_dxf_insunits_scale, check_mesh_open_units_axis, check_meshes_become_shapes_for_ifc]


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
