"""Raqamli egizak API: joriy holat, aktivlar (CRUD, holat), vaqt mashinasi, kunlik hisobot yuborish."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, require_project_role
from ..orm import Asset, AssetDocument, CalibrationRun, Project, Role, Sensor, utcnow
from . import calibration, health, kks, live, twin

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
    # H1: ierarxiya va kodlash
    parent_id: int | None = None
    kks_code: str | None = Field(default=None, max_length=32)
    taxonomy_level: str | None = None
    function_location: str = Field(default="", max_length=128)
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
    parent_id: int | None = None  # 0 — ildizga
    kks_code: str | None = None  # "" — o'chirish
    taxonomy_level: str | None = None
    function_location: str | None = None
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


# --------------------------------------------------------------- I1: model kalibrovkasi


class CalibrationIn(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="tarixiy oyna, kun")
    targets: list[Literal["penstock_roughness_mm", "max_efficiency"]] = Field(
        default_factory=lambda: ["penstock_roughness_mm", "max_efficiency"]
    )
    apply: bool = Field(default=False, description="natijani darhol qo'llash")


def _run_out(r: CalibrationRun) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "created_at": live._aware(r.created_at),
        "author": r.author.username if r.author else None,
        "window_from": live._aware(r.window_from),
        "window_to": live._aware(r.window_to),
        "n_points": r.n_points,
        "targets": list(r.targets or []),
        "status": r.status,
        "params_before": r.params_before or {},
        "params_after": r.params_after or {},
        "rmse_before": r.rmse_before,
        "rmse_after": r.rmse_after,
        "bias_after": r.bias_after,
        "improvement_pct": r.improvement_pct,
        "diagnostics": r.diagnostics or {},
        "applied": bool(r.applied),
        "note": r.note,
    }


@router.get("/projects/{project_id}/calibration")
def calibration_state(project: ViewerProject, db: DB, limit: int = 20):
    """Joriy kalibrovka, oxirgi qoldiq holati (drift) va kalibrovka tarixi."""
    rows = (
        db.query(CalibrationRun)
        .filter_by(project_id=project.id)
        .order_by(CalibrationRun.id.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "current": calibration.current(project),
        "residuals": calibration.residuals(db, project),
        "runs": [_run_out(r) for r in rows],
    }


@router.post("/projects/{project_id}/calibration/run")
def calibration_run(project: EngineerProject, body: CalibrationIn, user: CurrentUser, db: DB):
    """Kalibrovkani bajarish: tarixiy soatlik ma'lumotdan parametrlarni moslashtirish (eng kichik
    kvadratlar). Natija yozuv sifatida saqlanadi; `apply` bo'lsa egizak darhol shu parametrlar bilan."""
    rec = calibration.run(
        db, project, user.id, days=body.days, targets=tuple(body.targets), apply=body.apply
    )
    audit.log(
        db,
        user_id=user.id,
        action="twin.calibration",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"status": rec.status, "rmse_after": rec.rmse_after, "applied": rec.applied},
    )
    db.commit()
    db.refresh(rec)
    return _run_out(rec)


@router.post("/calibration/{run_id}/apply")
def calibration_apply(run_id: int, user: CurrentUser, db: DB):
    """Saqlangan kalibrovkani qo'llash (masalan, eski yozuvga qaytish)."""
    from ..auth.deps import get_project_role, has_role

    rec = db.get(CalibrationRun, run_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalibrovka topilmadi")
    project = db.get(Project, rec.project_id)
    if not has_role(get_project_role(db, project.id, user), Role.engineer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    try:
        calibration.apply_run(db, project, rec)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.log(
        db,
        user_id=user.id,
        action="twin.calibration_apply",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"run_id": rec.id},
    )
    db.commit()
    return {"current": calibration.current(project), "run": _run_out(rec)}


@router.delete("/projects/{project_id}/calibration")
def calibration_revert(project: EngineerProject, user: CurrentUser, db: DB):
    """Kalibrovkani bekor qilish — model IFC pasporti qiymatlariga qaytadi."""
    calibration.revert(db, project)
    audit.log(
        db,
        user_id=user.id,
        action="twin.calibration_revert",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={},
    )
    db.commit()
    return {"current": {}}


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
    # H3 — ISO 13374 qo'shimcha kanallari va chegaralari
    "shaft_vibration_sensor_id",
    "air_gap_sensor_id",
    "pd_sensor_id",
    "oil_water_sensor_id",
    "shaft_limits",
    "shaft_clearance_um",
    "air_gap_min_mm",
    "pd_warn",
    "pd_alarm",
    "oil_water_warn",
    "oil_water_alarm",
    "bearing",  # {n, d_mm, D_mm, alpha_deg} — nuqson chastotalari uchun geometriya
}
_SENSOR_CONFIG_KEYS = (
    "vibration_sensor_id",
    "bearing_temp_sensor_id",
    "shaft_vibration_sensor_id",
    "air_gap_sensor_id",
    "pd_sensor_id",
    "oil_water_sensor_id",
)


def _check_config(db, project_id: int, cfg: dict) -> dict:
    """Holat monitoringi sozlamalari: faqat ruxsat etilgan kalitlar, sensorlar shu loyihaniki."""
    out = {k: v for k, v in (cfg or {}).items() if k in _CONFIG_KEYS}
    for k in _SENSOR_CONFIG_KEYS:
        if out.get(k) not in (None, ""):
            s = db.get(Sensor, int(out[k]))
            if s is None or s.project_id != project_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor loyihada yo'q")
            out[k] = s.id
        elif k in out:
            out[k] = None
    if out.get("machine_group") not in (None, "") and int(out["machine_group"]) not in (1, 2, 3, 4):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "machine_group: 1–4")
    bearing = out.get("bearing")
    if bearing not in (None, "", {}):
        if not isinstance(bearing, dict) or not all(
            isinstance(bearing.get(k), (int, float)) and bearing.get(k, 0) > 0 for k in ("n", "d_mm", "D_mm")
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "bearing: {n, d_mm, D_mm} musbat sonlar (ixtiyoriy alpha_deg) — nuqson chastotalari uchun",
            )
    return out


def _check_hierarchy(db, project_id: int, data: dict, self_id: int | None = None) -> dict:
    """H1: KKS kodi grammatikasi, loyihada unikalligi; ota aktiv shu loyihaniki va halqa emas; daraja ISO 14224."""
    if "kks_code" in data:
        try:
            data["kks_code"] = kks.validate(data["kks_code"])
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        if data["kks_code"]:
            dup = db.query(Asset).filter_by(project_id=project_id, kks_code=data["kks_code"]).first()
            if dup is not None and dup.id != self_id:
                raise HTTPException(status.HTTP_409_CONFLICT, f"KKS kodi band: {data['kks_code']} ({dup.name})")
    if "taxonomy_level" in data:
        try:
            data["taxonomy_level"] = kks.level_for(data.get("kks_code"), data["taxonomy_level"])
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    if "parent_id" in data:
        if data["parent_id"] in (0, None):
            data["parent_id"] = None
        else:
            p = db.get(Asset, int(data["parent_id"]))
            if p is None or p.project_id != project_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ota aktiv loyihada yo'q")
            cur, hops = p, 0
            while cur is not None and hops < 100:
                if cur.id == self_id:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ierarxiya halqasi (aktiv o'zining avlodi bo'lolmaydi)")
                cur = db.get(Asset, cur.parent_id) if cur.parent_id else None
                hops += 1
    return data


@router.post("/projects/{project_id}/assets", status_code=201)
def create_asset(body: AssetIn, project: EngineerProject, user: CurrentUser, db: DB):
    if body.power_sensor_id is not None:
        s = db.get(Sensor, body.power_sensor_id)
        if s is None or s.project_id != project.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor loyihada yo'q")
    data = _check_hierarchy(db, project.id, body.model_dump())
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
    changes = _check_hierarchy(db, a.project_id, changes, self_id=a.id)
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


# --------------------------------------------------------------------------- G6: IFC dan aktivlar, aktiv hujjatlari


class AssetsFromIfcIn(BaseModel):
    version_id: int


@router.post("/projects/{project_id}/assets/from-ifc")
def assets_from_ifc(body: AssetsFromIfcIn, project: EngineerProject, user: CurrentUser, db: DB):
    """IFC versiyasidan aktiv registri → `Asset` yozuvlari (element_guid bo'yicha yangilanadi/yaratiladi):
    turbina, generator, transformator, zatvor, nasos; ishlab chiqaruvchi/model/seriya/kafolat config da."""
    from ..models import cobie, storage
    from ..orm import Version

    v = db.get(Version, body.version_id)
    if v is None or v.model.project_id != project.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu loyihaniki emas")
    try:
        reg = cobie.register_from_path(storage.resolve(v.file_sha256))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    res = cobie.sync_assets(db, project.id, reg)
    audit.log(db, user_id=user.id, action="asset.sync_ifc", target_type="project", target_id=project.id, project_id=project.id, detail={"version_id": v.id, **res})
    db.commit()
    return {**res, "components": reg["counts"]["components"], "assets": twin.asset_status(db, project)}


ASSET_DOC_KINDS = ("manual", "passport", "test", "commissioning", "other")
ASSET_DOC_EXTS = (".pdf", ".docx", ".xlsx", ".doc", ".xls", ".txt", ".md", ".csv", ".zip", ".png", ".jpg", ".jpeg")


class AssetDocOut(BaseModel):
    id: int
    asset_id: int
    kind: str
    title: str
    file_name: str
    file_size: int
    uploader_username: str
    created_at: datetime


def _asset_checked(db, asset_id: int, user, role: Role) -> Asset:
    from ..auth.deps import get_project_role, has_role

    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aktiv topilmadi")
    if not has_role(get_project_role(db, a.project_id, user), role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")
    return a


def _adoc_out(d: AssetDocument) -> AssetDocOut:
    return AssetDocOut(id=d.id, asset_id=d.asset_id, kind=d.kind, title=d.title, file_name=d.file_name, file_size=d.file_size, uploader_username=d.uploader.username, created_at=d.created_at)


@router.get("/assets/{asset_id}/documents", response_model=list[AssetDocOut])
def asset_documents(asset_id: int, user: CurrentUser, db: DB):
    _asset_checked(db, asset_id, user, Role.viewer)
    return [_adoc_out(d) for d in db.query(AssetDocument).filter_by(asset_id=asset_id).order_by(AssetDocument.id).all()]


@router.post("/assets/{asset_id}/documents", response_model=AssetDocOut, status_code=201)
def asset_document_upload(asset_id: int, file: UploadFile, user: CurrentUser, db: DB, kind: Annotated[str, Form()] = "other", title: Annotated[str, Form()] = ""):
    """Aktivga hujjat (operator+): qo'llanma, pasport, zavod sinov protokoli, ishga tushirish akti."""
    from ..config import get_settings
    from ..models import storage

    a = _asset_checked(db, asset_id, user, Role.operator)
    if kind not in ASSET_DOC_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"kind: {', '.join(ASSET_DOC_KINDS)}")
    name = file.filename or "hujjat"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ASSET_DOC_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ruxsat etilgan: {', '.join(ASSET_DOC_EXTS)}")
    try:
        sha, size = storage.store(file.file, ext=ext, max_bytes=get_settings().small_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(e)) from e
    d = AssetDocument(asset_id=a.id, kind=kind, title=title.strip() or name, file_name=name, file_sha256=sha, file_size=size, ext=ext, uploaded_by=user.id)
    db.add(d)
    db.flush()
    audit.log(db, user_id=user.id, action="asset.document.upload", target_type="asset", target_id=a.id, project_id=a.project_id, detail={"kind": kind, "title": d.title})
    db.commit()
    db.refresh(d)
    return _adoc_out(d)


@router.get("/assets/{asset_id}/documents/{doc_id}/file")
def asset_document_file(asset_id: int, doc_id: int, user: CurrentUser, db: DB):
    from fastapi.responses import FileResponse

    from ..models import storage

    _asset_checked(db, asset_id, user, Role.viewer)
    d = db.get(AssetDocument, doc_id)
    if d is None or d.asset_id != asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hujjat topilmadi")
    try:
        return FileResponse(storage.resolve(d.file_sha256, ext=d.ext), filename=d.file_name)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl topilmadi") from None


@router.delete("/assets/{asset_id}/documents/{doc_id}", status_code=204)
def asset_document_delete(asset_id: int, doc_id: int, user: CurrentUser, db: DB):
    a = _asset_checked(db, asset_id, user, Role.engineer)
    d = db.get(AssetDocument, doc_id)
    if d is None or d.asset_id != asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hujjat topilmadi")
    db.delete(d)
    audit.log(db, user_id=user.id, action="asset.document.delete", target_type="asset", target_id=a.id, project_id=a.project_id, detail={"doc_id": doc_id})
    db.commit()


# --------------------------------------------------------------------------- H1: aktiv daraxti, KKS import


@router.get("/projects/{project_id}/assets/tree")
def assets_tree(project: ViewerProject, db: DB):
    """Ierarxiya (H1): ildizdan avlodlarga; har tugunda holat (texnik xizmat), sog'liq indeksi (health) va
    avlodlardan agregatsiya (eng yomon holat/eng past indeks — uskuna sog'ligi komponentlardan)."""
    status_by = {x["id"]: x for x in twin.asset_status(db, project)}
    try:
        health_by = {h["asset_id"]: h for h in health.compute(db, project).get("assets", [])}
    except Exception:  # noqa: BLE001 — sog'liq hisobi bo'lmasa daraxt baribir ko'rinadi
        health_by = {}
    rows = db.query(Asset).filter_by(project_id=project.id).order_by(Asset.kks_code, Asset.name).all()
    children: dict[int | None, list[Asset]] = {}
    for a in rows:
        children.setdefault(a.parent_id if a.parent_id in {r.id for r in rows} else None, []).append(a)
    order = {"ok": 0, "due": 1, "overdue": 2}

    def node(a: Asset) -> dict:
        kids = [node(c) for c in children.get(a.id, [])]
        st = status_by.get(a.id, {})
        h = health_by.get(a.id)
        own_score = h.get("score") if h else None
        scores = [k["agg_score"] for k in kids if k["agg_score"] is not None] + ([own_score] if own_score is not None else [])
        statuses = [k["agg_status"] for k in kids] + [st.get("status", "ok")]
        return {
            "id": a.id,
            "name": a.name,
            "kks_code": a.kks_code,
            "taxonomy_level": a.taxonomy_level,
            "function_location": a.function_location,
            "element_guid": a.element_guid,
            "kks": (kks.parse(a.kks_code) if a.kks_code else None),
            "status": st.get("status"),
            "running": st.get("running"),
            "score": own_score,
            "level": h.get("level") if h else None,
            "agg_score": min(scores) if scores else None,
            "agg_status": max(statuses, key=lambda x: order.get(x, 0)),
            "children": kids,
        }

    return {"roots": [node(a) for a in children.get(None, [])], "count": len(rows), "levels": list(kks.LEVELS), "level_labels": kks.LEVEL_LABEL}


@router.post("/projects/{project_id}/assets/import-kks")
def assets_import_kks(project: EngineerProject, user: CurrentUser, db: DB, file: UploadFile):
    """CSV import (H1): ustunlar kks_code, name, [parent_kks], [taxonomy_level], [element_guid], [sensor_key],
    [function_location]. Kod bo'yicha mavjud aktiv yangilanadi, yo'q — yaratiladi; ota kod bo'yicha
    bog'lanadi (ro'yxatdagi tartibdan qat'i nazar), sensor_key — sensor KKS kodini ham qo'yadi."""
    import csv
    import io

    from ..config import get_settings

    raw = file.file.read(get_settings().small_upload_mb * 1024 * 1024 + 1)
    if len(raw) > get_settings().small_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CSV juda katta")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))
    if not rows or "kks_code" not in rows[0]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV: kks_code, name[, parent_kks, taxonomy_level, element_guid, sensor_key, function_location]")
    by_code = {a.kks_code: a for a in db.query(Asset).filter_by(project_id=project.id).all() if a.kks_code}
    created = updated = 0
    errors: list[str] = []
    parsed: list[tuple[dict, str]] = []
    for i, r in enumerate(rows, start=2):
        try:
            code = kks.validate(r.get("kks_code"))
            if not code:
                raise ValueError("kks_code bo'sh")
            level = kks.level_for(code, (r.get("taxonomy_level") or "").strip() or None)
        except ValueError as e:
            errors.append(f"{i}-qator: {e}")
            continue
        parsed.append((r, code))
        a = by_code.get(code)
        if a is None:
            a = Asset(project_id=project.id, name=(r.get("name") or code).strip(), kks_code=code, taxonomy_level=level)
            db.add(a)
            db.flush()
            by_code[code] = a
            created += 1
        else:
            if (r.get("name") or "").strip():
                a.name = r["name"].strip()
            a.taxonomy_level = level
            updated += 1
        if (r.get("element_guid") or "").strip():
            a.element_guid = r["element_guid"].strip()
        if (r.get("function_location") or "").strip():
            a.function_location = r["function_location"].strip()[:128]
        if (r.get("sensor_key") or "").strip():
            s = db.query(Sensor).filter_by(project_id=project.id, key=r["sensor_key"].strip()).first()
            if s is not None:
                s.kks_code = code
    # ota bog'lanishi (ikkinchi o'tish — barcha kodlar mavjud)
    for r, code in parsed:
        pk = (r.get("parent_kks") or "").strip()
        parent = None
        if pk:
            try:
                parent = by_code.get(kks.validate(pk))
            except ValueError:
                parent = None
            if parent is None:
                errors.append(f"{code}: ota kod topilmadi ({pk})")
        elif kks.parent_code(code):
            parent = by_code.get(kks.parent_code(code))  # koddan kelib chiqadigan ota (tizim → uskuna → komponent)
        if parent is not None and parent.id != by_code[code].id:
            by_code[code].parent_id = parent.id
    audit.log(db, user_id=user.id, action="asset.import_kks", target_type="project", target_id=project.id, project_id=project.id, detail={"created": created, "updated": updated, "errors": len(errors)})
    db.commit()
    return {"created": created, "updated": updated, "errors": errors}


@router.get("/kks/systems")
def kks_systems(_: CurrentUser):
    """KKS tizim kalitlari (VGB-B 105, GES qismi) va ISO 14224 darajalari."""
    return {"systems": kks.SYSTEM_KEYS, "levels": list(kks.LEVELS), "level_labels": kks.LEVEL_LABEL}
