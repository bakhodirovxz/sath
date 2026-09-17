"""Tayyor raqamli egizak (preset) yaratish: model + IFC versiya + maydon pasporti + foto asosi bir bosishda."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from ges_sim import schema, site
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, require_project_role
from ..config import get_settings
from ..orm import ImageUnderlay, Model, Project, Role, Version
from . import drafts, ifc_meta, storage, twin_builder

router = APIRouter(prefix="/api", tags=["twin"])
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]

# Preset fotolari: repo docs/samples/twin (server bilan birga tarqatiladi) yoki GES_DATA_DIR/twin
_PHOTO_DIRS = [Path(__file__).resolve().parents[3] / "docs" / "samples" / "twin"]


class TwinCreate(BaseModel):
    preset: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(default="", max_length=128)
    with_photo: bool = True


@router.get("/twin/presets")
def list_presets(_: CurrentUser):
    return [
        {
            "id": k,
            "title": p["title"],
            "description": p["description"],
            "location": p["location"],
            "sources": p["sources"],
            "photo": bool(p.get("photo")),
            "dam": p["dam"],
            "units": p["units"],
        }
        for k, p in twin_builder.PRESETS.items()
    ]


@router.post("/projects/{project_id}/twin", status_code=201)
def create_twin(
    project: EngineerProject,
    body: TwinCreate,
    user: CurrentUser,
    db: DB,
    background: BackgroundTasks,
):
    """Preset → yangi model (parametrik GES: relyef, to'g'on, minora, tunnellar, mashina zali, agregatlar,
    transformatorlar, suv tashlagich) + v1 IFC + loyiha maydon pasporti (+ foto asosi)."""
    if body.preset not in twin_builder.PRESETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset topilmadi")
    preset = twin_builder.PRESETS[body.preset]
    settings = get_settings()
    name = body.name or preset["title"].split(" (")[0] + " — raqamli egizak"
    if db.query(Model).filter_by(project_id=project.id, name=name).first():
        n = db.query(Model).filter_by(project_id=project.id).count() + 1
        name = f"{name} {n}"
    objects = twin_builder.build_objects(body.preset)
    tmp, info = drafts.build_to_temp(None, objects)
    with open(tmp, "rb") as fh:
        sha, size = storage.store(fh, max_bytes=settings.max_upload_mb * 1024 * 1024)
    tmp.unlink(missing_ok=True)
    model = Model(project_id=project.id, name=name, description=preset["description"])
    db.add(model)
    db.flush()
    v = Version(
        model_id=model.id,
        number=1,
        parent_id=None,
        author_id=user.id,
        message=f"Raqamli egizak (preset «{preset['title']}»): {info['count']} element. Manbalar: "
        + ", ".join(preset["sources"]),
        file_sha256=sha,
        file_name=f"{body.preset}_twin.ifc",
        file_size=size,
        meta=ifc_meta.extract(storage.resolve(sha)),
    )
    db.add(v)
    db.flush()
    # maydon pasporti (loyiha darajasida; bo'sh bo'lsa yoki foydalanuvchi so'rasa to'ldiriladi)
    try:
        project.site = schema.parse(site.SITE_FIELDS, twin_builder.site_values(body.preset))
    except ValueError as e:  # preset qiymati pasport chegarasidan tashqarida — jim o'tkazmaymiz
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Preset pasporti xato: {e}"
        ) from e
    photo_id = None
    photo = preset.get("photo")
    if body.with_photo and photo:
        for d in _PHOTO_DIRS + [settings.data_dir / "twin"]:
            f = d / photo["file"]
            if f.exists():
                data = f.read_bytes()
                try:
                    from PIL import Image

                    with Image.open(io.BytesIO(data)) as im:
                        pw, ph = im.size
                except Exception:  # noqa: BLE001
                    break
                psha, _ = storage.store(io.BytesIO(data), max_bytes=len(data) + 1)
                dam = preset["dam"]
                u = ImageUnderlay(
                    model_id=model.id,
                    author_id=user.id,
                    name=f"Foto: {photo['credit']}",
                    file_sha256=psha,
                    content_type="image/jpeg",
                    px_w=pw,
                    px_h=ph,
                    x=0.0,
                    # foto — quyi yuza tomondan: to'g'on quyi etagidan 350 m nariga, vertikal, gerb balandligida
                    # quyi byefda, vodiy oxirida — «fon» sifatida (to'g'on foto oldida ko'rinadi)
                    y=-5.5 * dam["height_m"],
                    z=dam["base_elevation_m"] + dam["height_m"] * 0.7,
                    width_m=dam["length_m"] * 2.0,
                    vertical=True,
                    opacity=0.75,
                )
                db.add(u)
                db.flush()
                photo_id = u.id
                break
    audit.log(
        db,
        user_id=user.id,
        action="model.create",
        target_type="model",
        target_id=model.id,
        project_id=project.id,
        detail={"twin_preset": body.preset, "elements": info["count"], "version_id": v.id},
    )
    db.commit()
    db.refresh(v)
    if settings.fragments_enabled:
        from . import fragments

        background.add_task(fragments.convert, storage.resolve(sha), sha)
    if settings.precompute_geometry:
        from . import geometry

        background.add_task(geometry.precompute, storage.resolve(sha), sha)
    return {
        "model_id": model.id,
        "model_name": model.name,
        "version_id": v.id,
        "elements": info["count"],
        "site_filled": True,
        "photo_underlay_id": photo_id,
        "preset": body.preset,
        "sources": preset["sources"],
    }
