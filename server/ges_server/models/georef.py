"""IFC georeferensiya (G3): IfcProjectedCRS + IfcMapConversion yozish/o'qish (IFC4 Addendum 2, IFC4.3),
IfcSite RefLatitude/RefLongitude ni loyiha CRS dan to'ldirish."""

from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.api.georeference

from .crs import ProjectCRS, from_epsg


def _dms(deg: float) -> tuple[int, int, int, int]:
    """Gradus → IfcCompoundPlaneAngleMeasure (gradus, minut, soniya, mikrosoniya) — ishora birinchi komponentda."""
    sign = -1 if deg < 0 else 1
    d = abs(deg)
    g = int(d)
    m = int((d - g) * 60)
    s_f = ((d - g) * 60 - m) * 60
    s = int(s_f)
    us = int(round((s_f - s) * 1_000_000))
    if us == 1_000_000:
        us, s = 0, s + 1
    return (sign * g, sign * m, sign * s, sign * us)


def dms_to_deg(v) -> float | None:
    if not v:
        return None
    parts = list(v) + [0] * (4 - len(v))
    sign = -1 if any(p < 0 for p in parts) else 1
    d, m, s, us = (abs(p) for p in parts[:4])
    return sign * (d + m / 60 + s / 3600 + us / 3_600_000_000)


def apply(f: ifcopenshell.file, crs: ProjectCRS) -> dict:
    """IfcMapConversion/IfcProjectedCRS ni yozadi (bor bo'lsa yangilaydi) va IfcSite Ref* ni to'ldiradi."""
    p = crs.projection
    if not f.by_type("IfcMapConversion"):
        ifcopenshell.api.georeference.add_georeferencing(f)
    th = math.radians(crs.rotation_deg)
    ifcopenshell.api.georeference.edit_georeferencing(
        f,
        projected_crs={
            "Name": f"EPSG:{crs.epsg}",
            "Description": p.name,
            "GeodeticDatum": p.geodetic_datum,
            "VerticalDatum": "EGM2008" if p.datum == "WGS84" else "Baltic 1977",
            "MapProjection": "Transverse Mercator" if p.datum == "WGS84" else "Gauss-Kruger",
            "MapZone": f"{p.zone}{'N' if p.false_n == 0 else 'S'}" if p.datum == "WGS84" else str(p.zone),
        },
        coordinate_operation={
            "Eastings": float(crs.origin_e),
            "Northings": float(crs.origin_n),
            "OrthogonalHeight": float(crs.origin_h),
            "XAxisAbscissa": math.cos(th),
            "XAxisOrdinate": math.sin(th),
            "Scale": float(crs.scale),
        },
    )
    lat, lon = crs.to_latlon(0.0, 0.0)
    for site in f.by_type("IfcSite"):
        site.RefLatitude = _dms(lat)
        site.RefLongitude = _dms(lon)
        if site.RefElevation is None:
            site.RefElevation = float(crs.origin_h)
    return read(f)


def read(f: ifcopenshell.file) -> dict | None:
    """IfcMapConversion → {epsg, name, origin_e, origin_n, origin_h, rotation_deg, scale, datum, site_lat, site_lon}."""
    convs = f.by_type("IfcMapConversion")
    out: dict = {}
    if convs:
        mc = convs[0]
        tcrs = mc.TargetCRS
        name = (tcrs.Name or "") if tcrs else ""
        epsg = None
        if name.upper().startswith("EPSG:"):
            try:
                epsg = int(name[5:])
            except ValueError:
                epsg = None
        rot = math.degrees(math.atan2(mc.XAxisOrdinate or 0.0, mc.XAxisAbscissa if mc.XAxisAbscissa is not None else 1.0))
        out = {
            "epsg": epsg,
            "name": name,
            "description": getattr(tcrs, "Description", None) if tcrs else None,
            "datum": getattr(tcrs, "GeodeticDatum", None) if tcrs else None,
            "origin_e": mc.Eastings,
            "origin_n": mc.Northings,
            "origin_h": mc.OrthogonalHeight,
            "rotation_deg": round(rot, 6),
            "scale": mc.Scale if mc.Scale is not None else 1.0,
            "supported": epsg is not None and _supported(epsg),
        }
    sites = f.by_type("IfcSite")
    if sites:
        lat, lon = dms_to_deg(sites[0].RefLatitude), dms_to_deg(sites[0].RefLongitude)
        if lat is not None and lon is not None:
            out["site_lat"], out["site_lon"] = round(lat, 7), round(lon, 7)
    return out or None


def _supported(epsg: int) -> bool:
    try:
        from_epsg(epsg)
        return True
    except ValueError:
        return False
