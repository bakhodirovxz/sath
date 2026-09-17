"""Rasmdan raqamli egizak: skanerlangan chizma / balandlik xaritasi → 3D elementlar (drafts.build formati).

Rejimlar:
  * drawing  — plan/kesim rasmi (PNG/JPG/TIFF, skaner yoki foto): OpenCV bilan siyoh maskasi (adaptiv chegara),
               konturlar → yopiq ko'pburchaklar (teshiklari bilan) → `extrude_m` balandlikka ko'tariladi (devorlar,
               to'g'on konturi); ochiq/ingichka chiziqlar yupqa lenta. Masshtab: rasm kengligi metrda (width_m)
               yoki m/px. Katta konturlar alohida element (nomi: «Kontur 1…»), mayda shovqin tashlanadi.
  * heightmap — balandlik xaritasi (DEM PNG/TIFF kulrang, sun'iy yo'ldosh relyef): piksel yorug'ligi → balandlik
               z_min..z_max, panjara ≤ grid×grid → relyef yuzasi (IfcSite geometriyasi «Relyef»).
  * photo     — oddiy foto: qorong'i/och joylar bo'yicha taxminiy relyef (heightmap kabi, Gauss silliqlash) —
               aniq emas, faqat ko'rgazma; aniq model uchun ko'p foto → fotogrammetriya (Meshroom/COLMAP, tashqi).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_SIDE = 2000


def _read_gray(path: Path) -> np.ndarray:
    import cv2

    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Rasmni o'qib bo'lmadi (PNG/JPG/TIFF kutilgan)")
    if img.ndim == 3:
        if img.shape[2] == 4:  # alfa → oq fon
            a = img[:, :, 3:4] / 255.0
            img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        lo, hi = float(img.min()), float(img.max())
        img = ((img - lo) / max(hi - lo, 1e-9) * 255).astype(np.uint8)
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img


def _ink_mask(gray: np.ndarray, invert: bool = False, block: int = 35) -> np.ndarray:
    """Siyoh (qora chiziqlar) maskasi — adaptiv chegara (yoritish notekis skanlarda ham)."""
    import cv2

    g = cv2.GaussianBlur(gray, (3, 3), 0)
    mask = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block | 1, 12
    )
    if invert:
        mask = 255 - mask
    # mayda shovqinni tozalash
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return mask


def vectorize_drawing(
    path: Path,
    width_m: float | None = None,
    m_per_px: float | None = None,
    extrude_m: float = 3.0,
    min_area_px: int = 40,
    invert: bool = False,
    simplify_px: float = 1.5,
    max_objects: int = 400,
) -> list[dict]:
    """Chizma rasmi → [{name, kind, ifc_class, mesh:{vertices, faces}, transform, psets, color}] (metrda)."""
    import cv2
    import trimesh
    from shapely.geometry import Polygon
    from shapely.validation import make_valid

    gray = _read_gray(path)
    h, w = gray.shape
    scale = m_per_px or ((width_m or 100.0) / w)
    mask = _ink_mask(gray, invert)
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        raise ValueError("Rasmda chiziqlar topilmadi (kontrastni oshiring yoki «invert»)")
    hier = hier[0]
    out: list[dict] = []
    ink_pct = float(mask.mean() / 255 * 100)
    # tashqi konturlar (parent == -1) va ularning teshiklari
    items = []
    for i, c in enumerate(contours):
        if hier[i][3] != -1:
            continue
        area = cv2.contourArea(c)
        if area < min_area_px:
            continue
        items.append((area, i))
    items.sort(reverse=True)
    for _area, i in items[:max_objects]:
        c = cv2.approxPolyDP(contours[i], simplify_px, True).reshape(-1, 2)
        if len(c) < 3:
            continue
        holes = []
        j = hier[i][2]  # birinchi bola (teshik)
        while j != -1:
            hc = cv2.approxPolyDP(contours[j], simplify_px, True).reshape(-1, 2)
            if len(hc) >= 3 and cv2.contourArea(contours[j]) >= min_area_px:
                holes.append([(float(x) * scale, float(h - y) * scale) for x, y in hc])
            j = hier[j][0]
        ring = [(float(x) * scale, float(h - y) * scale) for x, y in c]
        try:
            poly = make_valid(Polygon(ring, holes=holes))
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            elif poly.geom_type != "Polygon":
                continue
            if poly.area < (min_area_px * scale * scale):
                continue
            mesh = trimesh.creation.extrude_polygon(poly, max(extrude_m, 0.01))
        except Exception:  # noqa: BLE001 — bitta buzuq kontur importni to'xtatmasin
            continue
        v = np.asarray(mesh.vertices, dtype=float)
        f = np.asarray(mesh.faces, dtype=int)
        ctr = v.mean(axis=0)
        n = len(out) + 1
        out.append(
            {
                "kind": "wall",
                "name": f"Kontur {n}",
                "ifc_class": "IfcWall",
                "color": (0.75, 0.72, 0.65),
                "transform": {
                    "x": float(ctr[0]),
                    "y": float(ctr[1]),
                    "z": float(ctr[2]),
                    "rz": 0.0,
                },
                "psets": {
                    "Pset_GES_Import": {
                        "Manba": "rasm (chizma)",
                        "Maydon_m2": round(float(poly.area), 2),
                        "Balandlik_m": extrude_m,
                        "Masshtab_m_px": round(scale, 5),
                    }
                },
                "mesh": {"vertices": (v - ctr).tolist(), "faces": f.tolist()},
            }
        )
    if not out:
        raise ValueError(
            f"Rasmdan kontur chiqmadi (siyoh {ink_pct:.1f} %). Kontrastni oshiring, «invert» ni sinang yoki "
            "minimal maydonni kamaytiring"
        )
    return out


def heightmap_terrain(
    path: Path,
    width_m: float = 1000.0,
    z_min: float = 0.0,
    z_max: float = 100.0,
    grid: int = 160,
    smooth: int = 0,
    invert: bool = False,
    name: str = "Relyef",
) -> list[dict]:
    """Balandlik xaritasi / foto → relyef yuzasi (bitta element, IfcSite geometriyasi sifatida keyin joylanadi)."""
    import cv2

    gray = _read_gray(path).astype(np.float32)
    if smooth > 0:
        k = smooth * 2 + 1
        gray = cv2.GaussianBlur(gray, (k, k), 0)
    if invert:
        gray = 255 - gray
    h, w = gray.shape
    n = max(grid, 8)
    nx = n if w >= h else max(int(n * w / h), 8)
    ny = n if h > w else max(int(n * h / w), 8)
    small = cv2.resize(gray, (nx, ny), interpolation=cv2.INTER_AREA)
    lo, hi = float(small.min()), float(small.max())
    z = z_min + (small - lo) / max(hi - lo, 1e-9) * (z_max - z_min)
    scale = width_m / w
    xs = np.arange(nx) * (w / (nx - 1)) * scale
    ys = (h - np.arange(ny) * (h / (ny - 1))) * scale
    X, Y = np.meshgrid(xs, ys)
    V = np.column_stack([X.ravel(), Y.ravel(), z.ravel()])
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = a + 1
            c = a + nx
            d = c + 1
            faces.append([a, c, b])
            faces.append([b, c, d])
    F = np.asarray(faces, dtype=int)
    ctr = V.mean(axis=0)
    return [
        {
            "kind": "site",
            "name": name,
            "ifc_class": "IfcGeographicElement",
            "color": (0.45, 0.55, 0.35),
            "transform": {"x": float(ctr[0]), "y": float(ctr[1]), "z": float(ctr[2]), "rz": 0.0},
            "psets": {
                "Pset_GES_Import": {
                    "Manba": "rasm (balandlik xaritasi)",
                    "Kenglik_m": width_m,
                    "Z_min": z_min,
                    "Z_max": z_max,
                    "Panjara": f"{nx}×{ny}",
                }
            },
            "mesh": {"vertices": (V - ctr).tolist(), "faces": F.tolist()},
        }
    ]


def load_image(path: Path, mode: str, **kw) -> list[dict]:
    if mode == "drawing":
        return vectorize_drawing(
            path,
            width_m=kw.get("width_m"),
            m_per_px=kw.get("m_per_px"),
            extrude_m=kw.get("extrude_m", 3.0),
            min_area_px=int(kw.get("min_area_px", 40)),
            invert=bool(kw.get("invert", False)),
        )
    if mode in ("heightmap", "photo"):
        return heightmap_terrain(
            path,
            width_m=kw.get("width_m") or 1000.0,
            z_min=kw.get("z_min", 0.0),
            z_max=kw.get("z_max", 100.0),
            grid=int(kw.get("grid", 160)),
            smooth=int(kw.get("smooth", 3 if mode == "photo" else 0)),
            invert=bool(kw.get("invert", False)),
        )
    raise ValueError(f"Noma'lum rejim: {mode}")
