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
