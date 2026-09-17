"""Haqiqiy relyef (DEM) — AWS Terrain Tiles (Mapzen «terrarium», SRTM/ASTER/… asosida, ochiq, kalitsiz):
https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png, balandlik = R·256 + G + B/256 − 32768 (m).
Berilgan markaz (lat, lon), maydon (kenglik × uzunlik, m), burilish (X o'qi — to'g'on gerbi yo'nalishi) bo'yicha
panjara namuna olinadi (bilinear) → relyef yuzasi (IfcGeographicElement «Relyef (DEM)»), z — mutlaq balandlik.
Zoom 12 ≈ 38 m/px (ekvatorda; 41° da ≈ 29 m), zoom 13 ≈ 15 m. Plitkalar data_dir/dem da keshlanadi."""

from __future__ import annotations

import io
import math
import urllib.request

import numpy as np

from ..config import get_settings

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = "Sath/1.0 (ichki BIM; relyef import)"


def _tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2**z
    x = (lon + 180) / 360 * n
    y = (
        (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi)
        / 2
        * n
    )
    return x, y


def _tile(z: int, x: int, y: int) -> np.ndarray:
    cache = get_settings().data_dir / "dem" / str(z) / str(x)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{y}.png"
    if not f.exists():
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — sobit ochiq manba
            f.write_bytes(r.read())
    from PIL import Image

    with Image.open(io.BytesIO(f.read_bytes())) as im:
        a = np.asarray(im.convert("RGB")).astype(float)
    return a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256 - 32768


def fetch_grid(
    lat: float,
    lon: float,
    width_m: float,
    height_m: float,
    rotation_deg: float = 0.0,
    zoom: int = 12,
    nx: int = 120,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """→ (vertices N×3 lokal metr (x — burilgan o'q, y — unga perpendikulyar, z mutlaq), faces M×3, info)."""
    zoom = max(8, min(14, int(zoom)))
    nx = max(8, min(400, int(nx)))
    ny = max(8, min(400, int(round(nx * height_m / width_m))))
    # lokal metr → lat/lon: 1° kenglik ≈ 111 320 m, 1° uzunlik ≈ 111 320·cos(lat)
    m_lat = 111_320.0
    m_lon = 111_320.0 * math.cos(math.radians(lat))
    a = math.radians(rotation_deg)
    xs = np.linspace(-width_m / 2, width_m / 2, nx)
    ys = np.linspace(-height_m / 2, height_m / 2, ny)
    X, Y = np.meshgrid(xs, ys)
    E = X * math.cos(a) - Y * math.sin(a)  # sharq (m)
    N = X * math.sin(a) + Y * math.cos(a)  # shimol (m)
    LAT = lat + N / m_lat
    LON = lon + E / m_lon
    # plitka piksel koordinatalari
    n = 2**zoom
    PX = (LON + 180) / 360 * n * 256
    LATR = np.radians(LAT)
    PY = (1 - np.log(np.tan(LATR) + 1 / np.cos(LATR)) / math.pi) / 2 * n * 256
    tx0, tx1 = int(PX.min() // 256), int(PX.max() // 256)
    ty0, ty1 = int(PY.min() // 256), int(PY.max() // 256)
    if (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 64:
        raise ValueError(
            "Maydon juda katta (64 plitkadan ko'p) — zoom ni kamaytiring yoki maydonni kichraytiring"
        )
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            mosaic[
                (ty - ty0) * 256 : (ty - ty0 + 1) * 256, (tx - tx0) * 256 : (tx - tx0 + 1) * 256
            ] = _tile(zoom, tx, ty)
    # bilinear namuna
    fx = PX - tx0 * 256 - 0.5
    fy = PY - ty0 * 256 - 0.5
    i0 = np.clip(np.floor(fx).astype(int), 0, mosaic.shape[1] - 2)
    j0 = np.clip(np.floor(fy).astype(int), 0, mosaic.shape[0] - 2)
    tx_ = np.clip(fx - i0, 0, 1)
    ty_ = np.clip(fy - j0, 0, 1)
    Z = (mosaic[j0, i0] * (1 - tx_) + mosaic[j0, i0 + 1] * tx_) * (1 - ty_) + (
        mosaic[j0 + 1, i0] * (1 - tx_) + mosaic[j0 + 1, i0 + 1] * tx_
    ) * ty_
    V = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            k = j * nx + i
            F.append([k, k + 1, k + nx])
            F.append([k + 1, k + nx + 1, k + nx])
    info = {
        "zoom": zoom,
        "nx": nx,
        "ny": ny,
        "m_per_px": 40075016.686 * math.cos(math.radians(lat)) / (256 * n),
        "z_min": float(Z.min()),
        "z_max": float(Z.max()),
        "tiles": (tx1 - tx0 + 1) * (ty1 - ty0 + 1),
        "source": "AWS Terrain Tiles (Mapzen terrarium: SRTM/ASTER/GMTED/…)",
    }
    return V, np.asarray(F), info


def terrain_object(
    lat, lon, width_m, height_m, rotation_deg=0.0, zoom=12, nx=120, name="Relyef (DEM)"
) -> tuple[dict, dict]:
    V, F, info = fetch_grid(lat, lon, width_m, height_m, rotation_deg, zoom, nx)
    ctr = V.mean(axis=0)
    obj = {
        "kind": "site",
        "name": name,
        "ifc_class": "IfcGeographicElement",
        "color": (0.44, 0.52, 0.34),
        "transform": {"x": float(ctr[0]), "y": float(ctr[1]), "z": float(ctr[2]), "rz": 0.0},
        "psets": {
            "Pset_GES_Site": {
                "Manba": info["source"],
                "Lat": lat,
                "Lon": lon,
                "Kenglik_m": width_m,
                "Uzunlik_m": height_m,
                "Burilish_deg": rotation_deg,
                "Zoom": zoom,
                "Piksel_m": round(info["m_per_px"], 1),
                "Z_min": round(info["z_min"], 1),
                "Z_max": round(info["z_max"], 1),
            }
        },
        "mesh": {"vertices": (V - ctr).round(3).tolist(), "faces": F.tolist()},
    }
    return obj, info
