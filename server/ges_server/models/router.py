import functools
import random
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .. import audit, jobs, ratelimit
from ..auth.deps import (
    DB,
    AdminUser,
    CurrentUser,
    check_project_role,
    get_project_role,
    has_role,
    require_project_role,
)
from ..config import get_settings
from ..downloads import content_disposition
from ..orm import Federation, Job, JobStatus, Model, Project, Role, Version, VersionState, utcnow
from . import classification, cobie, derived, federation, ifc_meta, ifc_schema, iso19650, storage
from . import crs as crs_mod

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
    ids_status: str | None = None  # G2: pass | fail | error | None
    suitability_code: str | None = None  # G4: S0–S7 / A1–An / B1–Bn / CR / PR
    revision_code: str | None = None  # G4: P01… / C01…
    suitability_label: str = ""

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


_VERSION_RETRIES = 8


def _next_number(db, model_id: int) -> int:
    """Keyingi versiya raqami (max+1). Alohida funksiya — poyga testi uchun to'siq qo'yiladi."""
    return (
        db.query(func.coalesce(func.max(Version.number), 0)).filter_by(model_id=model_id).scalar()
        + 1
    )


# --- Versiya yaratish: yagona yo'l (VCS-01/02) ---

PURGE_GRACE_S = 600  # VCS-06: tozalangan model fayllari — shundan eski bo'lsa darhol o'chiriladi
HEAD = object()  # parent_id = joriy oxirgi versiya (yozish paytida o'qiladi)
ANY = object()  # expected_head tekshirilmaydi
HEAD_MOVED_MSG = "Model yangilangan — boshqa foydalanuvchi yangi versiya yozdi. Avval yangilang (oxirgi versiyani oling)"


class HeadMoved(Exception):
    """Optimistic concurrency: klient ko'rgan oxirgi versiya endi oxirgi emas (VCS-01)."""

    def __init__(self, head_id: int | None):
        super().__init__(head_id)
        self.head_id = head_id


def head_conflict_response(fn):
    """Endpoint dekoratori: `HeadMoved` → 409 `{detail, head_id}` (klient yangilab, qayta urinadi)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HeadMoved as e:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": HEAD_MOVED_MSG, "head_id": e.head_id},
                headers={"X-Head-Id": str(e.head_id or "")},
            )

    return wrapper


def head_version(db, model_id: int) -> Version | None:
    """Modelning oxirgi versiyasi — DB dan (sessiyadagi eskirgan `model.versions` emas)."""
    return db.query(Version).filter_by(model_id=model_id).order_by(Version.number.desc()).first()


def check_head(db, model_id: int, expected_id: int | None) -> Version | None:
    """expected_id oxirgi versiya bo'lmasa `HeadMoved` (None — model bo'sh bo'lishi kutiladi)."""
    head = head_version(db, model_id)
    if (head.id if head else None) != expected_id:
        raise HeadMoved(head.id if head else None)
    return head


def create_version(
    db,
    *,
    model_id: int,
    user,
    parent_id=HEAD,
    expected_head=ANY,
    file_sha256: str,
    file_name: str,
    file_size: int,
    meta: dict,
    message: str,
    action: str = "version.create",
    detail: dict | None = None,
    on_insert: Callable[[Version], None] | None = None,
) -> Version:
    """Yangi versiya yozuvi — upload, restore, klassifikatsiya, draft commit va importlar uchun yagona yo'l.

    - `parent_id`: HEAD — joriy oxirgi versiya; int — aniq ota; None — ildiz (yangi IFC).
    - `expected_head`: ANY — tekshirilmaydi; int/None — yozish paytida oxirgi versiya shu bo'lishi shart,
      aks holda `HeadMoved` (409, tarmoqlanish jimgina bo'lmaydi — VCS-01).
    - Raqam: max+1; parallel yozuvda `UniqueConstraint(model_id, number)` IntegrityError beradi → rollback,
      qisqa kutish va qayta urinish (har urinishda oxirgi versiya qayta tekshiriladi). Tugasa 409 (VCS-02).
    - ISO 19650: har yangi versiya S0 (WIP) va keyingi P reviziya (upload bilan bir xil).
    - `on_insert(v)` — shu tranzaksiyada qo'shimcha o'zgarishlar (masalan qoralamalarni o'chirish).
    Fayl oldindan saqlangan (idempotent, content-addressed) — qayta urinish faylga tegmaydi."""
    version = None
    for attempt in range(_VERSION_RETRIES):
        try:
            model = db.get(Model, model_id)
            if model is None or model.deleted_at is not None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Model topilmadi")
            if expected_head is not ANY:
                check_head(db, model_id, expected_head)
            if parent_id is HEAD:
                head = head_version(db, model_id)
                pid = head.id if head else None
            else:
                pid = parent_id
            revisions = [r for (r,) in db.query(Version.revision_code).filter_by(model_id=model_id).all()]
            version = Version(
                model_id=model_id,
                number=_next_number(db, model_id),
                parent_id=pid,
                author_id=user.id,
                message=message,
                file_sha256=file_sha256,
                file_name=file_name,
                file_size=file_size,
                meta=meta,
                suitability_code=iso19650.DEFAULT[VersionState.wip],
                revision_code=iso19650.next_revision(revisions, "P"),
            )
            db.add(version)
            db.flush()
            if on_insert is not None:
                on_insert(version)
            audit.log(
                db,
                user_id=user.id,
                action=action,
                target_type="version",
                target_id=version.id,
                project_id=model.project_id,
                detail={"model_id": model_id, "number": version.number, **(detail or {})},
            )
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == _VERSION_RETRIES - 1:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Parallel yozuv — versiya raqami band, qayta urinib ko'ring"
                ) from None
            time.sleep(random.uniform(0.005, 0.03) * (attempt + 1))
        except (HeadMoved, HTTPException):
            db.rollback()
            raise
    db.refresh(version)
    derived.enqueue_for(db, file_sha256, meta_pending=bool((meta or {}).get("pending")))
    return version


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
        ids_status=v.ids_status,
        suitability_code=v.suitability_code,
        revision_code=v.revision_code,
        suitability_label=iso19650.label(v.suitability_code),
        created_at=v.created_at,
    )


def get_model_checked(db, model_id: int, user, required: Role) -> Model:
    model = db.get(Model, model_id)
    if model is None or model.deleted_at is not None:  # VCS-06: o'chirilgan (savatdagi) model ko'rinmaydi
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model topilmadi")
    check_project_role(db, model.project_id, user, required)
    return model


def get_version_checked(db, version_id: int, user, required: Role) -> Version:
    version = db.get(Version, version_id)
    if version is None or version.model.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versiya topilmadi")
    check_project_role(db, version.model.project_id, user, required)
    return version


# --- Modellar ---


@router.get("/projects/{project_id}/models", response_model=list[ModelOut])
def list_models(project: ViewerProject):
    return [_model_out(m) for m in project.models if m.deleted_at is None]


@router.post("/projects/{project_id}/models", response_model=ModelOut, status_code=201)
def create_model(body: ModelCreate, project: EngineerProject, user: CurrentUser, db: DB):
    same = next((m for m in project.models if m.name == body.name), None)
    if same is not None:
        if same.deleted_at is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Bu nom o'chirilgan (savatdagi) modelniki — administrator tiklashi yoki butunlay tozalashi kerak",
            )
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
    """VCS-06: yumshoq o'chirish (tasdiqlovchi) — model va butun tarixi saqlanadi, ro'yxatlardan yo'qoladi.
    Tiklash va butunlay tozalash — faqat administrator (`/api/admin/models/...`)."""
    model = get_model_checked(db, model_id, user, Role.approver)
    model.deleted_at = utcnow()
    model.deleted_by = user.id
    audit.log(
        db,
        user_id=user.id,
        action="model.delete",
        target_type="model",
        target_id=model.id,
        project_id=model.project_id,
        detail={"name": model.name, "soft": True, "versions": len(model.versions)},
    )
    db.commit()


# --- VCS-06: o'chirilgan modellar (administrator) ---


class DeletedModelOut(ModelOut):
    deleted_at: datetime
    deleted_by: int | None = None


def _deleted_model(db, model_id: int) -> Model:
    model = db.get(Model, model_id)
    if model is None or model.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O'chirilgan model topilmadi")
    return model


@router.get("/admin/models/deleted", response_model=list[DeletedModelOut])
def list_deleted_models(_: AdminUser, db: DB, project_id: int | None = None):
    q = db.query(Model).filter(Model.deleted_at.isnot(None))
    if project_id is not None:
        q = q.filter(Model.project_id == project_id)
    return [
        DeletedModelOut(**_model_out(m).model_dump(), deleted_at=m.deleted_at, deleted_by=m.deleted_by)
        for m in q.order_by(Model.deleted_at.desc()).all()
    ]


@router.post("/admin/models/{model_id}/restore", response_model=ModelOut)
def restore_deleted_model(model_id: int, admin: AdminUser, db: DB):
    model = _deleted_model(db, model_id)
    model.deleted_at = None
    model.deleted_by = None
    audit.log(
        db, user_id=admin.id, action="model.restore", target_type="model", target_id=model.id,
        project_id=model.project_id, detail={"name": model.name},
    )
    db.commit()
    return _model_out(model)


@router.delete("/admin/models/{model_id}/purge", status_code=204)
def purge_deleted_model(model_id: int, admin: AdminUser, db: DB):
    """Savatdagi modelni butunlay o'chirish: versiyalar, CR, issue, sim ishlari; boshqa hech kim murojaat
    qilmaydigan fayllar (va hosilaviy kesh) darhol GC bilan o'chiriladi (SRV-05)."""
    from ..orm import ChangeRequest, Issue, SimJob
    from . import blob_gc

    model = _deleted_model(db, model_id)
    shas = {v.file_sha256 for v in model.versions}
    audit.log(
        db, user_id=admin.id, action="model.purge", target_type="model", target_id=model.id,
        project_id=model.project_id, detail={"name": model.name, "versions": len(model.versions), "files": len(shas)},
    )
    # Versiyalarga bog'liq yozuvlar (FK cascade siz): sim vazifalari, issue lar, tasdiqlash so'rovlari — avval
    for cls in (SimJob, Issue, ChangeRequest):
        for row in db.query(cls).filter_by(model_id=model.id).all():
            db.delete(row)
    for v in model.versions:  # ota-bola zanjiri (parent_id) — o'chirish tartibi muhim bo'lmasin
        v.parent_id = None
    db.flush()
    db.delete(model)
    db.commit()
    # Fayllar: faqat shu model sha lari, boshqa yozuv murojaat qilmasa; 10 daqiqalik oyna — parallel yuklash
    # (xuddi shu fayl dedup bo'lib, hali commit bo'lmagan) himoyasi
    blob_gc.collect(db, dry_run=False, grace_s=PURGE_GRACE_S, only_shas=shas)


# --- Versiyalar ---


@router.get("/models/{model_id}/versions", response_model=list[VersionOut])
def list_versions(model_id: int, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.viewer)
    return [version_out(v) for v in reversed(model.versions)]


@router.post(
    "/models/{model_id}/versions",
    response_model=VersionOut,
    status_code=201,
    responses={409: {"description": "parent_id oxirgi versiya emas: {detail, head_id}"}},
)
@head_conflict_response
def upload_version(
    model_id: int,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    message: Annotated[str, Form()] = "",
    parent_id: Annotated[int | None, Form()] = None,
):
    """Commit: yangi IFC versiya yuklash. parent_id berilmasa oxirgi versiya ota bo'ladi; berilsa u oxirgi
    versiya bo'lishi shart — aks holda 409 `{detail, head_id}` (eski versiyadan jimgina tarmoqlanmaydi, VCS-01).
    Yuklangach fonda geometriya tahlili (QTO, to'qnashuvlar) oldindan hisoblanadi."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    if not (file.filename or "").lower().endswith(".ifc"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faqat .ifc fayl qabul qilinadi")
    # G4: konteyner nomlash qoidasi (ISO 19650-2 §5.1.6 — loyiha shabloni)
    naming_warning = iso19650.check_name(file.filename or "", model.project.naming_template or "")
    if naming_warning and model.project.naming_required:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, naming_warning)

    settings = get_settings()
    try:
        sha, size = storage.store(file.file, max_bytes=settings.max_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from e

    try:
        # OPS-03: katta fayl so'rov ichida to'liq parse qilinmaydi (faqat sarlavha) — to'liq metadata navbatda
        meta = ifc_meta.extract_bounded(storage.resolve(sha))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if naming_warning:
        meta["warnings"] = [*meta.get("warnings", []), naming_warning]
    if not meta.get("pending") and crs_mod.from_project(model.project) is not None and not (meta.get("georef") or {}).get("epsg"):
        # G3: loyihada CRS bor, faylda IfcMapConversion yo'q — ogohlantirish (POST /models/{id}/georeference qo'shadi)
        meta["warnings"] = [*meta.get("warnings", []), "Georeferensiya yo'q: IfcMapConversion topilmadi — loyiha CRS bilan mos kelmasligi mumkin"]

    if parent_id is not None:
        parent = db.get(Version, parent_id)
        if parent is None or parent.model_id != model.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "parent_id shu modelga tegishli emas")

    version = create_version(
        db,
        model_id=model.id,
        user=user,
        parent_id=HEAD if parent_id is None else parent_id,
        expected_head=ANY if parent_id is None else parent_id,
        file_sha256=sha,
        file_name=file.filename or "model.ifc",
        file_size=size,
        meta=meta,
        message=message,
        detail={"message": message},
    )
    return version_out(version)


@router.get("/versions/{version_id}/ids")
def version_ids(version_id: int, user: CurrentUser, db: DB):
    """IDS tekshiruv natijasi (G2): talablar, yiqilgan elementlar (GUID) — hali tekshirilmagan bo'lsa 404."""
    version = get_version_checked(db, version_id, user, Role.viewer)
    if version.ids_result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "IDS tekshiruvi hali bajarilmagan (navbatda) — «Qayta tekshirish»")
    return version.ids_result


@router.post("/versions/{version_id}/ids")
def version_ids_run(version_id: int, user: CurrentUser, db: DB):
    """IDS tekshiruvini hozir bajarish (muhandis+) va natijani saqlash."""
    from . import ids_check

    version = get_version_checked(db, version_id, user, Role.engineer)
    try:
        path = storage.resolve(version.file_sha256)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    res = ids_check.validate(path)
    for v in db.query(Version).filter_by(file_sha256=version.file_sha256).all():
        v.ids_status = res["status"]
        v.ids_result = res
    audit.log(
        db, user_id=user.id, action="version.ids_check", target_type="version", target_id=version.id,
        project_id=version.model.project_id, detail={"status": res["status"]},
    )
    db.commit()
    return res


@router.get("/versions/{version_id}/fragments")
def version_fragments(version_id: int, user: CurrentUser, db: DB):
    """Tayyor fragments (.frag) — brauzer IFC o'rniga shuni yuklaydi (tez). OPS-03: konvertatsiya (1800 s gacha)
    so'rov ichida emas — navbatda: hali tayyor bo'lmasa 202 `{job_id, status}` (klient IFC ni ochadi yoki
    keyinroq qayta so'raydi); vosita yo'q yoki konvertatsiya yiqilgan — 404. Yangi konvertatsiya — rate limit."""
    from . import fragments

    version = get_version_checked(db, version_id, user, Role.viewer)
    if not get_settings().fragments_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fragments o'chirilgan")
    sha = version.file_sha256
    out = fragments.frag_path(sha)
    if not out.exists():
        if not fragments.available():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "fragments tayyor emas (Node/tool yo'q)")
        try:
            storage.resolve(sha)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
        job = _derived_job(
            db, user, kind="fragments", payload={"sha": sha}, key=f"fragments:{sha}",
            project_id=version.model.project_id, failed_status=status.HTTP_404_NOT_FOUND,
        )
        return _accepted(job)
    return FileResponse(
        out,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": content_disposition(f"{version.model.name}_v{version.number}.frag"),
        },
    )


@router.get("/versions/{version_id}", response_model=VersionOut)
def get_version(version_id: int, user: CurrentUser, db: DB):
    return version_out(get_version_checked(db, version_id, user, Role.viewer))


class VersionPatch(BaseModel):
    message: str | None = None
    tag: str | None = Field(None, max_length=64)
    # G4 (ISO 19650): tasdiqlovchi; holat bilan mos bo'lishi shart (S0 — wip, S1–S7 — shared, A/B/CR/PR — published)
    suitability_code: str | None = Field(None, max_length=4)
    revision_code: str | None = Field(None, max_length=6)


@router.patch("/versions/{version_id}", response_model=VersionOut)
def update_version(version_id: int, body: VersionPatch, user: CurrentUser, db: DB):
    """Izoh (muallif yoki tasdiqlovchi) va yorliq/teg (tasdiqlovchi) — fayl o'zgarmaydi.
    VCS-05: published/archived versiya o'zgarmas — izoh va reviziya kodi 409 (yorliq/teg va yaroqlilik kodi
    tasdiqlovchi uchun o'zgaruvchan qoladi)."""
    v = get_version_checked(db, version_id, user, Role.viewer)
    project_id = v.model.project_id
    approver = has_role(get_project_role(db, project_id, user), Role.approver)
    if v.state in (VersionState.published, VersionState.archived):
        frozen = [k for k in ("message", "revision_code") if getattr(body, k) is not None]
        if frozen:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"v{v.number} {v.state.value} — o'zgarmas ({', '.join(frozen)} o'zgartirilmaydi); yorliq qo'yish mumkin",
            )
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
    if body.suitability_code is not None or body.revision_code is not None:
        if not approver:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "ISO 19650 kodlarini tasdiqlovchi qo'yadi")
        try:
            if body.suitability_code is not None:
                code = iso19650.normalize(body.suitability_code)
                if code:
                    iso19650.check_suitability(code, v.state)
                v.suitability_code = code
            if body.revision_code is not None:
                rev = iso19650.normalize(body.revision_code)
                if rev:
                    iso19650.check_revision(rev, v.state)
                v.revision_code = rev
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
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
@head_conflict_response
def restore_version(version_id: int, user: CurrentUser, db: DB, expected_head_id: int | None = None):
    """Eski versiyani qayta tiklash: fayli bilan yangi (oxirgi) versiya yaratiladi (git revert kabi),
    ota — joriy oxirgi versiya, izoh — qaysi versiyadan. Tarix o'chmaydi. `expected_head_id` — klient
    ko'rgan oxirgi versiya; oraliqda boshqa commit bo'lgan bo'lsa 409 `{detail, head_id}` (VCS-01)."""
    src = get_version_checked(db, version_id, user, Role.engineer)
    last = head_version(db, src.model_id)
    if last is not None and last.id == src.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu allaqachon oxirgi versiya")
    v = create_version(
        db,
        model_id=src.model_id,
        user=user,
        parent_id=HEAD,
        expected_head=ANY if expected_head_id is None else expected_head_id,
        file_sha256=src.file_sha256,
        file_name=src.file_name,
        file_size=src.file_size,
        meta=src.meta,
        message=f"v{src.number} dan qayta tiklandi: {src.message}".strip(),
        action="version.restore",
        detail={"from_version_id": src.id, "from_number": src.number},
    )
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
        headers={"Content-Disposition": content_disposition(f"{version.model.name}_v{version.number}.ifc")},
    )


# ---------- BIM tekshiruvlar: hajm-miqdor (QTO), to'qnashuvlar ----------


# OPS-03/04: og'ir hosilaviy hisob (geometriya, fragments) — foydalanuvchi bo'yicha yangi hisoblar chegarasi
# (keshdagi natijani o'qish va navbatdagi ishni kuzatish cheklanmaydi); chegara — `rate_derived_per_min`
def _derived_rate(user) -> None:
    ratelimit.check("derived", f"user:{user.id}", get_settings().rate_derived_per_min)


DERIVED_FAILED_RETRY_S = 600  # yiqilgan hisob shuncha vaqt ichida qayta navbatga qo'yilmaydi (xato qaytadi)


def _derived_job(db, user, *, kind: str, payload: dict, key: str, project_id: int, failed_status: int = 422) -> Job:
    """OPS-03: og'ir hosilaviy hisob — DB navbati (jobs.py). Navbatda/ishlayotgan bo'lsa o'sha ish qaytadi
    (takror yo'q, cheklanmaydi); yangi (yoki natijasi yo'qolgan) hisob — foydalanuvchi bo'yicha rate limit.
    Yaqinda yiqilgan ish — `failed_status` bilan xato (so'rov har safar og'ir ishni qayta boshlamasin)."""
    row = db.query(Job).filter_by(idempotency_key=key).one_or_none()
    if row is not None and row.status in (JobStatus.queued, JobStatus.running):
        return row
    if row is not None and row.status == JobStatus.failed and row.finished_at is not None:
        fin = row.finished_at if row.finished_at.tzinfo else row.finished_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - fin).total_seconds() < DERIVED_FAILED_RETRY_S:
            raise HTTPException(failed_status, f"Hisoblab bo'lmadi: {(row.error or '?')[:300]}")
    _derived_rate(user)
    row = jobs.enqueue(db, kind, payload, idempotency_key=key, project_id=project_id, user_id=user.id)
    if row.status in (JobStatus.done, JobStatus.failed):  # natija (kesh) yo'qolgan yoki eski xato — qayta
        row.status, row.attempts, row.error = JobStatus.queued, 0, ""
        row.finished_at = row.worker_id = row.lease_until = None
    db.commit()
    jobs.kick()
    return row


def _accepted(job: Job) -> JSONResponse:
    """202 — hisob navbatda: klient shu URL ni `Retry-After` dan keyin qayta so'raydi (200 — natija)."""
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"job_id": job.id, "status": job.status.value},
        headers={"Retry-After": "2", "Cache-Control": "no-store"},
    )


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
    tur va qavat bo'yicha jamlanma; ?format=csv — Excel uchun. Natija fayl bo'yicha keshlanadi.
    OPS-03: keshda bo'lmasa navbatga qo'yiladi — 202 `{job_id, status}`, tayyor bo'lgach shu URL 200."""
    from . import geometry

    version, _path = _version_path(db, version_id, user)
    data = geometry.peek(version.file_sha256, "qto")
    if data is None:
        sha = version.file_sha256
        return _accepted(
            _derived_job(db, user, kind="qto", payload={"sha": sha}, key=f"qto:{sha}", project_id=version.model.project_id)
        )
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
                "Content-Disposition": content_disposition(f"qto_{version.model.name}_v{version.number}.csv")
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
    — faqat shu guruhlar orasidagi juftlar. OPS-04: turlar ma'lum IFC klasslari bo'lishi shart (aks holda
    422), kesh kaliti — normallashtirilgan parametrlar xeshi, yangi hisob foydalanuvchi bo'yicha cheklangan."""
    from . import geometry

    if kind is not None and kind not in ("hard", "possible", "touch"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kind: hard | possible | touch")
    try:
        ta, tb = geometry.normalize_types(types_a), geometry.normalize_types(types_b)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    version, _path = _version_path(db, version_id, user)
    key = geometry.clash_kind(ta, tb)
    data = geometry.peek(version.file_sha256, key)
    if data is None:  # OPS-03: navbatda — 202, tayyor bo'lgach 200
        sha = version.file_sha256
        return _accepted(
            _derived_job(
                db, user, kind="clash", payload={"sha": sha, "types_a": ta, "types_b": tb},
                key=f"clash:{sha}:{key}", project_id=version.model.project_id,
            )
        )
    if kind:
        data = {**data, "clashes": [c for c in data["clashes"] if c["kind"] == kind]}
    return data


# --------------------------------------------------------------------------- SRV-05: fayl ombori tozalash


class StorageGcIn(BaseModel):
    dry_run: bool = True
    # Kamida 1 soat: yangi saqlangan, lekin hali commit bo'lmagan fayl o'chirilmasin
    grace_hours: float = Field(default=24.0, ge=1.0, le=24 * 365)


@router.post("/admin/storage/gc")
def storage_gc(body: StorageGcIn, admin: AdminUser, db: DB):
    """Murojaatsiz content-addressed fayllar, ularning hosilaviy keshi va eskirgan vaqtinchalik (`tmp*`,
    `*.part`) fayllar: `dry_run` (default) — faqat hisobot; aks holda o'chiradi (audit)."""
    from . import blob_gc

    rep = blob_gc.collect(db, dry_run=body.dry_run, grace_s=body.grace_hours * 3600)
    if not body.dry_run:
        audit.log(
            db, user_id=admin.id, action="storage.gc", target_type="storage",
            detail={k: rep[k] for k in ("blobs", "derived", "temp", "bytes", "kept_recent", "errors", "grace_s")},
        )
        db.commit()
    return rep


# --------------------------------------------------------------------------- G5: klassifikatsiya


@router.get("/classification/systems")
def classification_systems(_: CurrentUser):
    """Mavjud klassifikatorlar va GES turi → kod xaritasi (Uniclass 2015, SATH-KSI)."""
    return {k: {"title": v["title"], "source": v["source"], "edition": v["edition"], "kinds": v["kinds"]} for k, v in classification.SYSTEMS.items()}


class ClassifyIn(BaseModel):
    system: str = classification.DEFAULT_SYSTEM
    overwrite: bool = False
    message: str = ""


@router.post("/versions/{version_id}/classify", response_model=VersionOut, status_code=201)
@head_conflict_response
def classify_version(version_id: int, body: ClassifyIn, user: CurrentUser, db: DB):
    """Oxirgi versiyani GES turi bo'yicha klassifikatsiyalab (IfcClassificationReference) yangi versiya yozadi."""
    import tempfile
    from pathlib import Path as _P

    import ifcopenshell

    src_v = get_version_checked(db, version_id, user, Role.engineer)
    model = src_v.model
    head = head_version(db, model.id)
    if head is None or head.id != src_v.id:
        raise HeadMoved(head.id if head else None)  # faqat oxirgi versiya klassifikatsiyalanadi
    if body.system not in classification.SYSTEMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Klassifikator: {', '.join(classification.SYSTEMS)}")
    try:
        f = ifcopenshell.open(str(storage.resolve(src_v.file_sha256)))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    info = classification.classify_file(f, body.system, body.overwrite)
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="ges-cls-") as tmp:
        out = _P(tmp) / "cls.ifc"
        f.write(str(out))
        with open(out, "rb") as fh:
            sha, size = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    meta = ifc_meta.extract_bounded(storage.resolve(sha))
    v = create_version(
        db,
        model_id=model.id,
        user=user,
        parent_id=src_v.id,
        expected_head=src_v.id,
        file_sha256=sha,
        file_name=src_v.file_name,
        file_size=size,
        meta=meta,
        message=body.message or f"Klassifikatsiya ({body.system}): {info['assigned']} element",
        action="version.classify",
        detail=info,
    )
    return version_out(v)


# --------------------------------------------------------------------------- G5: federatsiya


class FedMember(BaseModel):
    model_id: int
    version_id: int | None = None  # None — oxirgi published (yo'q bo'lsa oxirgi)
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    rot_deg: float = Field(default=0.0, ge=-360, le=360)


class FederationIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    members: list[FedMember] = Field(min_length=1, max_length=50)


class FederationOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    members: list[dict]
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _fed_out(db, fed: Federation) -> FederationOut:
    try:
        members = federation.resolve_members(db, fed.members)
    except ValueError as e:
        members = [{**m, "error": str(e)} for m in fed.members]
    return FederationOut(id=fed.id, project_id=fed.project_id, name=fed.name, description=fed.description, members=members, created_by=fed.created_by, created_at=fed.created_at, updated_at=fed.updated_at)


def _get_fed(db, fed_id: int, user, role: Role) -> Federation:
    fed = db.get(Federation, fed_id)
    if fed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Federatsiya topilmadi")
    check_project_role(db, fed.project_id, user, role)
    return fed


def _check_members(db, project: Project, members: list[FedMember]) -> list[dict]:
    raw = [m.model_dump() for m in members]
    for m in raw:
        model = db.get(Model, m["model_id"])
        if model is None or model.project_id != project.id or model.deleted_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Model {m['model_id']} shu loyihaniki emas")
    try:
        federation.resolve_members(db, raw)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return raw


@router.get("/projects/{project_id}/federations", response_model=list[FederationOut])
def list_federations(project: ViewerProject, db: DB):
    return [_fed_out(db, f) for f in db.query(Federation).filter_by(project_id=project.id).order_by(Federation.id).all()]


@router.post("/projects/{project_id}/federations", response_model=FederationOut, status_code=201)
def create_federation(body: FederationIn, project: EngineerProject, user: CurrentUser, db: DB):
    fed = Federation(project_id=project.id, name=body.name, description=body.description, members=_check_members(db, project, body.members), created_by=user.id)
    db.add(fed)
    db.flush()
    audit.log(db, user_id=user.id, action="federation.create", target_type="federation", target_id=fed.id, project_id=project.id, detail={"name": fed.name, "members": len(fed.members)})
    db.commit()
    db.refresh(fed)
    return _fed_out(db, fed)


@router.put("/federations/{fed_id}", response_model=FederationOut)
def update_federation(fed_id: int, body: FederationIn, user: CurrentUser, db: DB):
    fed = _get_fed(db, fed_id, user, Role.engineer)
    fed.name, fed.description = body.name, body.description
    fed.members = _check_members(db, db.get(Project, fed.project_id), body.members)
    audit.log(db, user_id=user.id, action="federation.update", target_type="federation", target_id=fed.id, project_id=fed.project_id, detail={"members": len(fed.members)})
    db.commit()
    db.refresh(fed)
    return _fed_out(db, fed)


@router.delete("/federations/{fed_id}", status_code=204)
def delete_federation(fed_id: int, user: CurrentUser, db: DB):
    fed = _get_fed(db, fed_id, user, Role.engineer)
    db.delete(fed)
    audit.log(db, user_id=user.id, action="federation.delete", target_type="federation", target_id=fed_id, project_id=fed.project_id)
    db.commit()


@router.get("/federations/{fed_id}", response_model=FederationOut)
def get_federation(fed_id: int, user: CurrentUser, db: DB):
    return _fed_out(db, _get_fed(db, fed_id, user, Role.viewer))


@router.get("/federations/{fed_id}/clashes")
def federation_clashes(
    fed_id: int,
    user: CurrentUser,
    db: DB,
    tolerance: float = Query(0.0, ge=0.0, le=1.0, description="AABB zaxirasi, m (katta qiymat juftlar sonini portlatadi)"),
    cross_only: bool = True,
):
    """Federatsiya ustida to'qnashuvlar (G5): a'zolar siljitilgan holda, default faqat modellar orasida; kesh.
    OPS-03: keshda bo'lmasa so'rov ichida hisoblanmaydi — navbatga (`fedclash`), 202 `{job_id, status}` +
    `Retry-After`; tayyor bo'lgach shu URL 200. Yangi hisob — foydalanuvchi bo'yicha `rate_derived_per_min`
    (429). A'zo/fayl topilmasa yoki hisob yiqilgan bo'lsa — 409."""
    fed = _get_fed(db, fed_id, user, Role.viewer)
    try:
        resolved = federation.resolve_members(db, fed.members)
        for m in resolved:
            storage.resolve(m["sha"])
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    data = federation.peek_clashes(resolved, tolerance, cross_only)
    if data is None:
        key = federation.clash_cache_key(resolved, tolerance, cross_only)
        return _accepted(
            _derived_job(
                db, user, kind="fedclash", payload={"members": resolved, "tolerance": tolerance, "cross_only": cross_only},
                key=f"fedclash:{key}", project_id=fed.project_id, failed_status=status.HTTP_409_CONFLICT,
            )
        )
    return data


@router.get("/federations/{fed_id}/ifc")
def federation_ifc(fed_id: int, user: CurrentUser, db: DB):
    """Birlashtirilgan IFC (ko'rish uchun): birinchi a'zo asos, qolganlari siljitilib nusxalangan."""
    fed = _get_fed(db, fed_id, user, Role.viewer)
    try:
        path = federation.merged_ifc(federation.resolve_members(db, fed.members))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return FileResponse(
        path, media_type="application/octet-stream", headers={"Content-Disposition": content_disposition(f"federation_{fed.id}.ifc")}
    )


# --------------------------------------------------------------------------- G6: aktiv registri (COBie ga o'xshash)


@router.get("/versions/{version_id}/assets/register")
def version_asset_register(version_id: int, user: CurrentUser, db: DB, format: str = "json"):
    """IFC dan aktiv registri: Facility/Floor/Type/Component/Attribute (COBie 2.4 soddalashtirilgan);
    `format=csv` — CSV varaqlari zip (qurilishdan ekspluatatsiyaga topshirish)."""
    from fastapi.responses import Response

    v = get_version_checked(db, version_id, user, Role.viewer)
    try:
        reg = cobie.register_from_path(storage.resolve(v.file_sha256))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    if format == "csv":
        audit.log(db, user_id=user.id, action="export.cobie", target_type="version", target_id=v.id, project_id=v.model.project_id, detail=reg["counts"])
        db.commit()
        return Response(cobie.to_csv_zip(reg), media_type="application/zip", headers={"Content-Disposition": content_disposition(f"cobie_{v.model.name}_v{v.number}.zip")})
    return reg


@router.get("/ifc/schemas")
def ifc_schemas(_: CurrentUser):
    """G1: qo'llab-quvvatlanadigan IFC sxemalari, joriy default va GES turi → sinf xaritasi (sxema bo'yicha)."""
    return {
        "default": ifc_schema.normalize(get_settings().ifc_schema),
        "schemas": list(ifc_schema.SCHEMAS),
        "map": {sc: {k: {"class": v[0], "predefined": v[1], "object_type": v[2]} for k, v in ifc_schema._MAP[sc].items()} for sc in ifc_schema.SCHEMAS},
    }
