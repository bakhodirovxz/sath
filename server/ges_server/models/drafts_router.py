"""Qoralama obyektlar API: ro'yxat/yaratish/tahrirlash/o'chirish, IFC ga commit (yangi versiya)."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, get_project_role, has_role
from ..config import get_settings
from ..downloads import content_disposition
from ..orm import DraftObject, Role, Version, utcnow
from . import assimp_load, cad_import, drafts, ifc_meta, mesh_import, storage
from . import crs as crs_mod
from .router import (
    ANY,
    check_head,
    create_version,
    get_model_checked,
    head_conflict_response,
    head_version,
    version_out,
)

router = APIRouter(prefix="/api", tags=["drafts"])

MAX_MESH_VERTICES = 200_000


class DraftIn(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=128)
    ifc_class: str = Field(default="", max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    transform: dict[str, float] = Field(default_factory=dict)
    psets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mesh: dict[str, list] = Field(default_factory=dict)
    source_guid: str | None = Field(None, max_length=32)  # mavjud element tahriri/o'chirish


class DraftPatch(BaseModel):
    name: str | None = Field(None, max_length=128)
    ifc_class: str | None = Field(None, max_length=64)
    params: dict[str, Any] | None = None
    transform: dict[str, float] | None = None
    psets: dict[str, dict[str, Any]] | None = None
    mesh: dict[str, list] | None = None
    source_guid: str | None = Field(None, max_length=32)


class DraftOut(BaseModel):
    id: int
    model_id: int
    author_id: int
    author_username: str
    kind: str
    name: str
    ifc_class: str
    params: dict
    transform: dict
    psets: dict
    has_mesh: bool
    source_guid: str | None = None
    mesh: dict | None = (
        None  # faqat kind == "mesh" (mavjud element / erkin mesh) — web qayta quradi
    )
    created_at: datetime
    updated_at: datetime


def _out(d: DraftObject) -> DraftOut:
    return DraftOut(
        id=d.id,
        model_id=d.model_id,
        author_id=d.author_id,
        author_username=d.author.username,
        kind=d.kind,
        name=d.name,
        ifc_class=d.ifc_class,
        params=d.params,
        transform=d.transform,
        psets=d.psets,
        has_mesh=bool(d.mesh),
        source_guid=d.source_guid,
        mesh=d.mesh if d.kind == "mesh" else None,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _check_mesh(mesh: dict | None) -> None:
    if not mesh:
        return
    v = mesh.get("vertices") or []
    if len(v) > MAX_MESH_VERTICES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Mesh juda katta")


@router.get("/models/{model_id}/drafts", response_model=list[DraftOut])
def list_drafts(model_id: int, user: CurrentUser, db: DB):
    get_model_checked(db, model_id, user, Role.viewer)
    rows = db.query(DraftObject).filter_by(model_id=model_id).order_by(DraftObject.id).all()
    return [_out(d) for d in rows]


@router.post("/models/{model_id}/drafts", response_model=DraftOut, status_code=201)
def create_draft(model_id: int, body: DraftIn, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.engineer)
    _check_mesh(body.mesh)
    d = DraftObject(
        model_id=model.id,
        author_id=user.id,
        kind=body.kind,
        name=body.name,
        ifc_class=body.ifc_class,
        params=body.params,
        transform=body.transform,
        psets=body.psets,
        mesh=body.mesh,
        source_guid=body.source_guid or None,
    )
    db.add(d)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="draft.create",
        target_type="draft",
        target_id=d.id,
        project_id=model.project_id,
        detail={"kind": d.kind, "name": d.name},
    )
    db.commit()
    db.refresh(d)
    return _out(d)


def _get_own_draft(db, draft_id: int, user) -> tuple[DraftObject, int]:
    """VCS-04: qoralamani faqat muallifi (yoki loyiha tasdiqlovchisi) o'zgartiradi/o'chiradi.
    Qaytaradi: (qoralama, project_id)."""
    d = db.get(DraftObject, draft_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qoralama topilmadi")
    model = get_model_checked(db, d.model_id, user, Role.engineer)
    if d.author_id != user.id and not has_role(get_project_role(db, model.project_id, user), Role.approver):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Qoralamani muallifi yoki tasdiqlovchi o'zgartiradi")
    return d, model.project_id


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: int, body: DraftPatch, user: CurrentUser, db: DB):
    d, project_id = _get_own_draft(db, draft_id, user)
    changes = body.model_dump(exclude_none=True)
    _check_mesh(changes.get("mesh"))
    for k in DraftPatch.model_fields:
        if k in changes:
            setattr(d, k, changes[k])
    d.updated_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="draft.update",
        target_type="draft",
        target_id=d.id,
        project_id=project_id,
        detail={"fields": sorted(changes), "author_id": d.author_id, "name": d.name},
    )
    db.commit()
    db.refresh(d)
    return _out(d)


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: int, user: CurrentUser, db: DB):
    d, project_id = _get_own_draft(db, draft_id, user)
    audit.log(
        db,
        user_id=user.id,
        action="draft.delete",
        target_type="draft",
        target_id=d.id,
        project_id=project_id,
        detail={"kind": d.kind, "name": d.name, "author_id": d.author_id},
    )
    db.delete(d)
    db.commit()


class CommitIn(BaseModel):
    message: str = Field(default="", max_length=2000)
    base_version_id: int | None = None  # qaysi versiya ustiga (default: oxirgi)
    # None — o'z qoralamalarim (VCS-04); boshqaning qoralamasini faqat tasdiqlovchi aniq id bilan qo'sha oladi
    draft_ids: list[int] | None = None
    keep_drafts: bool = False  # commitdan keyin qoralamalarni saqlab qolish


@router.post("/models/{model_id}/drafts/commit", status_code=201)
@head_conflict_response
def commit_drafts(
    model_id: int, body: CommitIn, user: CurrentUser, db: DB
):
    """Qoralamalarni IFC ga qo'shib yangi versiya yaratadi (git commit kabi): ota — tanlangan/oxirgi versiya.
    `base_version_id` oxirgi versiya bo'lishi shart; oraliqda boshqa commit bo'lsa 409 `{detail, head_id}`."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    q = db.query(DraftObject).filter_by(model_id=model.id)
    if body.draft_ids:
        q = q.filter(DraftObject.id.in_(body.draft_ids))
    else:
        q = q.filter(DraftObject.author_id == user.id)  # hammaning emas — faqat o'zimniki
    rows = q.order_by(DraftObject.id).all()
    if any(d.author_id != user.id for d in rows) and not has_role(
        get_project_role(db, model.project_id, user), Role.approver
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Boshqa foydalanuvchining qoralamasini faqat tasdiqlovchi commit qiladi")
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Commit uchun qoralama obyekt yo'q")
    missing = [d.name or d.kind for d in rows if not d.mesh and d.kind != "deleted"]
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Mesh yo'q: {', '.join(missing)} — 3D da qayta saqlang"
        )
    if body.base_version_id is not None:
        base = db.get(Version, body.base_version_id)
        if base is None or base.model_id != model.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "base_version_id shu modelga tegishli emas"
            )
        check_head(db, model.id, base.id)  # og'ir qurishdan oldin — eski versiya ustiga commit yo'q (VCS-01)
    else:
        base = head_version(db, model.id)
    src = None
    if base is not None:
        try:
            src = storage.resolve(base.file_sha256)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Asos versiya fayli topilmadi") from None
    objects = [
        {
            "kind": d.kind,
            "name": d.name,
            "ifc_class": d.ifc_class,
            "transform": d.transform,
            "psets": d.psets,
            "mesh": d.mesh,
            "guid": d.source_guid,
        }
        for d in rows
        if d.kind != "deleted"
    ]
    remove_guids = [d.source_guid for d in rows if d.kind == "deleted" and d.source_guid]
    if not objects and not remove_guids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Commit uchun o'zgarish yo'q")
    if src is None and (remove_guids or any(o["guid"] for o in objects)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Asos versiya yo'q — mavjud elementni tahrirlab bo'lmaydi"
        )
    try:
        tmp, info = drafts.build_to_temp(src, objects, remove_guids=remove_guids, crs=crs_mod.from_project(model.project))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    settings = get_settings()
    with open(tmp, "rb") as fh:
        sha, size = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    tmp.unlink(missing_ok=True)
    meta = ifc_meta.extract(storage.resolve(sha))
    names = ", ".join((d.name or d.kind) for d in rows[:5]) + (" …" if len(rows) > 5 else "")
    n_del, n_edit = len(remove_guids), sum(1 for o in objects if o["guid"])
    n_new = len(objects) - n_edit
    what = ", ".join(
        s
        for s, n in (
            (f"{n_new} ta qo'shildi", n_new),
            (f"{n_edit} ta o'zgardi", n_edit),
            (f"{n_del} ta o'chirildi", n_del),
        )
        if n
    )
    draft_ids = [d.id for d in rows]
    n_drafts = len(rows)
    message = body.message or f"Web 3D: {what} ({names})"

    def _drop_drafts(_v: Version) -> None:
        # shu tranzaksiyada: versiya yozilmasa qoralamalar ham qoladi
        if not body.keep_drafts:
            db.query(DraftObject).filter(DraftObject.id.in_(draft_ids)).delete(synchronize_session=False)

    v = create_version(
        db,
        model_id=model.id,
        user=user,
        parent_id=base.id if base else None,
        expected_head=base.id if base else None,
        file_sha256=sha,
        file_name=(base.file_name if base else f"{model.name}.ifc"),
        file_size=size,
        meta=meta,
        message=message,
        detail={"message": message, "drafts": n_drafts, "guids": info["guids"], "removed": info.get("removed", 0)},
        on_insert=_drop_drafts,
    )
    out = version_out(v).model_dump()
    out["guids"] = info["guids"]
    return out


@router.post("/models/{model_id}/versions/import-mesh", status_code=201)
@head_conflict_response
def import_mesh_version(
    model_id: int,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    message: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "m",
    y_up: Annotated[bool, Form()] = False,
    merge: Annotated[bool, Form()] = False,
    onto_current: Annotated[bool, Form()] = True,
    extrude_m: Annotated[float, Form()] = 0.0,
):
    """Blender / 3ds Max / AutoCAD faylini (OBJ, STL, PLY, glTF/GLB, DAE, 3MF, OFF, DXF) IFC ga aylantirib yangi
    versiya yaratadi: har obyekt — IFC element (nomi saqlanadi). onto_current — joriy oxirgi versiya ustiga
    qo'shiladi (ota = oxirgi), aks holda yangi IFC. unit — fayl birligi; y_up — Y yuqoriga (glTF, ba'zi eksportlar)."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    name = file.filename or "mesh"
    ext = Path(name).suffix.lower()
    if ext not in mesh_import.SUPPORTED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Qo'llanmaydigan format {ext or '?'}: {', '.join(sorted(mesh_import.SUPPORTED))}. FBX/.blend/.max — glTF yoki OBJ ga eksport qiling",
        )
    if unit not in mesh_import.UNITS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unit: {list(mesh_import.UNITS)}")
    settings = get_settings()
    base = model.versions[-1] if (onto_current and model.versions) else None
    src = None
    if base is not None:
        try:
            src = storage.resolve(base.file_sha256)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Asos versiya fayli topilmadi") from None
    with tempfile.TemporaryDirectory(prefix="ges-mesh-") as tmp:
        tp = Path(tmp) / name
        size = 0
        with open(tp, "wb") as fh:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fayl juda katta")
                fh.write(chunk)
        try:
            objects = mesh_import.load_objects(tp, unit, y_up, merge, extrude_m=extrude_m)
            out = Path(tmp) / "import.ifc"
            info = drafts.build(src, objects, out, crs=crs_mod.from_project(model.project))
        except (ValueError, OSError) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Faylni o'qib bo'lmadi: {e}") from e
        except Exception as e:  # noqa: BLE001 — trimesh/parsers turli xato beradi
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Faylni o'qib bo'lmadi: {type(e).__name__}: {e}"
            ) from e
        with open(out, "rb") as fh:
            sha, fsize = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    return _version_from_import(
        db, user, model, base, sha, fsize, name, message, info, objects, {"unit": unit}, onto=onto_current
    )


def _version_from_import(
    db, user, model, base, sha, fsize, name, message, info, objects, detail, *, onto: bool = True
):
    """Saqlangan IFC (sha) dan yangi versiya yozuvi, audit, fon vazifalar; javob JSON.
    `onto` — joriy oxirgi versiya ustiga: yozish paytida u hali oxirgi bo'lishi shart (aks holda 409)."""
    meta = ifc_meta.extract(storage.resolve(sha))
    v = create_version(
        db,
        model_id=model.id,
        user=user,
        parent_id=base.id if base else None,
        expected_head=(base.id if base else None) if onto else ANY,
        file_sha256=sha,
        file_name=f"{Path(name).stem}.ifc",
        file_size=fsize,
        meta=meta,
        message=message or f"{name} dan import: {info['count']} element",
        detail={"import": name, "elements": info["count"], **detail},
    )
    out_v = version_out(v).model_dump()
    out_v["imported"] = info["count"]
    out_v["names"] = [o["name"] for o in objects][:50]
    return out_v


@router.post("/models/{model_id}/versions/import-image", status_code=201)
@head_conflict_response
def import_image_version(
    model_id: int,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    mode: Annotated[str, Form()] = "drawing",
    message: Annotated[str, Form()] = "",
    width_m: Annotated[float, Form()] = 100.0,
    extrude_m: Annotated[float, Form()] = 3.0,
    z_min: Annotated[float, Form()] = 0.0,
    z_max: Annotated[float, Form()] = 100.0,
    grid: Annotated[int, Form()] = 160,
    min_area_px: Annotated[int, Form()] = 40,
    invert: Annotated[bool, Form()] = False,
    onto_current: Annotated[bool, Form()] = True,
):
    """Rasmdan raqamli egizak: mode=drawing — skanerlangan plan/kesim → konturlar balandlikka ko'tariladi
    (devor/to'g'on); mode=heightmap — balandlik xaritasi (DEM) → relyef; mode=photo — foto → taxminiy relyef.
    width_m — rasm kengligi metrda (masshtab)."""
    from . import image_import

    model = get_model_checked(db, model_id, user, Role.engineer)
    name = file.filename or "rasm.png"
    ext = Path(name).suffix.lower()
    if ext not in image_import.IMAGE_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Rasm kutilgan: {', '.join(sorted(image_import.IMAGE_EXTS))}",
        )
    if mode not in ("drawing", "heightmap", "photo"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode: drawing | heightmap | photo")
    settings = get_settings()
    base = model.versions[-1] if (onto_current and model.versions) else None
    src = None
    if base is not None:
        try:
            src = storage.resolve(base.file_sha256)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Asos versiya fayli topilmadi") from None
    with tempfile.TemporaryDirectory(prefix="ges-img-") as tmp:
        tp = Path(tmp) / name
        size = 0
        with open(tp, "wb") as fh:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fayl juda katta")
                fh.write(chunk)
        try:
            objects = image_import.load_image(
                tp,
                mode,
                width_m=width_m,
                extrude_m=extrude_m,
                z_min=z_min,
                z_max=z_max,
                grid=min(max(grid, 8), 400),
                min_area_px=min_area_px,
                invert=invert,
            )
            out = Path(tmp) / "import.ifc"
            info = drafts.build(src, objects, out, crs=crs_mod.from_project(model.project))
        except (ValueError, OSError) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Rasmni o'qib bo'lmadi: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Rasmni o'qib bo'lmadi: {type(e).__name__}: {e}"
            ) from e
        with open(out, "rb") as fh:
            sha, fsize = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    return _version_from_import(
        db,
        user,
        model,
        base,
        sha,
        fsize,
        name,
        message,
        info,
        objects,
        {"mode": mode, "width_m": width_m},
        onto=onto_current,
    )


class DemIn(BaseModel):
    lat: float = Field(ge=-85, le=85)
    lon: float = Field(ge=-180, le=180)
    width_m: float = Field(default=3000, gt=100, le=60000)
    height_m: float = Field(default=3000, gt=100, le=60000)
    rotation_deg: float = 0.0
    zoom: int = Field(default=12, ge=8, le=14)
    nx: int = Field(default=120, ge=8, le=400)
    z_offset_m: float = 0.0
    name: str = Field(default="Relyef (DEM)", max_length=128)
    replace_names: list[str] = Field(default_factory=lambda: ["Relyef (vodiy)", "Relyef (DEM)"])
    onto_current: bool = True
    message: str = ""
    # G3: loyiha CRS bo'yicha joylashtirish (markaz lat/lon → lokal x,y, burilish CRS dan, balandlik global)
    use_crs: bool = True


@router.post("/models/{model_id}/versions/import-dem", status_code=201)
@head_conflict_response
def import_dem_version(
    model_id: int, body: DemIn, user: CurrentUser, db: DB
):
    """Haqiqiy relyef (AWS Terrain Tiles / SRTM) — markaz lat/lon, maydon, burilish → IfcGeographicElement;
    parametrik «Relyef (vodiy)» o'rniga (replace_names). Internet kerak (plitkalar keshlanadi)."""
    from . import dem

    model = get_model_checked(db, model_id, user, Role.engineer)
    settings = get_settings()
    base = model.versions[-1] if (body.onto_current and model.versions) else None
    src = None
    if base is not None:
        try:
            src = storage.resolve(base.file_sha256)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE, "Asos versiya fayli topilmadi") from None
    pcrs = crs_mod.from_project(model.project)
    rotation = body.rotation_deg
    if pcrs is not None and body.use_crs and not body.rotation_deg:
        rotation = pcrs.rotation_deg  # panjara X o'qi — loyiha lokal X o'qi
    try:
        obj, info = dem.terrain_object(
            body.lat,
            body.lon,
            body.width_m,
            body.height_m,
            rotation,
            body.zoom,
            body.nx,
            body.name,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except Exception as e:  # noqa: BLE001 — tarmoq/plitka xatosi
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Relyef plitkalari olinmadi: {e}") from e
    if body.z_offset_m:
        obj["transform"]["z"] += body.z_offset_m
    if pcrs is not None and body.use_crs:
        # G3: relyef markazi lokal koordinatalarda loyiha CRS bo'yicha (lat/lon → E,N → lokal); balandlik global
        lx, ly = pcrs.from_latlon(body.lat, body.lon)
        obj["transform"]["x"] += lx
        obj["transform"]["y"] += ly
        obj["transform"]["z"] -= pcrs.origin_h
        obj["psets"]["Pset_GES_Site"]["EPSG"] = pcrs.epsg
        info["local_center"] = [round(lx, 2), round(ly, 2)]
    with tempfile.TemporaryDirectory(prefix="ges-dem-") as tmp:
        out = Path(tmp) / "dem.ifc"
        try:
            built = drafts.build(src, [obj], out, remove_names=body.replace_names if src else None, crs=pcrs)
        except (ValueError, OSError) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"IFC yozilmadi: {e}") from e
        with open(out, "rb") as fh:
            sha, fsize = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    name = f"dem_{body.lat:.3f}_{body.lon:.3f}.png"
    res = _version_from_import(
        db,
        user,
        model,
        base,
        sha,
        fsize,
        name,
        body.message
        or f"Haqiqiy relyef (DEM): {body.width_m:.0f}×{body.height_m:.0f} m, zoom {info['zoom']} "
        f"(~{info['m_per_px']:.0f} m/px), {info['source']}",
        built,
        [obj],
        {"dem": True, "lat": body.lat, "lon": body.lon, "removed": built.get("removed", 0)},
        onto=body.onto_current,
    )
    res["dem"] = info
    return res


@router.get("/versions/{version_id}/heightmap")
def version_heightmap(version_id: int, user: CurrentUser, db: DB, nx: int = 160):
    """Elementlar ustki yuzasi balandlik xaritasi (IFC koordinatalar, m) — suv yuzasini relyefga moslash."""
    from . import heightmap
    from .router import get_version_checked

    v = get_version_checked(db, version_id, user, Role.viewer)
    try:
        return heightmap.cached(
            storage.resolve(v.file_sha256), v.file_sha256, min(max(nx, 32), 320)
        )
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/versions/{version_id}/export")
def export_version(version_id: int, user: CurrentUser, db: DB, fmt: str = "glb"):
    """IFC → glTF/GLB, OBJ yoki STL — Blender / 3ds Max / boshqa dasturlarda ochish uchun (nom va GUID saqlanadi)."""
    from fastapi.responses import Response

    from .router import get_version_checked

    if fmt not in ("glb", "obj", "stl"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fmt: glb | obj | stl")
    v = get_version_checked(db, version_id, user, Role.viewer)
    try:
        data = mesh_import.export_ifc(storage.resolve(v.file_sha256), fmt)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    media = {"glb": "model/gltf-binary", "obj": "text/plain", "stl": "model/stl"}[fmt]
    name = f"{Path(v.file_name).stem}_v{v.number}.{fmt}"
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": content_disposition(name)},
    )


@router.get("/import/formats")
def import_formats(_: CurrentUser):
    """Qo'llanadigan import formatlari va serverdagi tashqi konverterlar (FBX/3DS — assimp, DWG — dwg2dxf, BLEND — blender)."""
    t = mesh_import.tools()
    return {
        "direct": sorted(mesh_import.DIRECT),
        "assimp": {
            "formats": sorted(mesh_import.VIA_ASSIMP),
            "available": bool(t["assimp"]) or assimp_load.available(),
        },
        "cad": {"formats": sorted(cad_import.CAD_EXTS), "available": cad_import.available()},
        "dwg": {
            "formats": sorted(mesh_import.VIA_DWG),
            "available": bool(t["dwg2dxf"] or t["oda"]),
        },
        "blender": {"formats": sorted(mesh_import.VIA_BLENDER), "available": bool(t["blender"])},
        "unsupported": [".max (3ds Max dan FBX/glTF/OBJ ga eksport qiling)"],
    }


class GeorefIn(BaseModel):
    message: str = ""


@router.post("/models/{model_id}/georeference")
@head_conflict_response
def add_georeference(model_id: int, body: GeorefIn, user: CurrentUser, db: DB):
    """G3: joriy (oxirgi) versiyaga loyiha CRS dan IfcMapConversion/IfcProjectedCRS va IfcSite Ref* qo'shib
    yangi versiya yozadi (mavjud modellarni georeferensiyalash)."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    pcrs = crs_mod.from_project(model.project)
    if pcrs is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Loyihada georeferensiya (EPSG, origin) sozlanmagan")
    base = model.versions[-1] if model.versions else None
    if base is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Modelda versiya yo'q")
    try:
        src = storage.resolve(base.file_sha256)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Asos versiya fayli topilmadi") from None
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="ges-georef-") as tmp:
        out = Path(tmp) / "georef.ifc"
        try:
            built = drafts.build(src, [], out, crs=pcrs)
        except (ValueError, OSError) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"IFC yozilmadi: {e}") from e
        with open(out, "rb") as fh:
            sha, fsize = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    return _version_from_import(
        db, user, model, base, sha, fsize, base.file_name, body.message or f"Georeferensiya: EPSG:{pcrs.epsg}, origin E={pcrs.origin_e:.2f} N={pcrs.origin_n:.2f}",
        built, [], {"georef": built.get("georef")},
    )
