"""Georeferensiya (G3): loyiha CRS (EPSG) ↔ lokal model koordinatalari; tashqi kutubxonasiz.

Qo'llab-quvvatlanadi:
- WGS 84 / UTM: EPSG:326NN (shimoliy), 327NN (janubiy) — O'zbekiston: 41N (EPSG:32641), 42N (EPSG:32642).
- Pulkovo 1942 / Gauss-Krüger 6° zonalari (SK-42): EPSG:284NN (NN — zona; O'zbekiston 11–12), Krassovskiy
  ellipsoidi; WGS84 ↔ Pulkovo datum o'tishi Helmert 7 parametr (EPSG::15865 «Pulkovo 1942 to WGS 84 (16)»,
  GOST R 51794-2008; aniqlik ~1–3 m — geodeziya bilan solishtirishda buni hisobga oling).
Proyeksiya: ko'ndalang Merkator, Krüger qatorlari (n³ tartib, zona ichida < 1 mm). Manba: Karney 2011,
«Transverse Mercator with an accuracy of a few nanometers» (soddalashtirilgan 3-tartib).

Lokal ↔ global: IfcMapConversion (Eastings, Northings, OrthogonalHeight, XAxisAbscissa/Ordinate, Scale):
  E = E0 + s·(x·cosθ − y·sinθ),  N = N0 + s·(x·sinθ + y·cosθ),  H = H0 + z.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Ellipsoid:
    a: float
    f: float

    @property
    def n(self) -> float:
        return self.f / (2 - self.f)


WGS84 = Ellipsoid(6378137.0, 1 / 298.257223563)
KRASSOVSKY = Ellipsoid(6378245.0, 1 / 298.3)


@dataclass(frozen=True)
class Projection:
    name: str
    ellipsoid: Ellipsoid
    lon0_deg: float
    k0: float
    false_e: float
    false_n: float
    datum: str  # "WGS84" | "Pulkovo1942"
    zone: int

    @property
    def geodetic_datum(self) -> str:
        return "WGS84" if self.datum == "WGS84" else "Pulkovo 1942"


def from_epsg(code: int) -> Projection:
    """EPSG kodi → proyeksiya parametrlari (faqat yuqoridagi oilalar)."""
    if 32601 <= code <= 32660:
        z = code - 32600
        return Projection(f"WGS 84 / UTM zone {z}N", WGS84, -183 + 6 * z, 0.9996, 500000.0, 0.0, "WGS84", z)
    if 32701 <= code <= 32760:
        z = code - 32700
        return Projection(f"WGS 84 / UTM zone {z}S", WGS84, -183 + 6 * z, 0.9996, 500000.0, 10_000_000.0, "WGS84", z)
    if 28402 <= code <= 28432:
        z = code - 28400
        return Projection(f"Pulkovo 1942 / Gauss-Kruger zone {z}", KRASSOVSKY, 6 * z - 3, 1.0, z * 1_000_000 + 500000.0, 0.0, "Pulkovo1942", z)
    raise ValueError(f"EPSG:{code} qo'llab-quvvatlanmaydi (UTM 326xx/327xx yoki Pulkovo GK 284xx)")


def utm_zone(lon: float) -> int:
    return int((lon + 180) // 6) + 1


# --------------------------------------------------------------------------- ko'ndalang Merkator (Krüger)


def _coeffs(n: float):
    a_ = (
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    )
    b_ = (
        n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96,
        n**2 / 48 + n**3 / 15,
        17 * n**3 / 480,
    )
    d_ = (
        2 * n - 2 * n**2 / 3 - 2 * n**3,
        7 * n**2 / 3 - 8 * n**3 / 5,
        56 * n**3 / 15,
    )
    A = 1 / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    return A, a_, b_, d_


def tm_forward(lat_deg: float, lon_deg: float, p: Projection) -> tuple[float, float]:
    """(φ, λ) → (E, N) — Krüger qatorlari."""
    e = p.ellipsoid
    n = e.n
    A, alpha, _, _ = _coeffs(n)
    A *= e.a
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg - p.lon0_deg)
    c = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi_ = math.atan2(t, math.cos(lam))
    eta_ = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi = xi_ + sum(alpha[j] * math.sin(2 * (j + 1) * xi_) * math.cosh(2 * (j + 1) * eta_) for j in range(3))
    eta = eta_ + sum(alpha[j] * math.cos(2 * (j + 1) * xi_) * math.sinh(2 * (j + 1) * eta_) for j in range(3))
    return p.false_e + p.k0 * A * eta, p.false_n + p.k0 * A * xi


def tm_inverse(easting: float, northing: float, p: Projection) -> tuple[float, float]:
    """(E, N) → (φ, λ) gradus."""
    e = p.ellipsoid
    n = e.n
    A, _, beta, delta = _coeffs(n)
    A *= e.a
    xi = (northing - p.false_n) / (p.k0 * A)
    eta = (easting - p.false_e) / (p.k0 * A)
    xi_ = xi - sum(beta[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_ = eta - sum(beta[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_) / math.cosh(eta_))
    phi = chi + sum(delta[j] * math.sin(2 * (j + 1) * chi) for j in range(3))
    lam = math.atan2(math.sinh(eta_), math.cos(xi_))
    return math.degrees(phi), p.lon0_deg + math.degrees(lam)


# --------------------------------------------------------------------------- datum (Helmert, Pulkovo 1942 ↔ WGS 84)

# EPSG::15865 Pulkovo 1942 → WGS 84 (16): dX dY dZ (m), rX rY rZ (soniya), dS (ppm); koordinata-freym aylanishi
_PULKOVO_TO_WGS84 = (23.92, -141.27, -80.9, 0.0, 0.35, 0.82, -0.12)


def _geodetic_to_xyz(lat: float, lon: float, h: float, e: Ellipsoid) -> tuple[float, float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    e2 = e.f * (2 - e.f)
    nn = e.a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return (
        (nn + h) * math.cos(phi) * math.cos(lam),
        (nn + h) * math.cos(phi) * math.sin(lam),
        (nn * (1 - e2) + h) * math.sin(phi),
    )


def _xyz_to_geodetic(x: float, y: float, z: float, e: Ellipsoid) -> tuple[float, float, float]:
    e2 = e.f * (2 - e.f)
    lam = math.atan2(y, x)
    p = math.hypot(x, y)
    phi = math.atan2(z, p * (1 - e2))
    for _ in range(6):
        nn = e.a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        h = p / math.cos(phi) - nn
        phi = math.atan2(z, p * (1 - e2 * nn / (nn + h)))
    nn = e.a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    h = p / math.cos(phi) - nn
    return math.degrees(phi), math.degrees(lam), h


def _helmert(x: float, y: float, z: float, prm, inverse: bool = False) -> tuple[float, float, float]:
    dx, dy, dz, rx, ry, rz, ds = prm
    rx, ry, rz = (math.radians(v / 3600) for v in (rx, ry, rz))
    s = 1 + ds * 1e-6
    if inverse:
        dx, dy, dz, rx, ry, rz, s = -dx, -dy, -dz, -rx, -ry, -rz, 1 / s
    # koordinata-freym aylanishi (EPSG 1032 / GOST): X' = dX + s·(X + rZ·Y − rY·Z) ...
    return (
        dx + s * (x + rz * y - ry * z),
        dy + s * (-rz * x + y + rx * z),
        dz + s * (ry * x - rx * y + z),
    )


def wgs84_to_datum(lat: float, lon: float, datum: str) -> tuple[float, float]:
    if datum == "WGS84":
        return lat, lon
    x, y, z = _geodetic_to_xyz(lat, lon, 0.0, WGS84)
    x, y, z = _helmert(x, y, z, _PULKOVO_TO_WGS84, inverse=True)
    la, lo, _ = _xyz_to_geodetic(x, y, z, KRASSOVSKY)
    return la, lo


def datum_to_wgs84(lat: float, lon: float, datum: str) -> tuple[float, float]:
    if datum == "WGS84":
        return lat, lon
    x, y, z = _geodetic_to_xyz(lat, lon, 0.0, KRASSOVSKY)
    x, y, z = _helmert(x, y, z, _PULKOVO_TO_WGS84)
    la, lo, _ = _xyz_to_geodetic(x, y, z, WGS84)
    return la, lo


# --------------------------------------------------------------------------- loyiha CRS


@dataclass(frozen=True)
class ProjectCRS:
    """Loyiha georeferensiyasi: EPSG + lokal (0,0,0) ning global (E0, N0, H0) joyi, X o'qining burilishi
    (gradus, shimoldan soat miliga qarshi → IfcMapConversion XAxisAbscissa/Ordinate), masshtab."""

    epsg: int
    origin_e: float
    origin_n: float
    origin_h: float = 0.0
    rotation_deg: float = 0.0
    scale: float = 1.0

    @property
    def projection(self) -> Projection:
        return from_epsg(self.epsg)

    def to_global(self, x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
        th = math.radians(self.rotation_deg)
        return (
            self.origin_e + self.scale * (x * math.cos(th) - y * math.sin(th)),
            self.origin_n + self.scale * (x * math.sin(th) + y * math.cos(th)),
            self.origin_h + z,
        )

    def to_local(self, e: float, n: float, h: float | None = None) -> tuple[float, float, float]:
        th = math.radians(self.rotation_deg)
        dx, dy = (e - self.origin_e) / self.scale, (n - self.origin_n) / self.scale
        return (dx * math.cos(th) + dy * math.sin(th), -dx * math.sin(th) + dy * math.cos(th), (h or 0.0) - self.origin_h)

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        e, n, _ = self.to_global(x, y)
        p = self.projection
        la, lo = tm_inverse(e, n, p)
        return datum_to_wgs84(la, lo, p.datum)

    def from_latlon(self, lat: float, lon: float) -> tuple[float, float]:
        p = self.projection
        la, lo = wgs84_to_datum(lat, lon, p.datum)
        e, n = tm_forward(la, lo, p)
        x, y, _ = self.to_local(e, n)
        return x, y

    def as_dict(self) -> dict:
        p = self.projection
        return {
            "epsg": self.epsg,
            "name": p.name,
            "origin_e": self.origin_e,
            "origin_n": self.origin_n,
            "origin_h": self.origin_h,
            "rotation_deg": self.rotation_deg,
            "scale": self.scale,
        }


def from_project(project) -> ProjectCRS | None:
    """`Project` (orm) dan; EPSG yo'q — None."""
    if not getattr(project, "epsg_code", None):
        return None
    return ProjectCRS(
        int(project.epsg_code),
        float(project.origin_e or 0.0),
        float(project.origin_n or 0.0),
        float(project.origin_h or 0.0),
        float(project.crs_rotation_deg or 0.0),
    )


def suggest_epsg(lat: float, lon: float, family: str = "utm") -> int:
    """Nuqta uchun zona: UTM (WGS84) yoki Pulkovo GK."""
    if family == "gk":
        return 28400 + int(lon // 6) + 1  # GK 6° zonalari Grinvichdan boshlab (lon0 = 6z − 3)
    z = utm_zone(lon)
    return (32600 if lat >= 0 else 32700) + z
