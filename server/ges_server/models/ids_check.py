"""IDS (Information Delivery Specification, buildingSMART) tekshiruvi (G2): `docs/ids/sath-ges.ids` ga
nisbatan `ifctester` bilan. Natija versiyaga biriktiriladi (`Version.ids_status`, `ids_result`);
loyihada `ids_required` bo'lsa yiqilgan versiya tasdiqlanmaydi/merge qilinmaydi."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("ges_server.ids")

MAX_FAILURES = 200  # har talab uchun saqlanadigan yiqilgan elementlar


def ids_path() -> Path:
    """Sozlangan IDS fayli: `ids_file` (nisbiy — CWD, keyin repo ildizi, keyin /app)."""
    p = Path(get_settings().ids_file)
    if p.is_absolute() or p.exists():
        return p
    for root in (Path(__file__).resolve().parents[3], Path("/app")):
        cand = root / p
        if cand.exists():
            return cand
    return p


def validate(ifc_path: Path, ids_file: Path | None = None) -> dict:
    """IFC ni IDS ga nisbatan tekshiradi → {status, ids, checked_at, totals..., specifications: [...]}.
    IDS fayli yo'q/xato bo'lsa `status="error"` (chaqiruvchi ogohlantiradi, yuklash to'xtamaydi)."""
    import ifcopenshell
    import ifctester.ids
    import ifctester.reporter

    ids_file = ids_file or ids_path()
    out: dict = {"ids": ids_file.name, "checked_at": datetime.now(timezone.utc).isoformat()}
    if not ids_file.exists():
        out.update(status="error", error=f"IDS fayli topilmadi: {ids_file}")
        return out
    try:
        specs = ifctester.ids.open(str(ids_file))
        f = ifcopenshell.open(str(ifc_path))
        specs.validate(f)
        rep = ifctester.reporter.Json(specs)
        rep.report()
        r = rep.results
    except Exception as e:  # noqa: BLE001 — natija holat sifatida saqlanadi
        log.exception("IDS tekshiruvi xato: %s", ifc_path)
        out.update(status="error", error=f"{type(e).__name__}: {e}"[:400])
        return out
    idents = _identifiers(ids_file)
    out.update(
        status="pass" if r["status"] else "fail",
        title=r.get("title"),
        total_specifications=r.get("total_specifications", 0),
        total_specifications_pass=r.get("total_specifications_pass", 0),
        total_checks=r.get("total_checks", 0),
        total_checks_pass=r.get("total_checks_pass", 0),
        specifications=[
            {
                "identifier": s.get("identifier") or (idents[i] if i < len(idents) else None),
                "name": s.get("name"),
                "description": s.get("description") or "",
                "status": bool(s.get("status")),
                "applicable": s.get("total_applicable", 0),
                "passed": s.get("total_applicable_pass", 0),
                "failed": s.get("total_applicable_fail", 0),
                "requirements": [
                    {
                        "description": req.get("description"),
                        "status": bool(req.get("status")),
                        "failed": [
                            {
                                "guid": e.get("global_id"),
                                "class": e.get("class"),
                                "name": e.get("name"),
                                "reason": e.get("reason"),
                            }
                            for e in (req.get("failed_entities") or [])[:MAX_FAILURES]
                        ],
                        "failed_total": len(req.get("failed_entities") or []),
                    }
                    for req in s.get("requirements", [])
                ],
            }
            for i, s in enumerate(r.get("specifications", []))
        ],
    )
    return out


def _identifiers(ids_file: Path) -> list[str | None]:
    """IDS dagi `identifier` atributlari tartibda (ifctester 0.8 ularni natijaga o'tkazmaydi)."""
    from defusedxml import ElementTree as ET

    try:
        root = ET.parse(str(ids_file)).getroot()
    except Exception:  # noqa: BLE001 — identifikatorlar ixtiyoriy
        return []
    return [e.get("identifier") for e in root.iter() if e.tag.endswith("}specification") or e.tag == "specification"]


def check_and_store(sha: str) -> str | None:
    """Ish navbati (derived `ids`): shu sha li barcha versiyalarga natija yoziladi; qaytaradi holat."""
    from ..db import SessionLocal
    from ..orm import Version
    from . import storage

    try:
        path = storage.resolve(sha)
    except FileNotFoundError:
        return None
    res = validate(path)
    with SessionLocal() as db:
        for v in db.query(Version).filter_by(file_sha256=sha).all():
            v.ids_status = res["status"]
            v.ids_result = res
        db.commit()
    return res["status"]
