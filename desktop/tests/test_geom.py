"""common/sath_common/geom.py — sof geometriya yadrosi (FreeCAD siz): yopiqlik, tashqi normallar, analitik hajm,
chord tolerance, bbox aniqligi, ear clipping, aks ettirish."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import geom  # noqa: E402


def _outward_convex(m, center) -> bool:
    """Qavariq shakl: har yuz normali markazdan tashqariga qaraydi."""
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    return bool((np.einsum("ij,ij->i", n, (a + b + c) / 3 - np.asarray(center)) > 0).all())


def test_segments_tolerance_multiple_of_four():
    for r in (0.05, 0.6, 3.0, 25.0, 400.0):
        n = geom.segments(r)
        assert n % 4 == 0 and geom.MIN_SEG <= n <= geom.MAX_SEG
        if geom.MIN_SEG < n < geom.MAX_SEG:
            assert r * (1 - math.cos(math.pi / n)) <= geom.TOL + 1e-12, r
    assert geom.segments(25.0, tol=0.001) > geom.segments(25.0)


def test_box_closed_outward_exact():
    m = geom.box((2.0, 3.0, 4.0), (1.0, -1.0, 0.5))
    assert geom.is_closed(m) and _outward_convex(m, (2.0, 0.5, 2.5))
    assert geom.signed_volume(m) == pytest.approx(24.0) and geom.area(m) == pytest.approx(52.0)
    assert geom.bbox(m).tolist() == [1.0, -1.0, 0.5, 3.0, 2.0, 4.5]


@pytest.mark.parametrize(
    "mesh,exact,bb",
    [
        (lambda: geom.cylinder(1.5, 4.0, base=(1.0, 2.0, -1.0)), math.pi * 1.5**2 * 4.0, [-0.5, 0.5, -1.0, 2.5, 3.5, 3.0]),
        (lambda: geom.cone(2.0, 0.5, 3.0), math.pi * 3.0 / 3 * (4.0 + 1.0 + 0.25), [-2.0, -2.0, 0.0, 2.0, 2.0, 3.0]),
        (lambda: geom.cone(1.0, 0.0, 2.0), math.pi * 2.0 / 3, [-1.0, -1.0, 0.0, 1.0, 1.0, 2.0]),
        (lambda: geom.torus(2.1, 0.6), 2 * math.pi**2 * 2.1 * 0.36, [-2.7, -2.7, -0.6, 2.7, 2.7, 0.6]),
    ],
    ids=["cylinder", "frustum", "cone", "torus"],
)
def test_revolved_primitives(mesh, exact, bb):
    m = mesh()
    assert geom.is_closed(m)
    vol = geom.signed_volume(m)
    assert 0 < vol <= exact and vol == pytest.approx(exact, rel=4e-3)  # ichki chizilgan: biroz kichik, ≤ 2·θ²/6
    assert geom.bbox(m) == pytest.approx(bb, abs=1e-9)  # n 4 ga karrali — ekstremumlar aniq


def test_cylinder_normals_outward():
    assert _outward_convex(geom.cylinder(1.0, 2.0), (0.0, 0.0, 1.0))


def test_extrude_concave_u_profile():
    u = [(-3, 0, -1), (3, 0, -1), (3, 0, 4), (2, 0, 4), (2, 0, 0), (-2, 0, 0), (-2, 0, 4), (-3, 0, 4)]
    m = geom.extrude(u, (0.0, 10.0, 0.0))
    assert geom.is_closed(m)
    assert geom.signed_volume(m) == pytest.approx(10.0 * (6 * 5 - 4 * 4))
    m2 = geom.extrude(u[::-1], (0.0, 10.0, 0.0))  # teskari aylanish — natija bir xil
    assert geom.signed_volume(m2) == pytest.approx(geom.signed_volume(m))


def test_triangulate_orientation_and_errors():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    t = geom.triangulate(sq)
    assert t.shape == (2, 3)
    p = np.asarray(sq, float)
    assert all(geom._cross2(p[a], p[b], p[c]) > 0 for a, b, c in t)
    tcw = geom.triangulate(sq[::-1])
    pcw = p[::-1]
    assert all(geom._cross2(pcw[a], pcw[b], pcw[c]) < 0 for a, b, c in tcw)  # CW kirdi — CW chiqdi
    col = [(0, 0), (1, 0), (2, 0), (2, 1), (0, 1)]  # kollinear uch saqlanadi
    assert len(geom.triangulate(col)) == 3
    with pytest.raises(ValueError):
        geom.triangulate([(0, 0), (1, 0), (2, 0), (3, 0)])  # nol yuzali (degenerat)


def test_partial_revolve_disc_touching_axis():
    """Chiqarish quvuri tirsagi: o'qqa tegadigan disk 90° — o'q nuqtasi payvandlanadi, qopqoqlar bilan yopiq."""
    R = 2.25
    m = geom.revolve(geom.circle(R, geom.segments(R), (R, 0.0)), math.pi / 2)
    assert geom.is_closed(m)
    assert geom.signed_volume(m) == pytest.approx(math.pi**2 * R**3 / 2, rel=4e-3)  # Pappus


def test_sweep_annulus_along_bent_path():
    """Bosimli quvur: halqa kesim to'g'ri — yoy — to'g'ri yo'l bo'ylab; hajm = halqa yuzasi × o'q uzunligi."""
    R, ro, ri, m_arc = 8.0, 1.22, 1.2, 24
    path, tans = [(0.0, 0.0, 0.0)], [(0.0, 0.0, -1.0)]
    for k in range(m_arc + 1):  # (0,0,−10) dan +Y ga 90° yoy, markaz (0, R, −10)
        g = math.pi / 2 * k / m_arc
        path.append((0.0, R - R * math.cos(g), -10.0 - R * math.sin(g)))
        tans.append((0.0, math.sin(g), -math.cos(g)))
    path.append((0.0, R + 6.0, -10.0 - R))
    tans.append((0.0, 1.0, 0.0))
    n = geom.segments(ro)
    m = geom.sweep(geom.circle(ro, n), path, tans, (1.0, 0.0, 0.0), hole=geom.circle(ri, n))
    assert geom.is_closed(m)
    exact = math.pi * (ro**2 - ri**2) * (10.0 + R * math.pi / 2 + 6.0)
    assert geom.signed_volume(m) == pytest.approx(exact, rel=4e-3)
    solid = geom.sweep(geom.circle(ro, n), path, tans, (1.0, 0.0, 0.0))  # teshiksiz — qopqoqlar uchburchaklangan
    assert geom.is_closed(solid) and geom.signed_volume(solid) > geom.signed_volume(m)


def test_loft_rectangles_prismatoid_exact():
    def rect(y, w, h):
        return [(-w / 2, y, -h / 2), (w / 2, y, -h / 2), (w / 2, y, h / 2), (-w / 2, y, h / 2)]

    m = geom.loft(rect(0.0, 4.5, 4.5), rect(12.0, 8.0, 4.0))
    assert geom.is_closed(m)
    a1, a2, am = 4.5 * 4.5, 32.0, (4.5 + 8.0) / 2 * (4.5 + 4.0) / 2
    assert geom.signed_volume(m) == pytest.approx(12.0 / 6 * (a1 + 4 * am + a2), rel=1e-12)


def test_transform_mirror_keeps_outward_and_merge_offsets():
    m = geom.box((1.0, 2.0, 3.0))
    mirror = np.diag([-1.0, 1.0, 1.0, 1.0])
    mm = geom.transform(m, mirror)
    assert geom.is_closed(mm) and geom.signed_volume(mm) == pytest.approx(6.0)
    both = geom.merge(m, geom.translate(m, (5.0, 0.0, 0.0)))
    assert len(both[0]) == 16 and both[1].max() == 15 and geom.signed_volume(both) == pytest.approx(12.0)


def test_is_closed_detects_open_and_degenerate():
    v, f = geom.box((1.0, 1.0, 1.0))
    assert not geom.is_closed((v, f[1:]))
    bad = f.copy()
    bad[0, 1] = bad[0, 0]
    assert not geom.is_closed((v, bad))


def test_invalid_input_fails_loudly():
    circ = geom.circle(1.0, 8)
    path, tans = [(0.0, 0.0, 0.0), (0.0, 0.0, -1.0)], [(0.0, 0.0, -1.0)] * 2
    bad = [
        lambda: geom.circle(0.0, 8),
        lambda: geom.circle(1.0, 2),
        lambda: geom.box((1.0, 0.0, 1.0)),
        lambda: geom.extrude([(0, 0, 0), (1, 0, 0), (1, 1, 0)], (0.0, 0.0, 0.0)),
        lambda: geom.cylinder(0.0, 1.0),
        lambda: geom.cylinder(1.0, -1.0),
        lambda: geom.cone(0.0, 0.0, 1.0),
        lambda: geom.cone(-1.0, 1.0, 1.0),
        lambda: geom.cone(1.0, 0.5, 0.0),
        lambda: geom.torus(1.0, 0.0),
        lambda: geom.torus(0.5, 1.0),
        lambda: geom.revolve([(1.0, 0.0), (1.0, 1.0)]),  # bir chiziq — ikki uch
        lambda: geom.revolve([(1.0, 0.0), (1.0, 1.0), (1.0, 2.0)]),  # nol yuza
        lambda: geom.revolve([(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]),  # ρ <= 0
        lambda: geom.revolve([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)], 0.0),
        lambda: geom.revolve([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)], 7.0),
        lambda: geom.sweep(circ, path[:1], tans[:1], (1.0, 0.0, 0.0)),  # bir nuqtali yo'l
        lambda: geom.sweep(circ, path, tans[:1], (1.0, 0.0, 0.0)),  # tangentlar soni mos emas
        lambda: geom.sweep(circ[:2], path, tans, (1.0, 0.0, 0.0)),  # profilda < 3 uch
        lambda: geom.sweep(circ, path, [(0.0, 0.0, 0.0)] * 2, (1.0, 0.0, 0.0)),  # nol tangent
        lambda: geom.sweep(circ, path, [(1.0, 0.0, 0.0)] * 2, (1.0, 0.0, 0.0)),  # tangent ‖ normal
        lambda: geom.sweep(circ, path, tans, (0.0, 0.0, 0.0)),  # nol normal
    ]
    for fn in bad:
        with pytest.raises(ValueError):
            fn()


def test_cone_apex_either_end_and_nonfinite_not_closed():
    assert geom.is_closed(geom.cone(0.0, 1.0, 2.0)) and geom.signed_volume(geom.cone(0.0, 1.0, 2.0)) > 0
    v, f = geom.box((1.0, 1.0, 1.0))
    v = v.copy()
    v[0, 0] = np.nan
    assert not geom.is_closed((v, f))
