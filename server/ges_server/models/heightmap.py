"""Model «yer yuzasi» balandlik xaritasi: barcha elementlarning (relyef, to'g'on, binolar) ustki yuzasi
panjaraga rasterlanadi (z-bufer, eng baland). Web 3D suv yuzasini shu xaritaga **moslashtiradi**: suv faqat
sathdan past joylarni to'ldiradi (ombor qirg'og'i tabiiy, to'g'on to'sadi, quyi byef toshqini relyef bo'ylab) —
Blender «shrinkwrap» kabi. Natija sha bo'yicha keshlanadi (data/derived/<sha>.hm<nx>.json)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..config import get_settings
from . import geometry


def _rasterize(
    verts: np.ndarray, faces: np.ndarray, x0, y0, dx, dy, nx, ny, zbuf: np.ndarray
) -> None:
    tri = verts[faces]  # (m, 3, 3)
    for a, b, c in tri:
        xs = (a[0], b[0], c[0])
        ys = (a[1], b[1], c[1])
        i0 = max(int((min(xs) - x0) / dx), 0)
        i1 = min(int((max(xs) - x0) / dx) + 1, nx - 1)
        j0 = max(int((min(ys) - y0) / dy), 0)
        j1 = min(int((max(ys) - y0) / dy) + 1, ny - 1)
        if i1 < i0 or j1 < j0:
            continue
        gx = x0 + (np.arange(i0, i1 + 1) + 0.5) * dx
        gy = y0 + (np.arange(j0, j1 + 1) + 0.5) * dy
        X, Y = np.meshgrid(gx, gy)
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / det
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / det
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not inside.any():
            continue
        z = l1 * a[2] + l2 * b[2] + l3 * c[2]
        sub = zbuf[j0 : j1 + 1, i0 : i1 + 1]
        np.maximum(sub, np.where(inside, z, -np.inf), out=sub)


def compute(path: Path, nx: int = 160, ny: int = 160) -> dict:
    meshes = geometry._load_meshes(path)
    if not meshes:
        raise ValueError("Modelda geometriya yo'q")
    allv = np.vstack([m.verts for m in meshes])
    x0, y0 = float(allv[:, 0].min()), float(allv[:, 1].min())
    x1, y1 = float(allv[:, 0].max()), float(allv[:, 1].max())
    # kvadrat kataklar: uzun tomon `nx` katak, qisqa tomon proporsional (suv gidrodinamikasi izotrop bo'lsin)
    wx, wy = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    cell = max(wx, wy) / max(nx, ny)
    nx = max(8, int(round(wx / cell)))
    ny = max(8, int(round(wy / cell)))
    dx = wx / nx
    dy = wy / ny
    zbuf = np.full((ny, nx), -np.inf)
    for m in meshes:
        _rasterize(m.verts, m.faces, x0, y0, dx, dy, nx, ny, zbuf)
    zmin = float(allv[:, 2].min())
    z = np.where(np.isfinite(zbuf), zbuf, np.nan)
    # bo'sh kataklar (geometriya yo'q) — eng past belgi minus 1 (suv «yerdan pastda» bo'lmasin uchun)
    z = np.where(np.isnan(z), zmin - 1.0, z)
    return {
        "x0": x0,
        "y0": y0,
        "dx": dx,
        "dy": dy,
        "nx": nx,
        "ny": ny,
        "z_min": zmin,
        "z_max": float(np.nanmax(z)),
        "z": [round(float(v), 2) for v in z.ravel()],  # qator-qator (y bo'yicha), har qatorda nx
    }


def cached(path: Path, sha: str, nx: int = 160) -> dict:
    d = get_settings().data_dir / "derived"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{sha}.hm{nx}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    hm = compute(path, nx, nx)
    try:
        f.write_text(json.dumps(hm), encoding="utf-8")
    except OSError:
        pass
    return hm
