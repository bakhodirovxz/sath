"""Holat monitoringi API (H3, ISO 13374): spektr yozuvlari (DA), tashqi tizim natijalari (SD/HA/PA)
va aktiv bo'yicha blok natijalari.

Rollar: ko'rish — ko'ruvchi; spektr va tashqi natija yuborish — muhandis yoki gateway (loyiha ingest
kaliti bilan, `keys.project_from_ingest_key` — SCADA/CM gateway'i odatda foydalanuvchi emas).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .. import audit
from ..auth.deps import (
    DB,
    CurrentUser,
    get_project_role,
    has_role,
    require_project_role,
    user_from_token,
)
from ..orm import Asset, CmResult, Project, Role, Sensor, Spectrum
from . import cm, keys, live, twin

router = APIRouter(prefix="/api", tags=["cm"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]

MAX_LINES = 8192


class SpectrumIn(BaseModel):
    asset_id: int | None = None
    sensor_key: str | None = Field(default=None, max_length=64)
    kind: Literal["spectrum", "envelope", "orbit", "waveform"] = "spectrum"
    unit: str = Field(default="mm/s", max_length=16)
    rpm: float | None = Field(default=None, ge=0, le=10000)
    f_min: float = Field(default=0, ge=0)
    f_max: float = Field(default=0, ge=0)
    values: list[float] = Field(min_length=2, max_length=MAX_LINES)
    freqs: list[float] | None = Field(default=None, max_length=MAX_LINES)
    ts: datetime | None = None
    source: str = Field(default="", max_length=64)
    meta: dict = Field(default_factory=dict)

    @field_validator("values", "freqs")
    @classmethod
    def _finite(cls, v):
        if v is not None and any(x != x or x in (float("inf"), float("-inf")) for x in v):
            raise ValueError("Qiymatlar chekli son bo'lishi kerak")
        return v


class SpectrumOut(BaseModel):
    id: int
    asset_id: int | None
    sensor_id: int | None
    ts: datetime
    kind: str
    unit: str
    rpm: float | None
    f_min: float
    f_max: float
    n_lines: int
    source: str
    meta: dict
    values: list[float] | None = None
    freqs: list[float] | None = None
    features: dict | None = None


class CmResultIn(BaseModel):
    asset_id: int
    source: str = Field(min_length=1, max_length=64, description="tashqi tizim nomi")
    block: Literal["SD", "HA", "PA"] = "HA"
    state: Literal["normal", "alert", "alarm", "unknown"] = "unknown"
    health_score: float | None = Field(default=None, ge=0, le=100)
    rul_days: float | None = Field(default=None, ge=0, le=100000)
    diagnosis: str = Field(default="", max_length=300)
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_hours: float = Field(default=24, gt=0, le=8760)
    ts: datetime | None = None
    detail: dict = Field(default_factory=dict)


class CmResultOut(BaseModel):
    id: int
    project_id: int
    asset_id: int
    source: str
    block: str
    ts: datetime
    state: str
    health_score: float | None
    rul_days: float | None
    diagnosis: str
    confidence: float | None
    valid_hours: float
    detail: dict


def _writer_project(
    project_id: int,
    db: DB,
    x_ingest_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Project:
    """Yozish huquqi: X-Ingest-Key (CM gateway'i) yoki foydalanuvchi tokeni (muhandis+) —
    o'lchov yuborish bilan bir xil qoida (`POST /readings`)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    if x_ingest_key:
        keys.verify(db, project, "ingest", x_ingest_key)  # 401/403 tashlaydi
        db.commit()
        return project
    user = (
        user_from_token(db, authorization[7:])
        if authorization and authorization.lower().startswith("bearer ")
        else None
    )
    if (
        user is None
        or not user.is_active
        or not has_role(get_project_role(db, project.id, user), Role.engineer)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Muhandis huquqi yoki ingest kaliti kerak")
    return project


WriterProject = Annotated[Project, Depends(_writer_project)]


def _check_asset(db, project_id: int, asset_id: int | None) -> Asset | None:
    if asset_id is None:
        return None
    a = db.get(Asset, asset_id)
    if a is None or a.project_id != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aktiv loyihada yo'q")
    return a


def _spec_out(sp: Spectrum, values: bool = False, features: dict | None = None) -> SpectrumOut:
    return SpectrumOut(
        id=sp.id,
        asset_id=sp.asset_id,
        sensor_id=sp.sensor_id,
        ts=live._aware(sp.ts),
        kind=sp.kind,
        unit=sp.unit,
        rpm=sp.rpm,
        f_min=sp.f_min,
        f_max=sp.f_max,
        n_lines=sp.n_lines,
        source=sp.source,
        meta=sp.meta or {},
        values=[float(v) for v in (sp.values or [])] if values else None,
        freqs=[float(f) for f in sp.freqs] if values and sp.freqs else None,
        features=features,
    )


@router.post("/projects/{project_id}/cm/spectra", response_model=SpectrumOut, status_code=201)
def add_spectrum(project: WriterProject, body: SpectrumIn, db: DB):
    """Spektr/envelope/orbita yozuvini saqlash (DA bloki). Chastota o'qi: `f_min`..`f_max` bir tekis
    to'r yoki aniq `freqs` (uzunligi `values` bilan bir xil)."""
    _check_asset(db, project.id, body.asset_id)
    if body.freqs is not None and len(body.freqs) != len(body.values):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "freqs va values uzunligi bir xil bo'lsin")
    if body.freqs is None and body.f_max <= body.f_min:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "f_max > f_min bo'lsin (yoki freqs bering)")
    sensor = None
    if body.sensor_key:
        sensor = db.query(Sensor).filter_by(project_id=project.id, key=body.sensor_key).first()
        if sensor is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sensor topilmadi: {body.sensor_key}")
    sp = Spectrum(
        project_id=project.id,
        asset_id=body.asset_id,
        sensor_id=sensor.id if sensor else None,
        ts=body.ts or datetime.now(timezone.utc),
        kind=body.kind,
        unit=body.unit,
        rpm=body.rpm,
        f_min=body.f_min if body.freqs is None else min(body.freqs),
        f_max=body.f_max if body.freqs is None else max(body.freqs),
        n_lines=len(body.values),
        values=body.values,
        freqs=body.freqs,
        source=body.source,
        meta=body.meta,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return _spec_out(sp)


@router.get("/projects/{project_id}/cm/spectra", response_model=list[SpectrumOut])
def list_spectra(project: ViewerProject, db: DB, asset_id: int | None = None, limit: int = 50):
    q = db.query(Spectrum).filter(Spectrum.project_id == project.id)
    if asset_id:
        q = q.filter(Spectrum.asset_id == asset_id)
    rows = q.order_by(Spectrum.ts.desc()).limit(min(limit, 500)).all()
    return [_spec_out(sp) for sp in rows]


@router.get("/cm/spectra/{spectrum_id}", response_model=SpectrumOut)
def get_spectrum(spectrum_id: int, user: CurrentUser, db: DB):
    """Bitta spektr: qiymatlar va DM bloki xususiyatlari (cho'qqilar, garmonikalar, podshipnik chastotalari)."""
    sp = db.get(Spectrum, spectrum_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Spektr topilmadi")
    if not has_role(get_project_role(db, sp.project_id, user), Role.viewer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    cfg = (sp.asset.config or {}) if sp.asset else {}
    feats = cm.dm.spectrum_features(sp, cfg.get("bearing"), float(cfg.get("rated_speed_rpm") or 0) or None)
    feats = {**feats, "ts": live._aware(feats["ts"]).isoformat()}
    return _spec_out(sp, values=True, features=feats)


@router.delete("/cm/spectra/{spectrum_id}", status_code=204)
def delete_spectrum(spectrum_id: int, user: CurrentUser, db: DB):
    sp = db.get(Spectrum, spectrum_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Spektr topilmadi")
    if not has_role(get_project_role(db, sp.project_id, user), Role.engineer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    db.delete(sp)
    db.commit()


@router.post("/projects/{project_id}/cm/results", response_model=CmResultOut, status_code=201)
def add_cm_result(project: WriterProject, body: CmResultIn, db: DB):
    """Tashqi holat monitoringi tizimi natijasi (SD/HA/PA bloki) — sog'liq indeksiga qo'shiladi.
    `valid_hours` o'tgach natija hisobga olinmaydi (eskirgan baho sog'liqni ushlab turmasin)."""
    _check_asset(db, project.id, body.asset_id)
    r = CmResult(
        project_id=project.id,
        asset_id=body.asset_id,
        source=body.source,
        block=body.block,
        ts=body.ts or datetime.now(timezone.utc),
        state=body.state,
        health_score=body.health_score,
        rul_days=body.rul_days,
        diagnosis=body.diagnosis,
        confidence=body.confidence,
        valid_hours=body.valid_hours,
        detail=body.detail,
    )
    db.add(r)
    db.flush()
    audit.log(
        db,
        user_id=None,
        action="cm.result",
        target_type="asset",
        target_id=body.asset_id,
        project_id=project.id,
        detail={"source": body.source, "block": body.block, "state": body.state, "score": body.health_score},
    )
    db.commit()
    db.refresh(r)
    return CmResultOut(
        id=r.id,
        project_id=r.project_id,
        asset_id=r.asset_id,
        source=r.source,
        block=r.block,
        ts=live._aware(r.ts),
        state=r.state,
        health_score=r.health_score,
        rul_days=r.rul_days,
        diagnosis=r.diagnosis,
        confidence=r.confidence,
        valid_hours=r.valid_hours,
        detail=r.detail or {},
    )


@router.get("/projects/{project_id}/cm/results", response_model=list[CmResultOut])
def list_cm_results(project: ViewerProject, db: DB, asset_id: int | None = None, limit: int = 100):
    q = db.query(CmResult).filter(CmResult.project_id == project.id)
    if asset_id:
        q = q.filter(CmResult.asset_id == asset_id)
    rows = q.order_by(CmResult.ts.desc()).limit(min(limit, 500)).all()
    return [
        CmResultOut(
            id=r.id,
            project_id=r.project_id,
            asset_id=r.asset_id,
            source=r.source,
            block=r.block,
            ts=live._aware(r.ts),
            state=r.state,
            health_score=r.health_score,
            rul_days=r.rul_days,
            diagnosis=r.diagnosis,
            confidence=r.confidence,
            valid_hours=r.valid_hours,
            detail=r.detail or {},
        )
        for r in rows
    ]


@router.get("/assets/{asset_id}/cm")
def asset_cm(asset_id: int, user: CurrentUser, db: DB):
    """Aktiv bo'yicha ISO 13374 zanjiri natijasi: DA/DM/SD/HA/PA/AG bloklari bitta javobda."""
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aktiv topilmadi")
    if not has_role(get_project_role(db, a.project_id, user), Role.viewer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    project = db.get(Project, a.project_id)
    sensors = db.query(Sensor).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, sensors)
    return cm.asset_health(db, project, a, twin.compute(db, project), slots)
