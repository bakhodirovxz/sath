"""Sensor ↔ IFC element bog'lanishi (SCADA-13): GUID tekshiruvi, "bog'lanmagan sensorlar" hisoboti,
yangi versiya nashr etilganda muhandislarga bildirishnoma.

Mos yozuvlar versiyasi (reference): modelning published versiyasi, yo'q bo'lsa oxirgi (head) versiya.
Sensor `model_id` berilgan bo'lsa shu model, aks holda loyihadagi barcha modellarning reference
versiyalari birlashmasi bo'yicha tekshiriladi. Loyihada versiya bo'lmasa (qurilishdan oldin) tekshiruv
o'tkazib yuboriladi. GUID lar IFC fayldan olinadi (IfcProduct, IfcSpatialElement ham) va fayl sha256
bo'yicha keshlanadi.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth.deps import DB, CurrentUser, get_project_role, has_role
from ..orm import Model, Role, Sensor, Version, VersionState

log = logging.getLogger("ges_server.linkage")
router = APIRouter(prefix="/api", tags=["monitoring"])

_CACHE: OrderedDict[str, frozenset[str]] = OrderedDict()
_CACHE_MAX = 8
_LOCK = threading.Lock()


def version_guids(v: Version) -> frozenset[str] | None:
    """Versiya faylidagi GlobalId lar (IfcProduct); fayl ochilmasa None (tekshiruv o'tkaziladi)."""
    key = v.file_sha256
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    try:
        import ifcopenshell

        from ..models import storage

        f = ifcopenshell.open(str(storage.resolve(key)))
        guids = frozenset(e.GlobalId for e in f.by_type("IfcProduct"))
    except Exception:  # noqa: BLE001 — IFC bo'lmagan / o'qilmagan fayl: tekshiruvni to'xtatmaymiz
        log.warning("linkage: versiya %s GUID lari o'qilmadi", v.id, exc_info=True)
        return None
    with _LOCK:
        _CACHE[key] = guids
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return guids


def reference_version(m: Model) -> Version | None:
    """published, yo'q bo'lsa oxirgi (head) versiya."""
    if not m.versions:
        return None
    pub = next((v for v in m.versions if v.state == VersionState.published), None)
    return pub or m.versions[-1]


def _reference_guids(db: Session, project_id: int, model_id: int | None) -> tuple[frozenset[str] | None, list[int]]:
    """(GUID to'plami yoki None — tekshirib bo'lmaydi, ishlatilgan versiya id lari)."""
    q = db.query(Model).filter(Model.project_id == project_id)
    if model_id is not None:
        q = q.filter(Model.id == model_id)
    out: set[str] = set()
    used: list[int] = []
    for m in q.all():
        v = reference_version(m)
        if v is None:
            continue
        g = version_guids(v)
        if g is None:
            continue
        out |= g
        used.append(v.id)
    return (frozenset(out) if used else None), used


def check_sensor_guid(
    db: Session, project_id: int, model_id: int | None, guid: str | None, force: bool = False
) -> None:
    """Sensor yaratish/tahrirlashda: GUID reference versiyada bo'lmasa 422. `force=True` — qurilishdan
    oldingi (hali modelda yo'q) element uchun ataylab bog'lash."""
    if not guid or force:
        return
    guids, used = _reference_guids(db, project_id, model_id)
    if guids is None:
        return  # versiya yo'q — tekshirib bo'lmaydi
    if guid not in guids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"element_guid «{guid}» joriy model versiyasida (id {', '.join(map(str, used))}) topilmadi — "
            "GUID ni tekshiring yoki hali modelda yo'q element uchun force=true bilan saqlang",
        )


def unlinked(db: Session, project_id: int, version_id: int | None = None) -> dict:
    """GUID i versiyada yo'q sensorlar. version_id berilsa — shu versiya (sensor model_id si shu model
    yoki bo'sh bo'lganlar); aks holda har sensor o'z modelining reference versiyasi bo'yicha."""
    sensors = (
        db.query(Sensor)
        .filter(Sensor.project_id == project_id, Sensor.element_guid.isnot(None), Sensor.element_guid != "")
        .order_by(Sensor.key)
        .all()
    )
    out: list[dict] = []
    checked = 0
    if version_id is not None:
        v = db.get(Version, version_id)
        if v is None or v.model.project_id != project_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Versiya topilmadi")
        guids = version_guids(v)
        if guids is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Versiya faylidan GUID o'qib bo'lmadi")
        for s in sensors:
            if s.model_id not in (None, v.model_id):
                continue
            checked += 1
            if s.element_guid not in guids:
                out.append(_row(s))
        return {"version_id": v.id, "checked": checked, "count": len(out), "sensors": out}
    cache: dict[int | None, frozenset[str] | None] = {}
    for s in sensors:
        if s.model_id not in cache:
            cache[s.model_id] = _reference_guids(db, project_id, s.model_id)[0]
        guids = cache[s.model_id]
        if guids is None:
            continue
        checked += 1
        if s.element_guid not in guids:
            out.append(_row(s))
    return {"version_id": None, "checked": checked, "count": len(out), "sensors": out}


def _row(s: Sensor) -> dict:
    return {"id": s.id, "key": s.key, "name": s.name, "element_guid": s.element_guid, "model_id": s.model_id}


def on_version_published(db: Session, version: Version) -> int:
    """Hook: versiya nashr etilganda (review merge) bog'lanmagan sensorlar hisobotini tuzadi va loyiha
    muhandislariga (muhandis+) bildirishnoma qo'shadi. Xato nashrni to'xtatmaydi. Commit chaqiruvchida.
    Qaytaradi: bog'lanmagan sensorlar soni."""
    try:
        from .. import notifications

        project_id = version.model.project_id
        rep = unlinked(db, project_id, version.id)
        if rep["count"] == 0:
            return 0
        keys = ", ".join(x["key"] for x in rep["sensors"][:10]) + (" …" if rep["count"] > 10 else "")
        notifications.push(
            db,
            notifications.member_ids(db, project_id, role=Role.engineer, at_least=True),
            "system",
            f"Bog'lanmagan sensorlar: {rep['count']} ta («{version.model.name}» v{version.number})",
            f"Yangi versiyada element GUID i topilmadi: {keys}. Sensorlarni qayta bog'lang.",
            f"/projects/{project_id}/monitoring?unlinked={version.id}",
        )
        return rep["count"]
    except Exception:  # noqa: BLE001
        log.warning("linkage: nashr hook xatosi (versiya %s)", getattr(version, "id", None), exc_info=True)
        return 0


@router.get("/projects/{project_id}/sensors/unlinked")
def unlinked_sensors(
    project_id: int, user: CurrentUser, db: DB, version_id: int | None = Query(None)
):
    """Element GUID i (berilgan yoki joriy) versiyada topilmagan sensorlar."""
    if not has_role(get_project_role(db, project_id, user), Role.viewer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")
    return unlinked(db, project_id, version_id)
