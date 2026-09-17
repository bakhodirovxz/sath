"""Rasm asosi (underlay): foto / skanerlangan chizma / sun'iy yo'ldosh surati 3D sahnada tekislik sifatida —
ustidan qoralama elementlar (Shift+A) bilan chizib raqamli egizak yaratiladi (AutoCAD «Attach image» kabi).
Rasm fayli content-addressed xotirada (storage), joylashuv/masshtab DB da (model bo'yicha)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser
from ..config import get_settings
from ..orm import ImageUnderlay, Role
from . import storage
from .router import get_model_checked

router = APIRouter(prefix="/api", tags=["underlays"])
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class UnderlayOut(BaseModel):
    id: int
    model_id: int
    name: str
    x: float
    y: float
    z: float
    width_m: float
    height_m: float
    rotation_deg: float
    opacity: float
    vertical: bool
    visible: bool
    url: str


class UnderlayPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    x: float | None = None
    y: float | None = None
    z: float | None = None
    width_m: float | None = Field(default=None, gt=0)
    rotation_deg: float | None = None
    opacity: float | None = Field(default=None, ge=0.05, le=1)
    vertical: bool | None = None
    visible: bool | None = None


def _out(u: ImageUnderlay) -> UnderlayOut:
    return UnderlayOut(
        id=u.id,
        model_id=u.model_id,
        name=u.name,
        x=u.x,
        y=u.y,
        z=u.z,
        width_m=u.width_m,
        height_m=u.width_m * (u.px_h / u.px_w if u.px_w else 1.0),
        rotation_deg=u.rotation_deg,
        opacity=u.opacity,
        vertical=u.vertical,
        visible=u.visible,
        url=f"/api/underlays/{u.id}/image",
    )


@router.get("/models/{model_id}/underlays", response_model=list[UnderlayOut])
def list_underlays(model_id: int, user: CurrentUser, db: DB):
    get_model_checked(db, model_id, user, Role.viewer)
    rows = db.query(ImageUnderlay).filter_by(model_id=model_id).order_by(ImageUnderlay.id).all()
    return [_out(u) for u in rows]


@router.post("/models/{model_id}/underlays", response_model=UnderlayOut, status_code=201)
def create_underlay(
    model_id: int,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    _bg: BackgroundTasks,
    name: Annotated[str, Form()] = "",
    width_m: Annotated[float, Form()] = 100.0,
    x: Annotated[float, Form()] = 0.0,
    y: Annotated[float, Form()] = 0.0,
    z: Annotated[float, Form()] = 0.0,
    vertical: Annotated[bool, Form()] = False,
):
    """Rasmni model ostiga (yoki vertical=true — vertikal, kesim/fasad uchun) tekislik sifatida qo'shadi."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    fname = file.filename or "rasm.png"
    ext = Path(fname).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rasm kutilgan (PNG/JPG/WebP/TIFF)")
    settings = get_settings()
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fayl juda katta")
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            px_w, px_h = im.size
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rasmni o'qib bo'lmadi") from None
    import io as _io

    sha, _size = storage.store(_io.BytesIO(data), max_bytes=len(data) + 1)
    u = ImageUnderlay(
        model_id=model.id,
        author_id=user.id,
        name=name or Path(fname).stem,
        file_sha256=sha,
        content_type=file.content_type or "image/png",
        px_w=px_w,
        px_h=px_h,
        x=x,
        y=y,
        z=z,
        width_m=width_m,
        vertical=vertical,
    )
    db.add(u)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="underlay.create",
        target_type="underlay",
        target_id=u.id,
        project_id=model.project_id,
        detail={"model_id": model.id, "name": u.name, "sha": hashlib.sha256(data).hexdigest()[:12]},
    )
    db.commit()
    db.refresh(u)
    return _out(u)


def _get(db, underlay_id: int, user, role: Role) -> ImageUnderlay:
    u = db.get(ImageUnderlay, underlay_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rasm asosi topilmadi")
    get_model_checked(db, u.model_id, user, role)
    return u


@router.get("/underlays/{underlay_id}/image")
def underlay_image(underlay_id: int, user: CurrentUser, db: DB):
    u = _get(db, underlay_id, user, Role.viewer)
    try:
        p = storage.resolve(u.file_sha256)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Rasm fayli topilmadi") from None
    return FileResponse(p, media_type=u.content_type)


@router.patch("/underlays/{underlay_id}", response_model=UnderlayOut)
def update_underlay(underlay_id: int, body: UnderlayPatch, user: CurrentUser, db: DB):
    u = _get(db, underlay_id, user, Role.engineer)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return _out(u)


@router.delete("/underlays/{underlay_id}", status_code=204)
def delete_underlay(underlay_id: int, user: CurrentUser, db: DB):
    u = _get(db, underlay_id, user, Role.engineer)
    db.delete(u)
    db.commit()
