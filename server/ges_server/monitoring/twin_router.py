"""Raqamli egizak API: joriy holat, aktivlar (CRUD, holat), vaqt mashinasi, kunlik hisobot yuborish."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, require_project_role
from ..orm import Asset, Project, Role, Sensor, utcnow
from . import health, twin

router = APIRouter(prefix="/api", tags=["twin"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]


@router.get("/projects/{project_id}/twin")
def twin_state(project: ViewerProject, db: DB):
    """Egizak: brutto napor, agregatlar bo'yicha o'lchangan/kutilgan quvvat, og'ish, FIK."""
    return twin.compute(db, project)


class WhatIf(BaseModel):
    """«Nima bo'lsa» sinovi: jonli qiymatlar o'rniga (hech narsa yozilmaydi)."""

    upstream_level: float | None = None
    downstream_level: float | None = None
    penstock_flow: float | None = None
    inflow: float | None = None
    unit1_power: float | None = None
    unit2_power: float | None = None
    unit3_power: float | None = None
    unit4_power: float | None = None
    target_mw: float | None = None


@router.post("/projects/{project_id}/twin/what-if")
def twin_what_if(project: ViewerProject, body: WhatIf, db: DB):
    """Egizakni o'zgartirilgan sharoitda hisoblash (sath, sarf, quvvat) — natija va xavfsizlik ko'rsatkichlari,
    optimal taqsimot; jonli ma'lumotga tegilmaydi (operatorni oldindan sinash, mashq)."""
    ov = {k: v for k, v in body.model_dump().items() if v is not None and k != "target_mw"}
    state = twin.compute(db, project, ov)
    state["dispatch"] = twin.optimal_dispatch(db, project, body.target_mw, ov)
    return state


class ForecastIn(BaseModel):
    """Kutilayotgan yog'in (ob-havo prognozi) — toshqin prognozi uchun."""

    rain_mm: float = Field(ge=0, le=2000)
    rain_hours: float = Field(default=24, ge=1, le=240)
    amc: str = "II"
    pattern: str | None = None
    snowmelt: bool = False
    air_temp: float | None = None
    glof: bool = False
    lake_mcm: float | None = None
    gate_opening: float | None = Field(None, ge=0, le=1)


@router.post("/projects/{project_id}/twin/forecast")
def twin_forecast(project: ViewerProject, body: ForecastIn, db: DB):
    """Toshqin prognozi: kutilayotgan yog'in + jonli sath/sarf + pasport → ombor sathi 3–5 kun, gerbdan oshish
    vaqti, oldindan sath tushirish tavsiyasi."""
    try:
        return twin.flood_forecast(db, project, body.model_dump())
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/projects/{project_id}/twin/dispatch")
def twin_dispatch(project: ViewerProject, db: DB, target_mw: float | None = None):
    """Bugungi optimal rejim: jonli napor va joriy (yoki berilgan) umumiy quvvat uchun agregatlar taqsimoti."""
    return twin.optimal_dispatch(db, project, target_mw)


@router.post("/projects/{project_id}/twin/run")
def twin_run(project: EngineerProject, db: DB):
    """Egizakni hozir hisoblab, virtual sensorlarga yozish (fon har 30 s da ham qiladi)."""
    return twin.publish(db, project)


@router.get("/projects/{project_id}/snapshot")
def snapshot(project: ViewerProject, db: DB, at: datetime):
    """Vaqt mashinasi: berilgan vaqtdagi barcha sensorlar qiymati (3D/sxema qayta ko'rish)."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return {"at": at.isoformat(), "sensors": twin.snapshot(db, project.id, at)}


# ---------- Aktivlar ----------


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    element_guid: str | None = None
    power_sensor_id: int | None = None
    base_run_hours: float = 0.0
    maintenance_interval_hours: float | None = None
    last_maintenance_at: datetime | None = None
    run_hours_at_maintenance: float = 0.0
    notes: str = ""
    config: dict = Field(default_factory=dict)


class AssetPatch(BaseModel):
    name: str | None = None
    element_guid: str | None = None
    power_sensor_id: int | None = None
    base_run_hours: float | None = None
    maintenance_interval_hours: float | None = None
    last_maintenance_at: datetime | None = None
    run_hours_at_maintenance: float | None = None
    notes: str | None = None
    config: dict | None = None


@router.get("/projects/{project_id}/assets")
def list_assets(project: ViewerProject, db: DB):
    return twin.asset_status(db, project)


@router.get("/projects/{project_id}/health")
def project_health(project: ViewerProject, db: DB):
    """Holat monitoringi: aktivlar sog'liq indeksi, tebranish zonasi (ISO 20816-5), harorat, FIK trendi,
    anomaliya, kavitatsiya (Toma), tavsiyalar."""
    return health.compute(db, project)


@router.post("/projects/{project_id}/health/run")
def project_health_run(project: EngineerProject, db: DB):
    return health.publish(db, project)


_CONFIG_KEYS = {
    "vibration_sensor_id",
    "bearing_temp_sensor_id",
    "machine_group",
    "temp_warn",
    "temp_alarm",
    "rated_speed_rpm",
    "runner_elev_m",
    "turbine_type",
    "rated_mva",
    "cos_phi",
    "ambient_c",
    "cooling",
}


def _check_config(db, project_id: int, cfg: dict) -> dict:
    """Holat monitoringi sozlamalari: faqat ruxsat etilgan kalitlar, sensorlar shu loyihaniki."""
    out = {k: v for k, v in (cfg or {}).items() if k in _CONFIG_KEYS}
    for k in ("vibration_sensor_id", "bearing_temp_sensor_id"):
        if out.get(k) not in (None, ""):
            s = db.get(Sensor, int(out[k]))
            if s is None or s.project_id != project_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor loyihada yo'q")
            out[k] = s.id
        elif k in out:
            out[k] = None
    if out.get("machine_group") not in (None, "") and int(out["machine_group"]) not in (1, 2, 3, 4):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "machine_group: 1–4")
    return out


@router.post("/projects/{project_id}/assets", status_code=201)
def create_asset(body: AssetIn, project: EngineerProject, user: CurrentUser, db: DB):
    if body.power_sensor_id is not None:
        s = db.get(Sensor, body.power_sensor_id)
        if s is None or s.project_id != project.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor loyihada yo'q")
    data = body.model_dump()
    data["config"] = _check_config(db, project.id, data.get("config") or {})
    a = Asset(project_id=project.id, **data)
    db.add(a)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="asset.create",
        target_type="asset",
        target_id=a.id,
        project_id=project.id,
        detail={"name": a.name},
    )
    db.commit()
    return next(x for x in twin.asset_status(db, project) if x["id"] == a.id)


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, user: CurrentUser, db: DB):
    from ..auth.deps import get_project_role, has_role

    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aktiv topilmadi")
    if not has_role(get_project_role(db, a.project_id, user), Role.engineer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Muhandis huquqi kerak")
    changes = body.model_dump(exclude_none=True)
    # Sensor faqat shu loyihaniki bo'lishi kerak (boshqa loyiha ma'lumotiga bog'lab bo'lmaydi)
    if "power_sensor_id" in changes:
        s = db.get(Sensor, changes["power_sensor_id"])
        if s is None or s.project_id != a.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor loyihada yo'q")
    if "config" in changes:
        changes["config"] = _check_config(
            db, a.project_id, {**(a.config or {}), **changes["config"]}
        )
    for k in AssetPatch.model_fields:  # faqat ruxsat etilgan maydonlar (project_id emas)
        if k in changes:
            setattr(a, k, changes[k])
    audit.log(
        db,
        user_id=user.id,
        action="asset.update",
        target_type="asset",
        target_id=a.id,
        project_id=a.project_id,
    )
    db.commit()
    return next(x for x in twin.asset_status(db, db.get(Project, a.project_id)) if x["id"] == a.id)


@router.post("/assets/{asset_id}/maintenance")
def record_maintenance(asset_id: int, user: CurrentUser, db: DB, note: str = ""):
    """Texnik xizmat o'tkazildi: hisoblagich nolga (ish soatlari shu paytdan)."""
    from ..auth.deps import get_project_role, has_role

    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aktiv topilmadi")
    if not has_role(get_project_role(db, a.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    project = db.get(Project, a.project_id)
    cur = next(x for x in twin.asset_status(db, project) if x["id"] == a.id)
    a.last_maintenance_at = utcnow()
    a.run_hours_at_maintenance = cur["run_hours_total"]
    if note:
        a.notes = (a.notes + "\n" if a.notes else "") + f"{utcnow().date()}: {note}"
    audit.log(
        db,
        user_id=user.id,
        action="asset.maintenance",
        target_type="asset",
        target_id=a.id,
        project_id=a.project_id,
        detail={"note": note, "run_hours": cur["run_hours_total"]},
    )
    db.commit()
    return next(x for x in twin.asset_status(db, project) if x["id"] == a.id)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, user: CurrentUser, db: DB):
    from ..auth.deps import get_project_role, has_role

    a = db.get(Asset, asset_id)
    if a is None:
        return
    if not has_role(get_project_role(db, a.project_id, user), Role.approver):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlovchi huquqi kerak")
    db.delete(a)
    db.commit()
