"""Sath sof geometriya yadrosi — FreeCAD Part o'rniga (spec §6). numpy, float64, bpy/FreeCAD siz.

Mesh = (V, F): V — (n, 3) float64 nuqtalar (metr), F — (m, 3) int64 uchburchaklar. Yopiq qobiqlarda normal
tashqariga (tashqaridan qaraganda soat miliga qarshi). Kirish/chiqish faqat numpy massivlari — keyin `sath_core`
(C++23, nanobind) xuddi shu API bilan almashtiriladi, bu modul paritet etaloni bo'lib qoladi.

Tessellatsiya chord tolerance bo'yicha: aylana bo'lagining sagittasi ≤ tol (default 5 mm). Segmentlar soni 4 ga
karrali (o'qlar bo'ylab ekstremum nuqtalar aniq → bbox aniq) va kamida MIN_SEG (ichki chizilgan ko'pburchakning
hajm xatosi ≈ θ²/6 ≤ 0.16 %, θ = 2π/MIN_SEG). Boolean (cut/fuse) yo'q: GES turlari to'g'ridan-to'g'ri quriladi
(`ges_kinds`), tegib turgan qismlar alohida yopiq qobiq bo'lib qoladi.
"""

from __future__ import annotations

import math

import numpy as np

TOL = 0.005
MIN_SEG = 64
MAX_SEG = 512
Mesh = tuple[np.ndarray, np.ndarray]


def segments(radius: float, tol: float = TOL) -> int:
    """To'liq aylana uchun segmentlar soni: sagitta r·(1 − cos(π/n)) ≤ tol; 4 ga karrali, [MIN_SEG, MAX_SEG]."""
    if radius <= 0 or tol >= radius:
        n = MIN_SEG
    else:
        n = math.ceil(math.pi / math.acos(1.0 - tol / radius))
    n = max(MIN_SEG, min(MAX_SEG, n))
    return (n + 3) // 4 * 4


def circle(r: float, n: int, center: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """(n, 2) aylana nuqtalari, burchak 0 dan soat miliga qarshi (n 4 ga karrali — ±r nuqtalar aniq)."""
    t = 2.0 * math.pi * np.arange(n) / n
    return np.column_stack([center[0] + r * np.cos(t), center[1] + r * np.sin(t)])


def _as_mesh(verts, faces) -> Mesh:
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3), np.asarray(faces, dtype=np.int64).reshape(-1, 3)


def merge(*meshes: Mesh) -> Mesh:
    """Bir nechta mesh → bitta (V, F); indekslar siljitiladi, qobiqlar alohida qoladi."""
    vs, fs, off = [], [], 0
    for v, f in meshes:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(vs), np.vstack(fs)


def transform(m: Mesh, matrix) -> Mesh:
    """4×4 affin matritsa; aks ettirishda (det < 0) uchburchak yo'nalishi tiklanadi (normal tashqarida qoladi)."""
    mat = np.asarray(matrix, dtype=np.float64)
    v, f = m
    v2 = v @ mat[:3, :3].T + mat[:3, 3]
    return v2, (f[:, ::-1].copy() if np.linalg.det(mat[:3, :3]) < 0 else f.copy())


def translate(m: Mesh, offset) -> Mesh:
    return m[0] + np.asarray(offset, dtype=np.float64), m[1].copy()


def signed_volume(m: Mesh) -> float:
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def area(m: Mesh) -> float:
    v, f = m
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0)


def bbox(m: Mesh) -> np.ndarray:
    """[xmin, ymin, zmin, xmax, ymax, zmax]"""
    return np.concatenate([m[0].min(axis=0), m[0].max(axis=0)])


def is_closed(m: Mesh) -> bool:
    """Yopiq va izchil yo'naltirilgan qobiq(lar): har yo'naltirilgan qirra bir marta, teskarisi ham bor;
    takroriy indeksli (degenerat) uchburchak yo'q."""
    v, f = m
    if len(f) == 0 or (f[:, 0] == f[:, 1]).any() or (f[:, 1] == f[:, 2]).any() or (f[:, 0] == f[:, 2]).any():
        return False
    e = f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    nv = len(v)
    key = e[:, 0] * nv + e[:, 1]
    rev = e[:, 1] * nv + e[:, 0]
    return len(np.unique(key)) == len(key) and bool(np.isin(rev, key).all())


def _area2(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _cross2(o, a, b) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _in_tri(q, a, b, c, eps: float) -> bool:
    """q CCW uchburchak (a, b, c) ichida yoki chegarasida."""
    return _cross2(a, b, q) >= -eps and _cross2(b, c, q) >= -eps and _cross2(c, a, q) >= -eps


def triangulate(poly) -> np.ndarray:
    """Oddiy ko'pburchak (n, 2) → (n − 2, 3) indekslar, quloq kesish (ear clipping). Uchburchaklar ko'pburchak
    bilan BIR XIL aylanish yo'nalishida (CW kirsa — CW). Kollinear uchlar saqlanadi. O'z-o'zini kesish
    tekshirilmaydi (kirish — ges_kinds profillari); quloq topilmasa (degenerat) — ValueError."""
    p = np.asarray(poly, dtype=np.float64)
    n = len(p)
    if n < 3:
        raise ValueError("ko'pburchakda kamida 3 uch kerak")
    ccw = _area2(p) > 0
    idx = list(range(n)) if ccw else list(range(n - 1, -1, -1))
    scale = float(np.abs(p).max()) or 1.0
    eps = 1e-12 * scale * scale
    tris: list[tuple[int, int, int]] = []
    while len(idx) > 3:
        m = len(idx)
        for i in range(m):
            a, b, c = idx[i - 1], idx[i], idx[(i + 1) % m]
            if _cross2(p[a], p[b], p[c]) <= eps:
                continue  # botiq yoki kollinear uch — quloq emas
            if any(_in_tri(p[k], p[a], p[b], p[c], eps) for k in idx if k not in (a, b, c)):
                continue
            tris.append((a, b, c))
            del idx[i]
            break
        else:
            raise ValueError("ko'pburchak degenerat yoki oddiy emas (quloq topilmadi)")
    tris.append((idx[0], idx[1], idx[2]))
    t = np.array(tris, dtype=np.int64)
    return t if ccw else t[:, ::-1].copy()


def _normal(p3: np.ndarray) -> np.ndarray:
    """Tekis 3D ko'pburchak normali (Newell usuli), uzunligi = 2 · yuza."""
    return np.cross(p3, np.roll(p3, -1, axis=0)).sum(axis=0)


def _cap(p3: np.ndarray) -> np.ndarray:
    """Tekis 3D ko'pburchak uchburchaklari, normali ko'pburchak normali (Newell) bilan bir tomonda."""
    nrm = _normal(p3)
    ax = int(np.argmax(np.abs(nrm)))
    t = triangulate(p3[:, [i for i in range(3) if i != ax]])
    tn = np.cross(p3[t[:, 1]] - p3[t[:, 0]], p3[t[:, 2]] - p3[t[:, 0]]).sum(axis=0)
    return t[:, ::-1].copy() if np.dot(tn, nrm) < 0 else t


def extrude(poly, vec) -> Mesh:
    """Tekis 3D ko'pburchakni (n, 3; botiq bo'lishi mumkin) `vec` bo'ylab cho'zish — prizma."""
    p = np.asarray(poly, dtype=np.float64).reshape(-1, 3)
    d = np.asarray(vec, dtype=np.float64)
    if np.dot(_normal(p), d) < 0:
        p = p[::-1].copy()
    n = len(p)
    t = _cap(p)
    i = np.arange(n)
    j = (i + 1) % n
    sides = np.concatenate([np.column_stack([i, j, j + n]), np.column_stack([i, j + n, i + n])])
    return _as_mesh(np.vstack([p, p + d]), np.concatenate([t[:, ::-1], t + n, sides]))


def box(size, origin=(0.0, 0.0, 0.0)) -> Mesh:
    """O'qlarga parallel quti: origin — minimal burchak, size — (dx, dy, dz)."""
    sx, sy, sz = (float(s) for s in size)
    x, y, z = (float(o) for o in origin)
    return extrude([(x, y, z), (x + sx, y, z), (x + sx, y + sy, z), (x, y + sy, z)], (0.0, 0.0, sz))


def revolve(profile, angle: float = 2 * math.pi, *, tol: float = TOL, matrix=None) -> Mesh:
    """(ρ, z) yarim tekislikdagi yopiq profilni (n, 2; ρ ≥ 0) lokal Z o'qi atrofida `angle` (0 < angle ≤ 2π) ga,
    +X dan +Y tomonga aylantirish. ρ ≈ 0 uchlar o'qda — bitta umumiy nuqta (payvandlanadi). angle < 2π — ikki
    uchida profil qopqog'i. `matrix` (4×4) natijani joylashtiradi (boshqa o'q atrofida aylantirish uchun)."""
    p = np.asarray(profile, dtype=np.float64)
    if _area2(p) < 0:
        p = p[::-1].copy()
    if (p[:, 0] < -1e-12).any():
        raise ValueError("revolve: profil ρ ≥ 0 bo'lishi kerak")
    n = len(p)
    rmax = float(p[:, 0].max())
    full = angle >= 2 * math.pi - 1e-12
    nseg = segments(rmax, tol)
    steps = nseg if full else max(1, math.ceil(nseg * angle / (2 * math.pi)))
    rings = steps if full else steps + 1
    on_axis = p[:, 0] <= 1e-9 * max(1.0, rmax)
    verts: list[tuple[float, float, float]] = []
    index = np.empty((rings, n), dtype=np.int64)
    axis_id: dict[int, int] = {}
    for k in range(rings):
        phi = angle * k / steps
        c, s = math.cos(phi), math.sin(phi)
        for i in range(n):
            if on_axis[i]:
                if i not in axis_id:
                    axis_id[i] = len(verts)
                    verts.append((0.0, 0.0, float(p[i, 1])))
                index[k, i] = axis_id[i]
            else:
                index[k, i] = len(verts)
                verts.append((float(p[i, 0]) * c, float(p[i, 0]) * s, float(p[i, 1])))
    faces: list = []
    for k in range(steps):
        k2 = (k + 1) % rings
        for i in range(n):
            j = (i + 1) % n
            if on_axis[i] and on_axis[j]:
                continue  # o'q bo'ylab qirra — sirt hosil qilmaydi
            q0, q1, q2, q3 = index[k, i], index[k2, i], index[k2, j], index[k, j]
            for tri in ((q0, q1, q2), (q0, q2, q3)):
                if len({int(x) for x in tri}) == 3:
                    faces.append(tri)
    if not full:
        t = triangulate(p)  # profil CCW → φ = 0 qopqog'i normali −Y (tashqariga)
        faces.extend(index[0][t].tolist())
        faces.extend(index[steps][t[:, ::-1]].tolist())
    m = _as_mesh(verts, faces)
    return transform(m, matrix) if matrix is not None else m


def cylinder(r: float, h: float, *, base=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli silindr, asosi markazi `base`."""
    return translate(revolve([(0.0, 0.0), (r, 0.0), (r, h), (0.0, h)], tol=tol), base)


def cone(r1: float, r2: float, h: float, *, base=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli kesik konus: pastda r1, yuqorida r2 (0 — uchli)."""
    prof = [(0.0, 0.0), (r1, 0.0)] + ([(r2, h)] if r2 > 0 else []) + [(0.0, h)]
    return translate(revolve(prof, tol=tol), base)


def torus(big_r: float, r: float, *, center=(0.0, 0.0, 0.0), tol: float = TOL) -> Mesh:
    """Z o'qli tor: markaziy aylana radiusi big_r, kesim radiusi r."""
    return translate(revolve(circle(r, segments(r, tol), (big_r, 0.0)), tol=tol), center)


def sweep(profile, path, tangents, normal, *, hole=None) -> Mesh:
    """Yopiq profilni (n, 2) yassi yo'l bo'ylab cho'zish. Kesim k: markazi path[k], tekisligi tangents[k] ga
    perpendikulyar; profil u o'qi — `normal` (yo'l tekisligiga perpendikulyar, doimiy), v o'qi — tangent × normal.
    hole (n, 2; profil bilan bir xil yo'nalish va uchlar soni) — ichki kontur: quvur, halqa qopqoqlar."""
    prof = np.asarray(profile, dtype=np.float64)
    inner = None if hole is None else np.asarray(hole, dtype=np.float64)
    if _area2(prof) < 0:
        prof = prof[::-1].copy()
        inner = None if inner is None else inner[::-1].copy()
    pts = np.asarray(path, dtype=np.float64)
    tan = np.asarray(tangents, dtype=np.float64)
    tan = tan / np.linalg.norm(tan, axis=1)[:, None]
    u = np.asarray(normal, dtype=np.float64)
    u = u / np.linalg.norm(u)
    bv = np.cross(tan, u)
    bv = bv / np.linalg.norm(bv, axis=1)[:, None]
    k, n = len(pts), len(prof)

    def rings(pr: np.ndarray) -> np.ndarray:
        return (pts[:, None, :] + pr[None, :, 0, None] * u + pr[None, :, 1, None] * bv[:, None, :]).reshape(-1, 3)

    verts = [rings(prof)] + ([] if inner is None else [rings(inner)])
    s = np.arange(k - 1)[:, None]
    i = np.arange(n)[None, :]
    j = (i + 1) % n
    a0, a1 = (s * n + i).ravel(), (s * n + j).ravel()
    b0, b1 = ((s + 1) * n + i).ravel(), ((s + 1) * n + j).ravel()
    faces = [np.column_stack([a0, a1, b1]), np.column_stack([a0, b1, b0])]
    last = (k - 1) * n
    ii = np.arange(n)
    jj = (ii + 1) % n
    if inner is None:
        t = triangulate(prof)
        faces += [t[:, ::-1], t + last]
    else:
        h = k * n  # ichki kontur indeks siljishi
        faces += [np.column_stack([a0 + h, b1 + h, a1 + h]), np.column_stack([a0 + h, b0 + h, b1 + h])]
        faces += [np.column_stack([ii, ii + h, jj + h]), np.column_stack([ii, jj + h, jj])]  # boshi (−t)
        o = ii + last
        faces += [np.column_stack([o, jj + last, jj + last + h]), np.column_stack([o, jj + last + h, o + h])]  # oxiri
    return _as_mesh(np.vstack(verts), np.concatenate(faces))


def loft(ring_a, ring_b) -> Mesh:
    """Ikki tekis yopiq kontur (n, 3; mos uchlar) orasida to'g'ri chiziqli (ruled) yuza + qopqoqlar."""
    a = np.asarray(ring_a, dtype=np.float64)
    b = np.asarray(ring_b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("loft: konturlarda uchlar soni bir xil bo'lishi kerak")
    d = b.mean(axis=0) - a.mean(axis=0)
    if np.dot(_normal(a), d) < 0:
        a, b = a[::-1].copy(), b[::-1].copy()
    if np.dot(_normal(b), d) <= 0:
        raise ValueError("loft: konturlar yo'nalishi mos emas")
    n = len(a)
    i = np.arange(n)
    j = (i + 1) % n
    sides = np.concatenate([np.column_stack([i, j, j + n]), np.column_stack([i, j + n, i + n])])
    return _as_mesh(np.vstack([a, b]), np.concatenate([_cap(a)[:, ::-1], _cap(b) + n, sides]))
