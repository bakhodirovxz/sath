"""common/sath_common/cad_common.py (server, Blender addoni, FreeCAD workbench uchun umumiy) — bpy/FreeCAD siz."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import cad_common  # noqa: E402

ezdxf = pytest.importorskip("ezdxf")


def _normal(tri):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _same_direction(tris):
    ns = [_normal(t) for t in tris]
    assert all(abs(sum(a * b for a, b in zip(ns[0], n, strict=True))) > 0 for n in ns)
    return all(sum(a * b for a, b in zip(ns[0], n, strict=True)) > 0 for n in ns[1:])


# --- CAD-02: SOLID/TRACE 0-1-3-2, 3DFACE 0-1-2-3 ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["SOLID", "TRACE"])
def test_solid_square_two_triangles_same_normal(kind):
    doc = ezdxf.new()
    msp = doc.modelspace()
    # AutoCAD SOLID kvadrat: uchlar «Z» tartibda (0,0) (1,0) (0,1) (1,1)
    pts = [(0, 0), (1, 0), (0, 1), (1, 1)]
    e = msp.add_solid(pts) if kind == "SOLID" else msp.add_trace(pts)
    verts = cad_common.dxf_face_vertices(e)
    assert verts == [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]  # aylanish tartibi
    tris = cad_common.dxf_triangles(e)
    assert len(tris) == 2 and _same_direction(tris)
    assert all(_normal(t)[2] > 0 for t in tris)
    # maydon = 1 (kapalak bo'lsa 0.5 bo'lardi)
    assert abs(sum(_normal(t)[2] / 2 for t in tris) - 1.0) < 1e-9


def test_3dface_quad_two_triangles_same_normal():
    doc = ezdxf.new()
    e = doc.modelspace().add_3dface([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)])
    tris = cad_common.dxf_triangles(e)
    assert len(tris) == 2 and _same_direction(tris)
    assert abs(sum(sum(c * c for c in _normal(t)) ** 0.5 / 2 for t in tris) - 6.0) < 1e-9


def test_3dface_triangle_and_degenerate():
    doc = ezdxf.new()
    msp = doc.modelspace()
    tri = msp.add_3dface([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 0)])
    assert len(cad_common.dxf_triangles(tri)) == 1
    line = msp.add_3dface([(0, 0, 0), (1, 0, 0), (1, 0, 0), (1, 0, 0)])
    assert cad_common.dxf_triangles(line) == []
    assert cad_common.dxf_triangles(msp.add_line((0, 0), (1, 1))) is None


def test_polymesh_is_read():
    doc = ezdxf.new()
    pm = doc.modelspace().add_polymesh((3, 3))
    for i in range(3):
        for j in range(3):
            pm.set_mesh_vertex((i, j), (i, j, 0))
    tris = cad_common.dxf_triangles(pm)
    assert len(tris) == 8 and _same_direction(tris)


# --- CAD-04: birlik va o'q ---------------------------------------------------------------------------------------

SAMPLES = ROOT / "server" / "tests" / "samples"


def test_detect_dxf_insunits(tmp_path):
    for code, unit in ((4, "mm"), (6, "m"), (1, "in")):
        doc = ezdxf.new()
        doc.header["$INSUNITS"] = code
        doc.saveas(tmp_path / "a.dxf")
        info = cad_common.detect_units_and_axis(tmp_path / "a.dxf")
        assert (info.unit, info.uncertain, info.up_axis, info.source) == (unit, False, "Z", "$INSUNITS")
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 0  # birliksiz
    doc.saveas(tmp_path / "b.dxf")
    info = cad_common.detect_units_and_axis(tmp_path / "b.dxf")
    assert info.unit is None and info.scale is None and info.uncertain and info.note


def test_detect_gltf_and_unknown_formats(tmp_path):
    g = cad_common.detect_units_and_axis(tmp_path / "x.glb")
    assert (g.unit, g.scale, g.up_axis, g.uncertain, g.axis_uncertain) == ("m", 1.0, "Y", False, False)
    o = cad_common.detect_units_and_axis(tmp_path / "x.obj")
    assert o.unit is None and o.uncertain and o.up_axis == "Y" and o.axis_uncertain  # faqat taklif
    s = cad_common.detect_units_and_axis(tmp_path / "x.3ds")
    assert s.uncertain and s.up_axis == "Z"


def test_detect_fbx_binary_global_settings():
    info = cad_common.detect_units_and_axis(SAMPLES / "box.fbx")  # Blender eksporti: UnitScaleFactor=100, Y-up
    assert (info.unit, info.scale, info.up_axis) == ("m", 1.0, "Y")
    assert not info.uncertain and not info.axis_uncertain


def test_detect_fbx_ascii_units_axis_and_user_props(tmp_path):
    fbx = tmp_path / "max.fbx"
    fbx.write_text(
        "; FBX 7.4.0 project file\nGlobalSettings:  {\n\tVersion: 1000\n\tProperties70:  {\n"
        '\t\tP: "UpAxis", "int", "Integer", "",2\n\t\tP: "UpAxisSign", "int", "Integer", "",1\n'
        '\t\tP: "UnitScaleFactor", "double", "Number", "",0.1\n\t}\n}\n'
        'Objects:  {\n\tModel: 123, "Model::Devor", "Mesh" {\n\t\tProperties70:  {\n'
        '\t\t\tP: "sath_guid", "KString", "", "U",  "2O2Fr$t4X7Zf8NOew3FLOH"\n\t\t}\n\t}\n}\n',
        encoding="utf-8",
    )
    info = cad_common.detect_units_and_axis(fbx)
    assert (info.unit, info.up_axis, info.uncertain) == ("mm", "Z", False)
    assert cad_common.fbx_info(fbx)["models"]["Devor"]["sath_guid"] == "2O2Fr$t4X7Zf8NOew3FLOH"


def test_to_z_up():
    assert cad_common.to_z_up((1, 2, 3)) == (1.0, -3.0, 2.0)
