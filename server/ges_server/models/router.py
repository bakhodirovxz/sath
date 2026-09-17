from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import audit
from ..auth.deps import (
    DB,
    CurrentUser,
    check_project_role,
    get_project_role,
    has_role,
    require_project_role,
)
from ..config import get_settings
from ..orm import Model, Project, Role, Version, VersionState
from . import ifc_meta, storage

router = APIRouter(prefix="/api", tags=["models"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class ModelOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    version_count: int = 0
    latest_version_id: int | None = None
    published_version_id: int | None = None
    safety: dict | None = None  # oxirgi xavfsizlik tekshiruvi xulosasi (ball, hisob, versiya)

    model_config = {"from_attributes": True}


class VersionOut(BaseModel):
    id: int
    model_id: int
    number: int
    parent_id: int | None
    author_id: int
    author_username: str
    message: str
    tag: str = ""
    file_sha256: str
    file_name: str
    file_size: int
    state: VersionState
    meta: dict
    created_at: datetime

    model_config = {"from_attributes": True}


def _model_out(m: Model) -> ModelOut:
    latest = m.versions[-1] if m.versions else None
    published = next((v for v in m.versions if v.state == VersionState.published), None)
    return ModelOut(
        id=m.id,
        project_id=m.project_id,
        name=m.name,
        description=m.description,
        version_count=len(m.versions),
        latest_version_id=latest.id if latest else None,
        published_version_id=published.id if published else None,
        safety=_safety_last(m.id),
    )


def _safety_last(model_id: int) -> dict | None:
    from ..sim import safety

    return safety.last(model_id)


def version_out(v: Version) -> VersionOut:
    return VersionOut(
        id=v.id,
        model_id=v.model_id,
        number=v.number,
        parent_id=v.parent_id,
        author_id=v.author_id,
        author_username=v.author.username,
        message=v.message,
        tag=v.tag or "",
        file_sha256=v.file_sha256,
        file_name=v.file_name,
        file_size=v.file_size,
        state=v.state,
        meta=v.meta,
        created_at=v.created_at,
    )


def get_model_checked(db, model_id: int, user, required: Role) -> Model:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model topilmadi")
    check_project_role(db, model.project_id, user, required)
    return model


def get_version_checked(db, version_id: int, user, required: Role) -> Version:
    version = db.get(Version, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versiya topilmadi")
    check_project_role(db, version.model.project_id, user, required)
    return version


# --- Modellar ---


@router.get("/projects/{project_id}/models", response_model=list[ModelOut])
def list_models(project: ViewerProject):
    return [_model_out(m) for m in project.models]


@router.post("/projects/{project_id}/models", response_model=ModelOut, status_code=201)
def create_model(body: ModelCreate, project: EngineerProject, user: CurrentUser, db: DB):
    if any(m.name == body.name for m in project.models):
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu loyihada shunday model mavjud")
    model = Model(project_id=project.id, **body.model_dump())
    db.add(model)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="model.create",
        target_type="model",
        target_id=model.id,
        project_id=project.id,
        detail={"name": model.name},
    )
    db.commit()
    return _model_out(model)


@router.get("/models/{model_id}", response_model=ModelOut)
def get_model(model_id: int, user: CurrentUser, db: DB):
    return _model_out(get_model_checked(db, model_id, user, Role.viewer))


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: int, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.approver)
    audit.log(
        db,
        user_id=user.id,
        action="model.delete",
        target_type="model",
        target_id=model.id,
        project_id=model.project_id,
        detail={"name": model.name},
    )
    # Versiyalarga bog'liq yozuvlar (FK cascade siz): sim vazifalari, issue lar, tasdiqlash so'rovlari — avval
    from ..orm import ChangeRequest, Issue, SimJob

    for cls in (SimJob, Issue, ChangeRequest):
        for row in db.query(cls).filter_by(model_id=model.id).all():
            db.delete(row)
    for v in model.versions:  # ota-bola zanjiri (parent_id) — o'chirish tartibi muhim bo'lmasin
        v.parent_id = None
    db.flush()
    db.delete(model)
    db.commit()


# --- Versiyalar ---


@router.get("/models/{model_id}/versions", response_model=list[VersionOut])
def list_versions(model_id: int, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.viewer)
    return [version_out(v) for v in reversed(model.versions)]


@router.post("/models/{model_id}/versions", response_model=VersionOut, status_code=201)
def upload_version(
    model_id: int,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    background: BackgroundTasks,
    message: Annotated[str, Form()] = "",
    parent_id: Annotated[int | None, Form()] = None,
):
    """Commit: yangi IFC versiya yuklash. parent_id berilmasa oxirgi versiya ota bo'ladi.
    Yuklangach fonda geometriya tahlili (QTO, to'qnashuvlar) oldindan hisoblanadi."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    if not (file.filename or "").lower().endswith(".ifc"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faqat .ifc fayl qabul qilinadi")

    settings = get_settings()
    try:
        sha, size = storage.store(file.file, max_bytes=settings.max_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(e)) from e

    try:
        meta = ifc_meta.extract(storage.resolve(sha))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    if parent_id is not None:
        parent = db.get(Version, parent_id)
        if parent is None or parent.model_id != model.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "parent_id shu modelga tegishli emas")
    else:
        parent = model.versions[-1] if model.versions else None

    next_number = (
        db.query(func.coalesce(func.max(Version.number), 0)).filter_by(model_id=model.id).scalar()
        + 1
    )
    version = Version(
        model_id=model.id,
        number=next_number,
        parent_id=parent.id if parent else None,
        author_id=user.id,
        message=message,
        file_sha256=sha,
        file_name=file.filename,
        file_size=size,
        meta=meta,
    )
    db.add(version)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="version.create",
        target_type="version",
        target_id=version.id,
        project_id=model.project_id,
        detail={"model_id": model.id, "number": version.number, "message": message},
    )
    db.commit()
    db.refresh(version)
    if settings.fragments_enabled:
        from . import fragments

        background.add_task(fragments.convert, storage.resolve(sha), sha)
    if settings.precompute_geometry:
        from . import geometry

        background.add_task(geometry.precompute, storage.resolve(sha), sha)
    return version_out(version)


@router.get("/versions/{version_id}/fragments")
def version_fragments(version_id: int, user: CurrentUser, db: DB):
    """Tayyor fragments (.frag) — brauzer IFC o'rniga shuni yuklaydi (tez). Hali yo'q bo'lsa 404;
    konvertatsiya mumkin bo'lsa shu so'rovda bajariladi (kesh)."""
    from . import fragments

    version = get_version_checked(db, version_id, user, Role.viewer)
    if not get_settings().fragments_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fragments o'chirilgan")
    out = fragments.frag_path(version.file_sha256)
    if not out.exists():
        try:
            path = storage.resolve(version.file_sha256)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
        if fragments.convert(path, version.file_sha256) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "fragments tayyor emas (Node/tool yo'q)")
    return FileResponse(
        out,
        media_type="application/octet-stream",
        filename=f"{version.model.name}_v{version.number}.frag",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/versions/{version_id}", response_model=VersionOut)
def get_version(version_id: int, user: CurrentUser, db: DB):
    return version_out(get_version_checked(db, version_id, user, Role.viewer))


class VersionPatch(BaseModel):
    message: str | None = None
    tag: str | None = Field(None, max_length=64)


@router.patch("/versions/{version_id}", response_model=VersionOut)
def update_version(version_id: int, body: VersionPatch, user: CurrentUser, db: DB):
    """Izoh (muallif yoki tasdiqlovchi) va yorliq/teg (tasdiqlovchi) — fayl o'zgarmaydi."""
    v = get_version_checked(db, version_id, user, Role.viewer)
    project_id = v.model.project_id
    approver = has_role(get_project_role(db, project_id, user), Role.approver)
    if body.message is not None:
        if v.author_id != user.id and not approver:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Izohni muallif yoki tasdiqlovchi o'zgartiradi"
            )
        v.message = body.message
    if body.tag is not None:
        if not approver:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Yorliqni tasdiqlovchi qo'yadi")
        v.tag = body.tag.strip()
    audit.log(
        db,
        user_id=user.id,
        action="version.update",
        target_type="version",
        target_id=v.id,
        project_id=project_id,
        detail=body.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(v)
    return version_out(v)


@router.post("/versions/{version_id}/restore", response_model=VersionOut, status_code=201)
def restore_version(version_id: int, user: CurrentUser, db: DB, background: BackgroundTasks):
    """Eski versiyani qayta tiklash: fayli bilan yangi (oxirgi) versiya yaratiladi (git revert kabi),
    ota — joriy oxirgi versiya, izoh — qaysi versiyadan. Tarix o'chmaydi."""
    src = get_version_checked(db, version_id, user, Role.engineer)
    model = src.model
    last = model.versions[-1] if model.versions else None
    if last is not None and last.id == src.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu allaqachon oxirgi versiya")
    number = (
        db.query(func.coalesce(func.max(Version.number), 0)).filter_by(model_id=model.id).scalar()
        + 1
    )
    v = Version(
        model_id=model.id,
        number=number,
        parent_id=last.id if last else None,
        author_id=user.id,
        message=f"v{src.number} dan qayta tiklandi: {src.message}".strip(),
        file_sha256=src.file_sha256,
        file_name=src.file_name,
        file_size=src.file_size,
        meta=src.meta,
    )
    db.add(v)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="version.restore",
        target_type="version",
        target_id=v.id,
        project_id=model.project_id,
        detail={"from_version_id": src.id, "from_number": src.number, "number": number},
    )
    db.commit()
    db.refresh(v)
    return version_out(v)


@router.get("/versions/{version_id}/file")
def download_version(version_id: int, user: CurrentUser, db: DB):
    version = get_version_checked(db, version_id, user, Role.viewer)
    try:
        path = storage.resolve(version.file_sha256)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    return FileResponse(
        path,
        media_type="application/x-step",
        filename=f"{version.model.name}_v{version.number}.ifc",
    )


# ---------- BIM tekshiruvlar: hajm-miqdor (QTO), to'qnashuvlar ----------


def _version_path(db, version_id: int, user):
    version = get_version_checked(db, version_id, user, Role.viewer)
    try:
        return version, storage.resolve(version.file_sha256)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None


@router.get("/versions/{version_id}/qto")
def version_qto(
    version_id: int,
    user: CurrentUser,
    db: DB,
    format: str = "json",
):
    """Hajm-miqdor hisobi (IfcOpenShell geometriyasidan): har element hajmi/sirti/o'lchamlari,
    tur va qavat bo'yicha jamlanma; ?format=csv — Excel uchun. Natija fayl bo'yicha keshlanadi."""
    from . import geometry

    version, path = _version_path(db, version_id, user)
    data = geometry.cached(version.file_sha256, "qto", lambda: geometry.compute_qto(path))
    if format == "csv":
        import csv
        import io

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "guid",
                "tur",
                "nom",
                "qavat",
                "material",
                "hajm m3",
                "sirt m2",
                "asos m2",
                "L m",
                "W m",
                "H m",
            ]
        )
        for r in data["elements"]:
            w.writerow(
                [
                    r["guid"],
                    r["type"],
                    r["name"],
                    r["storey"],
                    r["material"],
                    r["volume_m3"],
                    r["area_m2"],
                    r["footprint_m2"],
                    r["length_m"],
                    r["width_m"],
                    r["height_m"],
                ]
            )
        w.writerow([])
        w.writerow(["Tur", "soni", "hajm m3", "sirt m2"])
        for t, b in data["by_type"].items():
            w.writerow([t, b["count"], b["volume_m3"], b["area_m2"]])
        from fastapi.responses import Response

        return Response(
            "﻿" + buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="qto_{version.model.name}_v{version.number}.csv"'
            },
        )
    return data


@router.get("/versions/{version_id}/clashes")
def version_clashes(
    version_id: int,
    user: CurrentUser,
    db: DB,
    kind: str | None = None,
    types_a: str | None = None,
    types_b: str | None = None,
):
    """To'qnashuvlar (clash detection): hard — sirtlar kesishadi, possible — ichma-ich/aniq emas,
    touch — tegib turadi. types_a/types_b — vergul bilan IFC turlari (masalan IfcWall,IfcPipeSegment)
    — faqat shu guruhlar orasidagi juftlar."""
    from . import geometry

    version, path = _version_path(db, version_id, user)
    ta = [t for t in (types_a or "").split(",") if t] or None
    tb = [t for t in (types_b or "").split(",") if t] or None
    key = "clash" if not (ta or tb) else f"clash_{'+'.join(ta or [])}_{'+'.join(tb or [])}"
    data = geometry.cached(
        version.file_sha256, key, lambda: geometry.compute_clashes(path, 0.0, ta, tb)
    )
    if kind:
        data = {**data, "clashes": [c for c in data["clashes"] if c["kind"] == kind]}
    return data
