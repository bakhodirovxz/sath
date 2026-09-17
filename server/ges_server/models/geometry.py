"""IFC geometriya tahlili (IfcOpenShell): hajm-miqdor hisobi (QTO) va to'qnashuvlar (clash).

Natijalar fayl sha256 bo'yicha keshlanadi: data/derived/<sha>.qto.json, <sha>.clash.json —
bir xil fayl uchun qayta hisoblanmaydi.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import get_settings

log = logging.getLogger("ges_server.geometry")

# Katta modellarda cheklov (xotira/vaqt): shundan ko'p element bo'lsa clash faqat AABB bilan
CLASH_EXACT_MAX_ELEMENTS = 1500
CLASH_EXACT_MAX_TRIANGLE_PAIRS = 4_000_000


@dataclass
class Mesh:
    guid: str
    ifc_type: str
    name: str
    storey: str
    verts: np.ndarray  # (n,3) metr, dunyo koordinatalari
    faces: np.ndarray  # (m,3)

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.verts.min(axis=0), self.verts.max(axis=0)


def _derived_path(sha: str, kind: str) -> Path:
    d = get_settings().data_dir / "derived"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha}.{kind}.json"


_MESH_CACHE: dict[str, list[Mesh]] = {}
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def load_meshes(path: Path) -> list[Mesh]:
    """Barcha geometriyali IfcElement lar uchun uchburchak mesh — fayl bo'yicha xotirada keshlanadi
    (QTO va clash bir yuklashdan foydalanadi; oxirgi 3 ta fayl)."""
    key = str(path)
    with _lock("mesh:" + key):
        if key in _MESH_CACHE:
            return _MESH_CACHE[key]
        meshes = _load_meshes(path)
        if len(_MESH_CACHE) >= 3:
            _MESH_CACHE.pop(next(iter(_MESH_CACHE)))
        _MESH_CACHE[key] = meshes
        return meshes


def _load_meshes(path: Path) -> list[Mesh]:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as uel

    f = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    scale = _unit_scale(f)
    out: list[Mesh] = []
    for e in f.by_type("IfcElement"):
        if not e.Representation or e.is_a("IfcOpeningElement") or e.is_a("IfcFeatureElement"):
            continue
        fast = _tessellated(e, scale)
        if fast is not None:
            verts, faces = fast  # tessellyatsiya (masalan FreeCAD dan) — OCC siz, tez
        else:
            try:
                shape = ifcopenshell.geom.create_shape(settings, e)
            except Exception as ex:  # noqa: BLE001 — bitta element buzuq bo'lsa qolganlari hisoblansin
                log.warning("geometriya yo'q %s %s: %s", e.is_a(), e.GlobalId, ex)
                continue
            verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
            faces = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if len(verts) == 0 or len(faces) == 0:
            continue
        storey = uel.get_container(e)
        out.append(
            Mesh(
                guid=e.GlobalId,
                ifc_type=e.is_a(),
                name=e.Name or "",
                storey=(storey.Name or "") if storey is not None else "",
                verts=verts,
                faces=faces,
            )
        )
    return out


def _unit_scale(f) -> float:
    """Loyiha uzunlik birligi → metr koeffitsienti (mm bo'lsa 0.001)."""
    try:
        import ifcopenshell.util.unit as uu

        return float(uu.calculate_unit_scale(f))
    except Exception:  # noqa: BLE001
        return 1.0


FAST_ITEMS = ("IfcTriangulatedFaceSet", "IfcPolygonalFaceSet", "IfcFacetedBrep")


def _item_mesh(it, scale: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Tessellyatsiya/faceted item → (verts, faces); ko'pburchaklar yelpig'ich (fan) bilan uchburchak."""
    if it.is_a("IfcTriangulatedFaceSet"):
        v = np.array(it.Coordinates.CoordList, dtype=float) * scale
        f = np.array(it.CoordIndex, dtype=np.int64) - 1
        return (v, f) if v.ndim == 2 and f.ndim == 2 and f.shape[1] == 3 else None
    polys: list[list[int]] = []
    if it.is_a("IfcPolygonalFaceSet"):
        v = np.array(it.Coordinates.CoordList, dtype=float) * scale
        for face in it.Faces:
            polys.append([i - 1 for i in face.CoordIndex])
    elif it.is_a("IfcFacetedBrep"):
        index: dict[int, int] = {}
        pts: list = []
        for face in it.Outer.CfsFaces:
            loop = None
            for b in face.Bounds:
                if b.is_a("IfcFaceOuterBound") or loop is None:
                    loop = b.Bound
            if loop is None or not loop.is_a("IfcPolyLoop"):
                return None
            poly = []
            for pt in loop.Polygon:
                k = pt.id()
                if k not in index:
                    index[k] = len(pts)
                    pts.append(pt.Coordinates)
                poly.append(index[k])
            polys.append(poly)
        v = np.array(pts, dtype=float) * scale
    else:
        return None
    tris = [(pg[0], pg[i], pg[i + 1]) for pg in polys for i in range(1, len(pg) - 1)]
    if not tris:
        return None
    return v, np.array(tris, dtype=np.int64)


def _tessellated(e, scale: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Element faqat tessellyatsiya/faceted item lardan iborat bo'lsa (masalan FreeCAD dan chiqqan
    IfcFacetedBrep) — koordinatalarni to'g'ridan-to'g'ri o'qib, joylashuvni qo'llaymiz
    (IfcOpenShell OCC tikuvi 40k yuzli brep da ~20 s oladi, bu yo'l <1 s)."""
    import ifcopenshell.util.placement as up

    items = []
    for rep_ in e.Representation.Representations:
        if rep_.RepresentationIdentifier not in (None, "Body"):
            continue
        for it in rep_.Items:
            if it.is_a() not in FAST_ITEMS:
                return None
            items.append(it)
    if not items:
        return None
    m = np.array(up.get_local_placement(e.ObjectPlacement), dtype=float)
    vs, fs, off = [], [], 0
    for it in items:
        vf = _item_mesh(it, scale)
        if vf is None:
            return None
        v, f = vf
        vs.append(v @ m[:3, :3].T + m[:3, 3] * scale)
        fs.append(f + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


# ---------- QTO ----------


def mesh_volume(m: Mesh) -> float:
    a, b, c = m.verts[m.faces[:, 0]], m.verts[m.faces[:, 1]], m.verts[m.faces[:, 2]]
    return abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


def mesh_area(m: Mesh) -> float:
    a, b, c = m.verts[m.faces[:, 0]], m.verts[m.faces[:, 1]], m.verts[m.faces[:, 2]]
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


def footprint_area(m: Mesh) -> float:
    """XY tekislikka proyeksiya maydoni (taxminan: pastga qaragan uchburchaklar yig'indisi)."""
    a, b, c = m.verts[m.faces[:, 0]], m.verts[m.faces[:, 1]], m.verts[m.faces[:, 2]]
    n = np.cross(b - a, c - a)
    down = n[:, 2] < 0
    return float(0.5 * np.abs(n[down, 2]).sum())


def compute_qto(path: Path) -> dict:
    """Har element: hajm m³, sirt m², asos maydoni m², o'lchamlar (L×W×H, bbox); IFC dagi
    BaseQuantities bo'lsa ular ham. Jamlanma: tur bo'yicha va qavat bo'yicha."""
    import ifcopenshell
    import ifcopenshell.util.element as uel

    f = ifcopenshell.open(str(path))
    by_guid = {e.GlobalId: e for e in f.by_type("IfcElement")}
    rows = []
    for m in load_meshes(path):
        lo, hi = m.bbox
        dims = sorted((hi - lo).tolist(), reverse=True)
        e = by_guid.get(m.guid)
        ifc_q = {}
        if e is not None:
            for pname, props in uel.get_psets(e, qtos_only=True).items():
                for k, v in props.items():
                    if isinstance(v, int | float):
                        ifc_q[f"{pname}.{k}"] = round(float(v), 4)
        mat = uel.get_material(e) if e is not None else None
        rows.append(
            {
                "guid": m.guid,
                "type": m.ifc_type,
                "name": m.name,
                "storey": m.storey,
                "material": getattr(mat, "Name", "") if mat is not None else "",
                "volume_m3": round(mesh_volume(m), 4),
                "area_m2": round(mesh_area(m), 4),
                "footprint_m2": round(footprint_area(m), 4),
                "length_m": round(dims[0], 3),
                "width_m": round(dims[1], 3),
                "height_m": round(float(hi[2] - lo[2]), 3),
                "bbox": [lo.round(3).tolist(), hi.round(3).tolist()],
                "ifc_quantities": ifc_q,
            }
        )
    by_type: dict[str, dict] = {}
    by_storey: dict[str, dict] = {}
    for r in rows:
        for key, bucket in ((r["type"], by_type), (r["storey"] or "—", by_storey)):
            b = bucket.setdefault(key, {"count": 0, "volume_m3": 0.0, "area_m2": 0.0})
            b["count"] += 1
            b["volume_m3"] = round(b["volume_m3"] + r["volume_m3"], 3)
            b["area_m2"] = round(b["area_m2"] + r["area_m2"], 3)
    return {
        "element_count": len(rows),
        "total_volume_m3": round(sum(r["volume_m3"] for r in rows), 3),
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1]["volume_m3"])),
        "by_storey": by_storey,
        "elements": rows,
    }


# ---------- Clash ----------


def _tri_tri_intersect(t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """Vektorlashgan uchburchak–uchburchak kesishuvi (Möller 1997, ajratuvchi tekislik testi +
    intervallar). t1, t2: (k,3,3). Qaytaradi: (k,) bool."""
    # eps — sirtga "tegib turgan" (ustma-ust yotgan) uchburchaklar kesishuv emas: faqat haqiqiy
    # kirib borish (bir tomonda ham, ikkinchi tomonda ham uchlari bor) hisoblanadi
    eps = 1e-6
    p1, q1, r1 = t1[:, 0], t1[:, 1], t1[:, 2]
    p2, q2, r2 = t2[:, 0], t2[:, 1], t2[:, 2]
    n2 = np.cross(q2 - p2, r2 - p2)
    n2 /= np.maximum(np.linalg.norm(n2, axis=1, keepdims=True), 1e-12)
    d1 = np.stack([np.einsum("ij,ij->i", n2, x - p2) for x in (p1, q1, r1)], axis=1)
    sep = (d1 > -eps).all(axis=1) | (d1 < eps).all(axis=1)
    n1 = np.cross(q1 - p1, r1 - p1)
    n1 /= np.maximum(np.linalg.norm(n1, axis=1, keepdims=True), 1e-12)
    d2 = np.stack([np.einsum("ij,ij->i", n1, x - p1) for x in (p2, q2, r2)], axis=1)
    sep |= (d2 > -eps).all(axis=1) | (d2 < eps).all(axis=1)
    # Qolganlar uchun: kesishish chizig'i D = n1×n2 bo'ylab intervallar
    res = ~sep
    idx = np.nonzero(res)[0]
    if len(idx) == 0:
        return res
    D = np.cross(n1[idx], n2[idx])
    axis = np.argmax(np.abs(D), axis=1)

    def interval(tri: np.ndarray, dist: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        proj = np.take_along_axis(tri, axis[:, None, None].repeat(3, 1), axis=2)[:, :, 0]
        lo = np.full(len(idx), np.inf)
        hi = np.full(len(idx), -np.inf)
        for i, j in ((0, 1), (1, 2), (2, 0)):
            di, dj = dist[:, i], dist[:, j]
            cross = (di * dj) < 0
            den = np.where(di - dj == 0, eps, di - dj)
            t = proj[:, i] + (proj[:, j] - proj[:, i]) * di / den
            lo = np.where(cross, np.minimum(lo, t), lo)
            hi = np.where(cross, np.maximum(hi, t), hi)
            onplane = np.abs(di) <= eps
            lo = np.where(onplane, np.minimum(lo, proj[:, i]), lo)
            hi = np.where(onplane, np.maximum(hi, proj[:, i]), hi)
        return lo, hi

    a_lo, a_hi = interval(t1[idx], d1[idx])
    b_lo, b_hi = interval(t2[idx], d2[idx])
    ok = (a_lo <= b_hi + eps) & (b_lo <= a_hi + eps) & np.isfinite(a_lo) & np.isfinite(b_lo)
    res[idx] = ok
    return res


def _mesh_pair_intersects(
    a: Mesh, b: Mesh, box_lo: np.ndarray, box_hi: np.ndarray
) -> tuple[bool, list[float] | None, int]:
    """Ikki mesh sirtlari kesishadimi: umumiy AABB ichidagi uchburchaklar, tekis panjara (grid)
    bo'yicha bo'linib, faqat bir katakdagi juftlar tekshiriladi (xotira/vaqt chegaralangan)."""

    def tris_in_box(m: Mesh) -> np.ndarray:
        t = m.verts[m.faces]  # (n,3,3)
        lo, hi = t.min(axis=1), t.max(axis=1)
        keep = (hi >= box_lo - 1e-6).all(axis=1) & (lo <= box_hi + 1e-6).all(axis=1)
        return t[keep]

    ta, tb = tris_in_box(a), tris_in_box(b)
    if len(ta) == 0 or len(tb) == 0:
        return False, None, 0
    # Panjara: katak soni uchburchaklar soniga qarab (har katakda o'nlab uchburchak)
    size = np.maximum(box_hi - box_lo, 1e-6)
    n_cells = int(np.clip(np.cbrt(max(len(ta), len(tb)) / 8), 1, 48))
    cell = size / n_cells

    def cells_of(t: np.ndarray) -> dict[int, np.ndarray]:
        lo = np.clip(((t.min(axis=1) - box_lo) / cell).astype(int), 0, n_cells - 1)
        hi = np.clip(((t.max(axis=1) - box_lo) / cell).astype(int), 0, n_cells - 1)
        out: dict[int, list[int]] = {}
        for i in range(len(t)):
            for x in range(lo[i, 0], hi[i, 0] + 1):
                for y in range(lo[i, 1], hi[i, 1] + 1):
                    for z in range(lo[i, 2], hi[i, 2] + 1):
                        out.setdefault((x * n_cells + y) * n_cells + z, []).append(i)
        return {k: np.array(v) for k, v in out.items()}

    ca, cb = cells_of(ta), cells_of(tb)
    pairs_a, pairs_b, total = [], [], 0
    for k, ia in ca.items():
        ib = cb.get(k)
        if ib is None:
            continue
        total += len(ia) * len(ib)
        if total > CLASH_EXACT_MAX_TRIANGLE_PAIRS:
            return False, None, -1  # juda katta — aniq tekshirilmadi
        g1, g2 = np.meshgrid(ia, ib, indexing="ij")
        pairs_a.append(g1.ravel())
        pairs_b.append(g2.ravel())
    if not pairs_a:
        return False, None, 0
    ia, ib = np.concatenate(pairs_a), np.concatenate(pairs_b)
    uniq = np.unique(ia * len(tb) + ib)  # bir juft bir necha katakda takrorlanadi
    ia, ib = uniq // len(tb), uniq % len(tb)
    alo, ahi = ta.min(axis=1), ta.max(axis=1)
    blo, bhi = tb.min(axis=1), tb.max(axis=1)
    cand = (ahi[ia] >= blo[ib]).all(axis=1) & (alo[ia] <= bhi[ib]).all(axis=1)
    ia, ib = ia[cand], ib[cand]
    hits_a, hits_b = [], []
    for s0 in range(0, len(ia), 200_000):  # bo'laklab — xotira
        sl = slice(s0, s0 + 200_000)
        hit = _tri_tri_intersect(ta[ia[sl]], tb[ib[sl]])
        hits_a.append(ia[sl][hit])
        hits_b.append(ib[sl][hit])
    ha = np.concatenate(hits_a) if hits_a else np.array([], dtype=int)
    hb = np.concatenate(hits_b) if hits_b else np.array([], dtype=int)
    n = int(len(ha))
    if n == 0:
        return False, None, 0
    pts = (ta[ha].mean(axis=1) + tb[hb].mean(axis=1)) / 2
    return True, pts.mean(axis=0).round(3).tolist(), n


def compute_clashes(
    path: Path,
    tolerance: float = 0.0,
    types_a: list[str] | None = None,
    types_b: list[str] | None = None,
) -> dict:
    """To'qnashuvlar: AABB (tolerance bilan) → uchburchak kesishuvi. Natija: hard (sirtlar
    kesishadi — haqiqiy to'qnashuv), possible (bbox lar kirib boradi, sirt kesishuvi topilmadi —
    ichma-ich yoki juda katta juftlik), touch (faqat tegib turadi — odatda normal)."""
    meshes = load_meshes(path)
    exact = len(meshes) <= CLASH_EXACT_MAX_ELEMENTS
    boxes = [m.bbox for m in meshes]

    def wanted(a: Mesh, b: Mesh) -> bool:
        if not types_a and not types_b:
            return True

        def in_a(m: Mesh) -> bool:
            return not types_a or m.ifc_type in types_a

        def in_b(m: Mesh) -> bool:
            return not types_b or m.ifc_type in types_b

        return (in_a(a) and in_b(b)) or (in_a(b) and in_b(a))

    clashes = []
    checked = 0
    for i in range(len(meshes)):
        a = meshes[i]
        alo, ahi = boxes[i]
        for j in range(i + 1, len(meshes)):
            b = meshes[j]
            if not wanted(a, b):
                continue
            blo, bhi = boxes[j]
            if (alo > bhi + tolerance).any() or (blo > ahi + tolerance).any():
                continue
            checked += 1
            lo, hi = np.maximum(alo, blo) - tolerance, np.minimum(ahi, bhi) + tolerance
            overlap = np.clip(hi - lo, 0, None)
            # touch — bbox lar faqat tegib turadi (kirib borish yo'q); possible — kirib boradi,
            # lekin sirt kesishuvi topilmadi (ichma-ich yoki aniq tekshirilmadi)
            kind = "touch" if (overlap <= 1e-6).any() else "possible"
            point, n = ((lo + hi) / 2).round(3).tolist(), 0
            if exact and kind != "touch":
                hit, pt, n = _mesh_pair_intersects(a, b, lo, hi)
                if hit:
                    kind, point = "hard", pt
            clashes.append(
                {
                    "kind": kind,
                    "a": {"guid": a.guid, "type": a.ifc_type, "name": a.name},
                    "b": {"guid": b.guid, "type": b.ifc_type, "name": b.name},
                    "point": point,
                    "overlap_m": overlap.round(3).tolist(),
                    "overlap_volume_m3": round(float(np.prod(overlap)), 4),
                    "triangle_hits": max(n, 0),
                }
            )
    order = {"hard": 0, "possible": 1, "touch": 2}
    clashes.sort(key=lambda c: (order[c["kind"]], -c["overlap_volume_m3"]))
    return {
        "element_count": len(meshes),
        "pairs_checked": checked,
        "exact": exact,
        "tolerance": tolerance,
        "hard": sum(1 for c in clashes if c["kind"] == "hard"),
        "possible": sum(1 for c in clashes if c["kind"] == "possible"),
        "touch": sum(1 for c in clashes if c["kind"] == "touch"),
        "clashes": clashes,
    }


def cached(sha: str, kind: str, compute) -> dict:
    """Diskdagi kesh (data/derived); parallel so'rovlar bir xil hisobni ikki marta qilmasin."""
    p = _derived_path(sha, kind)
    with _lock(f"{sha}:{kind}"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        result = compute()
        p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result


def precompute(path: Path, sha: str) -> None:
    """Yuklashdan keyin fonda: QTO va to'qnashuvlar tayyor tursin (birinchi ochilishda kutilmasin)."""
    try:
        cached(sha, "qto", lambda: compute_qto(path))
        cached(sha, "clash", lambda: compute_clashes(path))
    except Exception:  # noqa: BLE001 — fon hisob API ni buzmasin
        log.exception("geometriya oldindan hisoblash xatosi: %s", path)


def write_stl(path: Path, guids: list[str], out: Path) -> dict:
    """Tanlangan elementlarni bitta ASCII STL ga yozadi (metr, dunyo koordinatalari) — CFD uchun.
    Qaytaradi: {"bbox": [lo, hi], "triangles": n, "elements": [...]}"""
    meshes = [m for m in load_meshes(path) if m.guid in set(guids)]
    if not meshes:
        raise ValueError("Tanlangan elementlarda geometriya yo'q")
    out.parent.mkdir(parents=True, exist_ok=True)
    lo = np.min([m.bbox[0] for m in meshes], axis=0)
    hi = np.max([m.bbox[1] for m in meshes], axis=0)
    n = 0
    with open(out, "w", encoding="ascii", newline="\n") as fh:
        fh.write("solid body\n")
        for m in meshes:
            t = m.verts[m.faces]
            nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            for tri, nv in zip(t, nrm, strict=False):
                fh.write(f"facet normal {nv[0]:.6g} {nv[1]:.6g} {nv[2]:.6g}\n outer loop\n")
                for v in tri:
                    fh.write(f"  vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                fh.write(" endloop\nendfacet\n")
                n += 1
        fh.write("endsolid body\n")
    return {
        "bbox": [lo.round(4).tolist(), hi.round(4).tolist()],
        "triangles": n,
        "elements": [{"guid": m.guid, "name": m.name, "type": m.ifc_type} for m in meshes],
    }
