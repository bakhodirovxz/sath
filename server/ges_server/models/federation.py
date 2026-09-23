"""Model federatsiyasi (G5): bir loyihaning bir necha model versiyasini bitta koordinata fazosiga yig'ish —
a'zo bo'yicha siljish/burilish (lokal, loyiha CRS ga nisbatan), federatsiya ustida to'qnashuv tahlili
(modellar orasida) va ko'rish uchun birlashtirilgan IFC (mavjud viewer bitta fayl yuklaydi)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..orm import Model, Version, VersionState
from . import geometry, storage

log = logging.getLogger("ges_server.federation")


def resolve_members(db: Session, members: list[dict]) -> list[dict]:
    """A'zolar → [{model_id, model_name, version_id, version_number, sha, dx, dy, dz, rot_deg}] —
    version_id berilmasa oxirgi published (yo'q bo'lsa oxirgi) versiya."""
    out = []
    for m in members:
        model = db.get(Model, int(m["model_id"]))
        if model is None or model.deleted_at is not None:  # VCS-06: savatdagi model federatsiyada yo'q
            raise ValueError(f"Model {m['model_id']} topilmadi")
        v = None
        if m.get("version_id"):
            v = db.get(Version, int(m["version_id"]))
            if v is None or v.model_id != model.id:
                raise ValueError(f"Versiya {m['version_id']} modelga tegishli emas")
        else:
            pub = [x for x in model.versions if x.state == VersionState.published]
            v = (pub or model.versions or [None])[-1]
        if v is None:
            raise ValueError(f"«{model.name}» modelida versiya yo'q")
        out.append(
            {
                "model_id": model.id,
                "model_name": model.name,
                "project_id": model.project_id,
                "version_id": v.id,
                "version_number": v.number,
                "sha": v.file_sha256,
                "dx": float(m.get("dx") or 0.0),
                "dy": float(m.get("dy") or 0.0),
                "dz": float(m.get("dz") or 0.0),
                "rot_deg": float(m.get("rot_deg") or 0.0),
            }
        )
    return out


def cache_key(resolved: list[dict], extra: str = "") -> str:
    raw = json.dumps([(m["sha"], m["dx"], m["dy"], m["dz"], m["rot_deg"]) for m in resolved]) + extra
    return hashlib.sha256(raw.encode()).hexdigest()


def clashes(resolved: list[dict], tolerance: float = 0.0, cross_only: bool = True) -> dict:
    """Federatsiya to'qnashuvlari: har a'zo mesh lari siljitilib/burilib bitta ro'yxatga; `cross_only` —
    faqat turli modellar orasidagi juftliklar (har modelning ichki to'qnashuvi o'z hisobotida)."""
    meshes: list[geometry.Mesh] = []
    for m in resolved:
        base = geometry.load_meshes(storage.resolve(m["sha"]))
        meshes.extend(geometry.transformed(base, m["dx"], m["dy"], m["dz"], m["rot_deg"], f"{m['model_name']} v{m['version_number']}"))
    rep = geometry.clashes_of(meshes, tolerance, cross_groups_only=cross_only)
    rep["members"] = [{k: m[k] for k in ("model_id", "model_name", "version_id", "version_number", "dx", "dy", "dz", "rot_deg")} for m in resolved]
    rep["cross_only"] = cross_only
    return rep


def clash_cache_key(resolved: list[dict], tolerance: float = 0.0, cross_only: bool = True) -> str:
    return cache_key(resolved, f"{tolerance}:{cross_only}")


def peek_clashes(resolved: list[dict], tolerance: float = 0.0, cross_only: bool = True) -> dict | None:
    """Keshlangan federatsiya to'qnashuvlari (hisoblamasdan) — yo'q bo'lsa None (OPS-03: navbatga)."""
    return geometry.peek(clash_cache_key(resolved, tolerance, cross_only), "fedclash")


def cached_clashes(resolved: list[dict], tolerance: float = 0.0, cross_only: bool = True) -> dict:
    key = clash_cache_key(resolved, tolerance, cross_only)
    return geometry.cached(key, "fedclash", lambda: clashes(resolved, tolerance, cross_only))


def merged_ifc(resolved: list[dict]) -> Path:
    """Birlashtirilgan IFC (kesh: data/derived/fed-<key>.ifc): birinchi a'zo fayli asos, qolgan a'zolarning
    elementlari (geometriyasi bilan) siljitilib nusxalanadi; element GUID lari saqlanadi (to'qnashuv
    ro'yxatidan 3D da tanlash uchun), nomga model nomi prefiksi."""
    key = cache_key(resolved)
    out = get_settings().data_dir / "derived" / f"fed-{key[:32]}.ifc"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    first = resolved[0]
    f = ifcopenshell.open(str(storage.resolve(first["sha"])))
    _shift_all(f, first)
    for m in resolved[1:]:
        src = ifcopenshell.open(str(storage.resolve(m["sha"])))
        _append(f, src, m)
    f.write(str(out))
    return out


def _shift_all(f: ifcopenshell.file, m: dict) -> None:
    if not any((m["dx"], m["dy"], m["dz"], m["rot_deg"])):
        return
    T = _matrix(m, ifcopenshell.util.unit.calculate_unit_scale(f))
    for el in f.by_type("IfcElement"):
        if el.ObjectPlacement is None:
            continue
        cur = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)
        ifcopenshell.api.geometry.edit_object_placement(f, product=el, matrix=T @ cur, is_si=False)


def _matrix(m: dict, unit_scale: float) -> np.ndarray:
    th = np.radians(m["rot_deg"])
    T = np.eye(4)
    T[:3, :3] = [[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]]
    T[:3, 3] = np.array([m["dx"], m["dy"], m["dz"]]) / unit_scale  # metr → fayl birligi
    return T


def _append(f: ifcopenshell.file, src: ifcopenshell.file, m: dict) -> None:
    """src elementlarini f ga nusxalash (IfcSite konteyneriga), siljitib; Pset lar bilan."""
    site = (f.by_type("IfcSite") or f.by_type("IfcBuildingStorey") or [None])[0]
    scale_f = ifcopenshell.util.unit.calculate_unit_scale(f)
    scale_s = ifcopenshell.util.unit.calculate_unit_scale(src)
    T = _matrix(m, scale_f)
    prefix = f"[{m['model_name']} v{m['version_number']}] "
    for el in src.by_type("IfcElement"):
        if el.Representation is None:
            continue
        try:
            f.by_guid(el.GlobalId)
            dup = True  # bir xil GUID allaqachon bor (shu model ikki marta) — yangisi beriladi
        except RuntimeError:
            dup = False
        new = ifcopenshell.util.element.copy_deep(f, el)  # geometriya, Pset havolalari
        new.GlobalId = ifcopenshell.guid.new() if dup else el.GlobalId  # GUID saqlanadi — 3D da tanlash uchun
        new.Name = prefix + (el.Name or "")
        cur = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement) if el.ObjectPlacement else np.eye(4)
        cur[:3, 3] *= scale_s / scale_f  # manba birligi → asos birligi
        ifcopenshell.api.geometry.edit_object_placement(f, product=new, matrix=T @ cur, is_si=False)
        if site is not None:
            ifcopenshell.api.spatial.assign_container(f, relating_structure=site, products=[new])
