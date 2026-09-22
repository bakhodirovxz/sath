"""Aktiv topshiruvi (G6): IFC dan aktiv registri (COBie ga o'xshash) — Facility / Floor / Space / Type /
Component / Attribute jadvallari; CSV (zip) eksport; aktivlarga (`Asset`) sinxronlash.

Manba maydonlar: Pset_ManufacturerTypeInformation (Manufacturer, ModelLabel, ArticleNumber),
Pset_ManufacturerOccurrence (SerialNumber, BarCode, AssemblyPlace), Pset_Warranty (WarrantyStartDate,
WarrantyEndDate, WarrantyPeriod), Pset_ServiceLife (ServiceLifeDuration), Pset_GES_* (mahalliy: Ishlab_chiqaruvchi,
Model, Seriya, Kafolat_oy, TX_davri_soat/oy, O'rnatilgan_yil) — birinchi topilgan qiymat olinadi.
COBie 2.4 (BS 1192-4) ustunlari soddalashtirilgan (Name, CreatedBy, CreatedOn, Category, ...)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element

from . import classification

_ASSET_CLASSES = (
    "IfcFlowMovingDevice",
    "IfcElectricGenerator",
    "IfcTransformer",
    "IfcPipeSegment",
    "IfcValve",
    "IfcPump",
    "IfcSwitchingDevice",
    "IfcElectricDistributionBoard",
    "IfcDistributionElement",
    "IfcBuildingElementProxy",
    "IfcWall",
    "IfcSlab",
)


def _first(psets: dict, keys: list[tuple[str, str]]):
    for pset, prop in keys:
        v = (psets.get(pset) or {}).get(prop)
        if v not in (None, ""):
            return v
    return None


def _container_name(el) -> tuple[str, str]:
    c = ifcopenshell.util.element.get_container(el)
    storey = c.Name if c is not None and c.is_a("IfcBuildingStorey") else ""
    space = c.Name if c is not None and c.is_a("IfcSpace") else ""
    return storey or "", space or ""


def register(f: ifcopenshell.file) -> dict:
    """Aktiv registri: {facility, floors, types, components, attributes}."""
    now = datetime.now(timezone.utc).date().isoformat()
    proj = f.by_type("IfcProject")
    site = f.by_type("IfcSite")
    facility = {
        "Name": (site[0].Name if site else None) or (proj[0].Name if proj else "") or "",
        "ProjectName": proj[0].Name if proj else "",
        "SiteName": site[0].Name if site else "",
        "CreatedOn": now,
        "Category": "Hydroelectric power station",
        "LinearUnits": "meter",
    }
    floors = [{"Name": s.Name or "", "Category": "Floor", "Elevation": getattr(s, "Elevation", None)} for s in f.by_type("IfcBuildingStorey")]
    types: dict[str, dict] = {}
    components = []
    attributes = []
    for el in f.by_type("IfcElement"):
        if not any(el.is_a(c) for c in _ASSET_CLASSES):
            continue
        psets = ifcopenshell.util.element.get_psets(el) or {}
        ges = {k: v for k, v in psets.items() if k.startswith("Pset_GES_")}
        if not ges and not any(el.is_a(c) for c in ("IfcFlowMovingDevice", "IfcElectricGenerator", "IfcTransformer", "IfcValve", "IfcPump", "IfcSwitchingDevice")):
            continue  # oddiy qurilish elementi (devor/plita) — Pset_GES_* siz aktiv emas
        kind = classification.kind_of(el)
        refs = classification.references(el)
        cat = refs[0]["code"] + " " + (refs[0]["name"] or "") if refs else (kind or el.is_a())
        el_type = ifcopenshell.util.element.get_type(el)
        type_name = (el_type.Name if el_type is not None else None) or f"{el.is_a()}:{kind or 'umumiy'}"
        manufacturer = _first(psets, [("Pset_ManufacturerTypeInformation", "Manufacturer")] + [(p, "Ishlab_chiqaruvchi") for p in ges])
        model_label = _first(psets, [("Pset_ManufacturerTypeInformation", "ModelLabel")] + [(p, "Model") for p in ges])
        serial = _first(psets, [("Pset_ManufacturerOccurrence", "SerialNumber")] + [(p, "Seriya") for p in ges])
        warranty_end = _first(psets, [("Pset_Warranty", "WarrantyEndDate")])
        warranty_months = _first(psets, [("Pset_Warranty", "WarrantyPeriod")] + [(p, "Kafolat_oy") for p in ges])
        mx_hours = _first(psets, [(p, "TX_davri_soat") for p in ges])
        mx_months = _first(psets, [(p, "TX_davri_oy") for p in ges])
        installed = _first(psets, [("Pset_ManufacturerOccurrence", "InstallationDate")] + [(p, "O'rnatilgan_yil") for p in ges])
        storey, space = _container_name(el)
        types.setdefault(
            type_name,
            {
                "Name": type_name,
                "Category": cat,
                "AssetType": "Fixed",
                "Manufacturer": manufacturer or "",
                "ModelNumber": model_label or "",
                "WarrantyDurationParts": warranty_months or "",
                "ExpectedLife": _first(psets, [("Pset_ServiceLife", "ServiceLifeDuration")]) or "",
                "ReplacementCost": "",
                "IfcClass": el.is_a(),
            },
        )
        components.append(
            {
                "Name": el.Name or el.GlobalId,
                "TypeName": type_name,
                "Space": space,
                "Floor": storey,
                "SerialNumber": serial or "",
                "InstallationDate": installed or "",
                "WarrantyEndDate": warranty_end or "",
                "MaintenanceIntervalHours": mx_hours or "",
                "MaintenanceIntervalMonths": mx_months or "",
                "ExtIdentifier": el.GlobalId,
                "ExtObject": el.is_a(),
                "Category": cat,
                "Kind": kind or "",
            }
        )
        for pname, props in ges.items():
            for k, v in (props or {}).items():
                if k == "id" or v in (None, ""):
                    continue
                attributes.append({"Name": k, "SheetName": "Component", "RowName": el.Name or el.GlobalId, "Value": v, "PropertySet": pname})
    return {
        "facility": facility,
        "floors": floors,
        "types": list(types.values()),
        "components": components,
        "attributes": attributes,
        "counts": {"types": len(types), "components": len(components), "attributes": len(attributes)},
    }


def register_from_path(path: Path) -> dict:
    return register(ifcopenshell.open(str(path)))


def to_csv_zip(reg: dict) -> bytes:
    """COBie-ga o'xshash CSV varaqlari (Facility, Floor, Type, Component, Attribute) bitta zip da."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, rows in (
            ("Facility", [reg["facility"]]),
            ("Floor", reg["floors"]),
            ("Type", reg["types"]),
            ("Component", reg["components"]),
            ("Attribute", reg["attributes"]),
        ):
            s = io.StringIO()
            if rows:
                w = csv.DictWriter(s, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            z.writestr(f"{name}.csv", "﻿" + s.getvalue())
    return buf.getvalue()


def sync_assets(db, project_id: int, reg: dict) -> dict:
    """Registrdan `Asset` yozuvlari: element_guid bo'yicha mavjudlar yangilanadi (nom, TX davri, config),
    yo'qlari yaratiladi. Faqat uskuna turlari (turbina, generator, transformator, zatvor, nasos)."""
    from ..orm import Asset

    equipment = {"turbine", "generator", "transformer"}
    existing = {a.element_guid: a for a in db.query(Asset).filter_by(project_id=project_id).all() if a.element_guid}
    created = updated = 0
    for c in reg["components"]:
        if c["Kind"] not in equipment and c["ExtObject"] not in ("IfcValve", "IfcPump"):
            continue
        cfg = {k: v for k, v in {"manufacturer": next((t["Manufacturer"] for t in reg["types"] if t["Name"] == c["TypeName"]), ""), "model": next((t["ModelNumber"] for t in reg["types"] if t["Name"] == c["TypeName"]), ""), "serial": c["SerialNumber"], "warranty_end": c["WarrantyEndDate"], "classification": c["Category"], "installed": c["InstallationDate"]}.items() if v not in ("", None)}
        interval = float(c["MaintenanceIntervalHours"]) if c["MaintenanceIntervalHours"] not in ("", None) else None
        a = existing.get(c["ExtIdentifier"])
        if a is None:
            a = Asset(project_id=project_id, name=c["Name"], element_guid=c["ExtIdentifier"], maintenance_interval_hours=interval, config={"kind": c["Kind"], **cfg})
            db.add(a)
            created += 1
        else:
            a.name = c["Name"] or a.name
            if interval and not a.maintenance_interval_hours:
                a.maintenance_interval_hours = interval
            a.config = {**(a.config or {}), "kind": c["Kind"], **cfg}
            updated += 1
    db.flush()
    return {"created": created, "updated": updated}
