"""IFC geometriya tahlili (IfcOpenShell): hajm-miqdor hisobi (QTO) va to'qnashuvlar (clash).

Natijalar fayl sha256 bo'yicha keshlanadi: data/derived/<sha>.qto.json, <sha>.clash.json —
bir xil fayl uchun qayta hisoblanmaydi.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import get_settings
from .keylocks import KeyLocks

log = logging.getLogger("ges_server.geometry")

# Element juftligi uchun uchburchak juftlari chegarasi (xotira/vaqt): oshsa juftlik «possible» (aniq tekshirilmadi)
CLASH_EXACT_MAX_TRIANGLE_PAIRS = 4_000_000
# G5: keng bosqich (broad phase) — element AABB lari bir xil panjara (grid) indeksida; O(n²) o'rniga faqat
# bir katakdagi juftliklar tekshiriladi, shuning uchun katta modellarda ham aniq (uchburchak) tekshiruv ishlaydi
CLASH_GRID_TARGET_PER_CELL = 8


@dataclass
class Mesh:
    guid: str
    ifc_type: str
    name: str
    storey: str
    verts: np.ndarray  # (n,3) metr, dunyo koordinatalari
    faces: np.ndarray  # (m,3)
    group: str = ""  # G5: federatsiyada model nomi/identifikatori (bir modelning ichki juftliklarini ajratish uchun)

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.verts.min(axis=0), self.verts.max(axis=0)


def _derived_path(sha: str, kind: str) -> Path:
    d = get_settings().data_dir / "derived"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha}.{kind}.json"


_MESH_CACHE: dict[str, list[Mesh]] = {}
# OPS-04: kalit bo'yicha qulflar chegaralangan (ilgari har noyob clash parametri uchun abadiy qulf)
_LOCKS = KeyLocks(256)


def _lock(key: str):
    return _LOCKS.get(key)


# --------------------------------------------------------------------------- OPS-04: clash turlari whitelist

_IFC_NAME = re.compile(r"^Ifc[A-Za-z0-9]+$")
MAX_TYPES = 30


@functools.lru_cache(maxsize=1)
def _ifc_classes() -> dict[str, str]:
    """Ma'lum IFC entity nomlari (IFC2X3, IFC4, IFC4X3*): kichik harf → kanonik nom."""
    import ifcopenshell.ifcopenshell_wrapper as w

    out: dict[str, str] = {}
    for schema in ("IFC2X3", "IFC4", "IFC4X3", "IFC4X3_ADD2"):
        try:
            sc = w.schema_by_name(schema)
        except Exception:  # noqa: BLE001 — eski ifcopenshell da sxema bo'lmasligi mumkin
            continue
        for d in sc.declarations():
            if isinstance(d, w.entity):
                out.setdefault(d.name().lower(), d.name())
    return out


def normalize_types(raw: str | None) -> list[str] | None:
    """`types_a`/`types_b` query: vergul bilan IFC klass nomlari → kanonik, takrorsiz, saralangan ro'yxat
    (None — cheklov yo'q). Noto'g'ri nom (`/`, bo'shliq, noma'lum klass) → ValueError (API 422)."""
    items = [t.strip() for t in (raw or "").split(",") if t.strip()]
    if not items:
        return None
    if len(items) > MAX_TYPES:
        raise ValueError(f"Ko'pi bilan {MAX_TYPES} ta IFC turi")
    known = _ifc_classes()
    out = set()
    for t in items:
        if not _IFC_NAME.fullmatch(t) or t.lower() not in known:
            raise ValueError(f"Noma'lum IFC turi: {t[:64]!r} (masalan IfcWall, IfcPipeSegment)")
        out.add(known[t.lower()])
    return sorted(out)


def clash_kind(types_a: list[str] | None, types_b: list[str] | None) -> str:
    """Kesh nomi: cheklovsiz — "clash"; aks holda "clash-<sha256(normallashtirilgan parametrlar)[:32]>"
    (ilgari query satri to'g'ridan-to'g'ri fayl nomiga tushardi — `/` bilan 500, cheksiz kalitlar)."""
    if not types_a and not types_b:
        return "clash"
    key = json.dumps({"a": types_a or [], "b": types_b or []}, sort_keys=True, separators=(",", ":"))
    return "clash-" + hashlib.sha256(key.encode()).hexdigest()[:32]


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


def candidate_pairs(boxes: list[tuple[np.ndarray, np.ndarray]], tolerance: float = 0.0) -> np.ndarray:
    """Keng bosqich (G5): AABB larni bir xil panjaraga (katak o'lchami — median box + tolerance) joylab,
    bir katakda uchrashgan juftliklar (i<j) qaytariladi; kichik ro'yxatda to'g'ridan-to'g'ri O(n²)."""
    n = len(boxes)
    if n < 2:
        return np.empty((0, 2), dtype=int)
    lo = np.array([b[0] for b in boxes]) - tolerance
    hi = np.array([b[1] for b in boxes]) + tolerance
    if n <= 64:
        ii, jj = np.triu_indices(n, 1)
        ok = (lo[ii] <= hi[jj]).all(axis=1) & (lo[jj] <= hi[ii]).all(axis=1)
        return np.stack([ii[ok], jj[ok]], axis=1)
    size = np.maximum(np.median(hi - lo, axis=0), 1e-3) * 2
    origin = lo.min(axis=0)
    cells_lo = np.floor((lo - origin) / size).astype(np.int64)
    cells_hi = np.floor((hi - origin) / size).astype(np.int64)
    # katta elementlar ko'p katakni egallaydi — chegara: element boshiga 4096 katak (aks holda 1 katakli "katta" qatlam)
    span = np.prod(cells_hi - cells_lo + 1, axis=1)
    big = span > 4096
    buckets: dict[tuple, list[int]] = {}
    for i in np.nonzero(~big)[0]:
        for x in range(cells_lo[i, 0], cells_hi[i, 0] + 1):
            for y in range(cells_lo[i, 1], cells_hi[i, 1] + 1):
                for z in range(cells_lo[i, 2], cells_hi[i, 2] + 1):
                    buckets.setdefault((x, y, z), []).append(int(i))
    pairs: set[tuple[int, int]] = set()
    for idx in buckets.values():
        if len(idx) < 2:
            continue
        arr = np.array(idx)
        ii, jj = np.triu_indices(len(arr), 1)
        a, b = arr[ii], arr[jj]
        ok = (lo[a] <= hi[b]).all(axis=1) & (lo[b] <= hi[a]).all(axis=1)
        for p, q in zip(a[ok], b[ok], strict=True):
            pairs.add((int(min(p, q)), int(max(p, q))))
    bigs = np.nonzero(big)[0]
    for i in bigs:  # katta elementlar hamma bilan bbox bo'yicha
        ok = (lo[i] <= hi).all(axis=1) & (lo <= hi[i]).all(axis=1)
        for j in np.nonzero(ok)[0]:
            if j != i:
                pairs.add((int(min(i, j)), int(max(i, j))))
    if not pairs:
        return np.empty((0, 2), dtype=int)
    return np.array(sorted(pairs), dtype=int)


def compute_clashes(
    path: Path,
    tolerance: float = 0.0,
    types_a: list[str] | None = None,
    types_b: list[str] | None = None,
) -> dict:
    """To'qnashuvlar: AABB (tolerance bilan) → uchburchak kesishuvi. Natija: hard (sirtlar
    kesishadi — haqiqiy to'qnashuv), possible (bbox lar kirib boradi, sirt kesishuvi topilmadi —
    ichma-ich yoki juda katta juftlik), touch (faqat tegib turadi — odatda normal)."""
    return clashes_of(load_meshes(path), tolerance, types_a, types_b)


def clashes_of(
    meshes: list[Mesh],
    tolerance: float = 0.0,
    types_a: list[str] | None = None,
    types_b: list[str] | None = None,
    cross_groups_only: bool = False,
) -> dict:
    """Mesh ro'yxati ustida (bitta model yoki federatsiya, G5). `cross_groups_only` — faqat turli
    modellar (group) orasidagi juftliklar. Keng bosqich panjara indeksi bilan — element soni cheklanmaydi."""
    exact = True
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
    for i, j in candidate_pairs(boxes, tolerance):
        a, b = meshes[i], meshes[j]
        if cross_groups_only and a.group == b.group:
            continue
        if not wanted(a, b):
            continue
        alo, ahi = boxes[i]
        blo, bhi = boxes[j]
        checked += 1
        lo, hi = np.maximum(alo, blo) - tolerance, np.minimum(ahi, bhi) + tolerance
        overlap = np.clip(hi - lo, 0, None)
        # touch — bbox lar faqat tegib turadi (kirib borish yo'q); possible — kirib boradi,
        # lekin sirt kesishuvi topilmadi (ichma-ich yoki aniq tekshirilmadi)
        kind = "touch" if (overlap <= 1e-6).any() else "possible"
        point, n = ((lo + hi) / 2).round(3).tolist(), 0
        if kind != "touch":
            hit, pt, n = _mesh_pair_intersects(a, b, lo, hi)
            if hit:
                kind, point = "hard", pt
            elif n < 0:
                exact = False  # kamida bitta juftlik chegaradan katta — aniq tekshirilmadi
        clashes.append(
            {
                "kind": kind,
                "a": {"guid": a.guid, "type": a.ifc_type, "name": a.name, **({"model": a.group} if a.group else {})},
                "b": {"guid": b.guid, "type": b.ifc_type, "name": b.name, **({"model": b.group} if b.group else {})},
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


def transformed(meshes: list[Mesh], dx: float, dy: float, dz: float, rot_deg: float, group: str) -> list[Mesh]:
    """G5 federatsiya: mesh larni Z o'qi atrofida burib va siljitib nusxalaydi (guruh belgisi bilan)."""
    th = np.radians(rot_deg)
    R = np.array([[np.cos(th), -np.sin(th), 0.0], [np.sin(th), np.cos(th), 0.0], [0.0, 0.0, 1.0]])
    off = np.array([dx, dy, dz], dtype=float)
    return [Mesh(m.guid, m.ifc_type, m.name, m.storey, (m.verts @ R.T) + off, m.faces, group) for m in meshes]


def peek(sha: str, kind: str) -> dict | None:
    """Keshlangan natija (hisoblamasdan); yo'q yoki buzilgan bo'lsa None."""
    p = _derived_path(sha, kind)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cached(sha: str, kind: str, compute) -> dict:
    """Diskdagi kesh (data/derived); parallel so'rovlar bir xil hisobni ikki marta qilmasin. Yozish atomik
    (noyob temp + os.replace) — jarayonlar orasida ham yarim yozilgan JSON o'qilmaydi."""
    p = _derived_path(sha, kind)
    with _lock(f"{sha}:{kind}"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        result = compute()
        fd, tmp = tempfile.mkstemp(prefix=f"{sha}.", suffix=".json.part", dir=p.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False)
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
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
