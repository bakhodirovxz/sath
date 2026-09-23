"""IFC fayldan metadata olish (IfcOpenShell). Xatolik bo'lsa ValueError.

OPS-03: yuklash so'rovida to'liq parse (2 GB gacha IFC — daqiqalar, GB xotira) chegaralangan:
`extract_bounded` `META_SYNC_MAX_BYTES` dan katta faylda faqat STEP sarlavhasini (sxema) o'qiydi va
`pending` belgisini qo'yadi — to'liq metadata `meta` navbat ishida (derived.py) hisoblanib versiyaga yoziladi.
Kichik fayllar (odatiy) avvalgidek darhol to'liq tahlil qilinadi va buzuq IFC 400 bilan rad etiladi.
"""

import re
from collections import Counter
from pathlib import Path

import ifcopenshell

META_SYNC_MAX_BYTES = 256 * 1024 * 1024
PENDING_WARNING = "Katta fayl"
_SCHEMA_RE = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", re.IGNORECASE)


def extract_bounded(path: Path, max_bytes: int | None = None) -> dict:
    """So'rov ichida xavfsiz metadata: kichik fayl — `extract`; katta — faqat sarlavha + `pending`."""
    limit = META_SYNC_MAX_BYTES if max_bytes is None else max_bytes
    size = path.stat().st_size
    if size <= limit:
        return extract(path)
    with open(path, "rb") as fh:
        head = fh.read(64 * 1024).decode("latin-1", errors="replace")
    if not head.lstrip().startswith("ISO-10303-21"):
        raise ValueError("IFC fayl o'qilmadi: STEP (ISO-10303-21) sarlavhasi yo'q")
    m = _SCHEMA_RE.search(head)
    return {
        "schema": m.group(1).upper() if m else None,
        "project_name": None,
        "element_count": None,
        "type_counts": {},
        "storeys": [],
        "georef": None,
        "classification": None,
        "pending": True,
        "warnings": [f"{PENDING_WARNING} ({size // (1024 * 1024)} MB): to'liq metadata fonda hisoblanmoqda"],
    }


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
    from . import classification, georef

    return {
        "schema": f.schema,
        "project_name": projects[0].Name if projects else None,
        "element_count": len(products),
        "type_counts": dict(type_counts.most_common(50)),
        "storeys": storeys,
        "georef": georef.read(f),  # G3: IfcMapConversion (epsg, origin, burilish) + IfcSite lat/lon yoki None
        "classification": classification.summary(f),  # G5: klassifikatorlar va kodlar bo'yicha soni
    }
