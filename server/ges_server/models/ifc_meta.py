"""IFC fayldan metadata olish (IfcOpenShell). Xatolik bo'lsa ValueError."""

from collections import Counter
from pathlib import Path

import ifcopenshell


def extract(path: Path) -> dict:
    try:
        f = ifcopenshell.open(str(path))
    except Exception as e:  # ifcopenshell turli xatolar tashlaydi
        raise ValueError(f"IFC fayl o'qilmadi: {e}") from e

    products = f.by_type("IfcProduct")
    type_counts = Counter(p.is_a() for p in products)
    projects = f.by_type("IfcProject")
    storeys = [
        {"guid": s.GlobalId, "name": s.Name or "", "elevation": getattr(s, "Elevation", None)}
        for s in f.by_type("IfcBuildingStorey")
    ]
    return {
        "schema": f.schema,
        "project_name": projects[0].Name if projects else None,
        "element_count": len(products),
        "type_counts": dict(type_counts.most_common(50)),
        "storeys": storeys,
    }
