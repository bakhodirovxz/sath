"""FreeCAD da IFC ochish/saqlash.

FreeCAD 1.0/1.1: BIM workbench ichida NativeIFC (`nativeifc.ifc_import`, `ifc_tools`) va
eski eksporter (`importers.exportIFC`). Ikkalasi ham BIM moduli sys.path da bo'lganda import qilinadi.
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD


def _nativeifc():
    try:
        from nativeifc import ifc_import, ifc_tools  # FreeCAD 1.0+
    except ImportError:
        import ifc_import
        import ifc_tools  # eski joylashuv  # noqa: I001
    return ifc_import, ifc_tools


def _legacy_export():
    try:
        from importers import exportIFC
    except ImportError:
        import exportIFC
    return exportIFC


def open_ifc(path: Path, strategy: int = 2):
    """IFC ni yangi hujjat sifatida ochadi (NativeIFC, dialogsiz). Qaytaradi: hujjat.

    strategy: 0 — faqat ildiz, 1 — faqat bino tuzilmasi, 2 — barcha elementlar (GES modellari uchun).
    shapemode 0 — to'liq shakl (tahrirlash uchun), singledoc — hujjatning o'zi IFC loyiha.
    """
    ifc_import, _ = _nativeifc()
    doc = FreeCAD.newDocument()
    doc.Label = path.stem
    FreeCAD.setActiveDocument(doc.Name)
    FreeCAD.IsOpeningIFC = True
    try:
        ifc_import.insert(
            str(path),
            doc.Name,
            strategy=strategy,
            shapemode=0,
            switchwb=False,
            silent=True,
            singledoc=True,
        )
    finally:
        if hasattr(FreeCAD, "IsOpeningIFC"):
            del FreeCAD.IsOpeningIFC
    doc.recompute()
    doc.Meta["ges_source_path"] = str(path)
    return doc


def project_object(doc):
    """NativeIFC loyiha: "singledoc" rejimida hujjatning o'zi (IfcFilePath bor), aks holda obyekt."""
    if hasattr(doc, "IfcFilePath"):
        return doc
    for o in doc.Objects:
        if getattr(o, "Class", None) in ("IfcProject", "IfcProjectLibrary") and hasattr(o, "Proxy"):
            return o
    return None


def _is_native(obj) -> bool:
    return hasattr(obj, "StepId") and hasattr(obj, "Class")


def expand_all(doc) -> int:
    """NativeIFC daraxtini to'liq yuklaydi (elementlar dastlab kerak bo'lganda yaratiladi)."""
    _, ifc_tools = _nativeifc()
    project = project_object(doc)
    if project is None:
        return 0
    ifcfile = ifc_tools.get_ifcfile(project)
    before = len(doc.Objects)
    roots = [o for o in doc.Objects if _is_native(o)] or [project]
    for o in roots:
        try:
            ifc_tools.create_children(o, ifcfile, recursive=True, expand=True)
        except Exception as e:  # noqa: BLE001
            FreeCAD.Console.PrintWarning(
                f"Sath: {getattr(o, 'Label', o)} kengaytirilmadi: {e}\n"
            )
    doc.recompute()
    return len(doc.Objects) - before


def _write_psets(ifcfile, element, props: dict) -> None:
    """IfcProperties ("pset;;IfcType;;value") → IFC PropertySet lar (NativeIFC buni o'zi qilmaydi)."""
    if not props:
        return
    import ifcopenshell.api.pset

    grouped: dict[str, dict] = {}
    for name, raw in dict(props).items():
        parts = str(raw).split(";;")
        if len(parts) != 3:
            continue
        pset, ptype, value = parts
        if ptype in ("IfcReal", "IfcLengthMeasure", "IfcPositiveLengthMeasure"):
            try:
                value = float(value)
            except ValueError:
                pass
        elif ptype in ("IfcInteger", "IfcCountMeasure"):
            try:
                value = int(float(value))
            except ValueError:
                pass
        elif ptype == "IfcBoolean":
            value = str(value).lower() in ("true", "1", "yes")
        grouped.setdefault(pset, {})[name.split(";;")[0]] = value
    for pset, values in grouped.items():
        ps = ifcopenshell.api.pset.add_pset(ifcfile, product=element, name=pset)
        ifcopenshell.api.pset.edit_pset(ifcfile, pset=ps, properties=values)


def save_ifc(doc, path: Path) -> Path:
    """Hujjatni IFC ga yozadi.

    - NativeIFC loyiha bo'lsa: yangi (IFC bo'lmagan) obyektlar loyihaga qo'shiladi (aggregate),
      keyin ifcfile yoziladi — mavjud elementlar GUID lari saqlanadi (diff ishlaydi).
    - Aks holda: eski eksporter bilan barcha obyektlar (GES obyektlari IfcType + IfcProperties bilan).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    project = project_object(doc)
    if project is not None:
        _, ifc_tools = _nativeifc()
        new_objs = [
            o
            for o in doc.Objects
            if not _is_native(o)
            and hasattr(o, "Shape")
            and not o.Shape.isNull()
            and not o.Name.startswith("Origin")
            and o.TypeId != "App::Origin"
        ]
        if new_objs:
            parent = _default_container(doc) or project
            ifcfile = ifc_tools.get_ifcfile(project)
            for o in new_objs:
                label = o.Label
                props = dict(getattr(o, "IfcProperties", {}) or {})
                try:
                    # aggregate asl obyektni o'chirib, IFC obyekt bilan almashtiradi
                    newobj = ifc_tools.aggregate(o, parent)
                    element = ifc_tools.get_ifc_element(newobj, ifcfile) if newobj else None
                    if element is not None:
                        _write_psets(ifcfile, element, props)
                except Exception as e:  # noqa: BLE001 — bitta obyekt xatosi qolganini to'xtatmasin
                    FreeCAD.Console.PrintWarning(f"Sath: {label} IFC ga qo'shilmadi: {e}\n")
            doc.recompute()
        ifc_tools.save_ifc(project, str(path))
        return path
    _legacy_export().export(
        [o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()], str(path)
    )
    return path


def _default_container(doc):
    """Yangi elementlar uchun konteyner: birinchi IfcSite/IfcBuilding/IfcBuildingStorey."""
    for cls in ("IfcBuildingStorey", "IfcBuilding", "IfcSite"):
        for o in doc.Objects:
            if getattr(o, "Class", None) == cls:
                return o
    return None


def doc_model_id(doc) -> int | None:
    v = doc.Meta.get("ges_model_id") if doc else None
    return int(v) if v else None


def doc_version_id(doc) -> int | None:
    v = doc.Meta.get("ges_version_id") if doc else None
    return int(v) if v else None


def tag_document(doc, model_id: int, version_id: int | None, model_name: str) -> None:
    doc.Meta["ges_model_id"] = str(model_id)
    doc.Meta["ges_version_id"] = str(version_id or "")
    doc.Meta["ges_model_name"] = model_name
