"""Simulyatsiya API: ishga tushirish (fon vazifa), holat, natija; IFC dan parametrlar; namuna."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from ges_sim import catalog, custom, scenario
from ges_sim.cfd import build_case, run_case
from ges_sim.cfd.params import ValidationError as CfdValidationError
from ges_sim.cfd.params import format_errors, parse_params
from ges_sim.cfd.runner import CfdError, collect_results
from pydantic import BaseModel, Field

from .. import audit, jobs, ratelimit
from ..auth.deps import DB, CurrentUser
from ..config import get_settings
from ..db import SessionLocal
from ..models import storage
from ..models.router import get_model_checked, get_version_checked
from ..orm import Model, Role, SimJob, SimStatus, SimTemplate, Version, utcnow
from . import compute, ges_params

log = logging.getLogger("ges_server.sim")
router = APIRouter(prefix="/api", tags=["simulation"])


class SimCreate(BaseModel):
    name: str = Field(default="", max_length=256)
    version_id: int | None = None
    kind: str = "hydro"
    params: dict[str, Any]
    # L3: takror yuborilgan so'rov (tarmoq uzilishi) yangi ish ochmaydi — mavjud ish qaytadi
    idempotency_key: str | None = Field(default=None, max_length=128)


class SimOut(BaseModel):
    id: int
    model_id: int
    version_id: int | None
    author_id: int
    author_username: str
    kind: str
    name: str
    status: SimStatus
    progress: float
    summary: dict
    error: str
    created_at: datetime
    finished_at: datetime | None
    params: dict | None = None
    attempts: int = 0


def _out(j: SimJob, with_params: bool = False) -> SimOut:
    return SimOut(
        id=j.id,
        model_id=j.model_id,
        version_id=j.version_id,
        author_id=j.author_id,
        author_username=j.author.username,
        kind=j.kind,
        name=j.name,
        status=j.status,
        progress=j.progress,
        summary=j.summary,
        error=j.error,
        created_at=j.created_at,
        finished_at=j.finished_at,
        params=j.params if with_params else None,
        attempts=j.attempts or 0,
    )


def _result_path(job_id: int, kind: str = ""):
    """Natija JSON. CFD — case papkasida (`cfd/<id>/result.json`): CFD worker faqat `cfd/` hajmini ko'radi,
    butun `/data` ni (secret.key, fayllar) emas."""
    if kind == "cfd":
        return _case_dir(job_id) / "result.json"
    d = get_settings().data_dir / "sim"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}.json"


def _case_dir(job_id: int):
    d = get_settings().data_dir / "cfd" / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _set_progress(job_id: int, progress: float, note: str) -> None:
    with SessionLocal() as db:
        job = db.get(SimJob, job_id)
        if job is not None:
            job.progress = progress
            job.error = note  # ish davomida holat matni; tugagach tozalanadi
            db.commit()


def run_job(job_id: int, cfd_mode: str | None = None) -> None:
    """Ishchi (jarayon ichidagi navbat yoki CFD worker) — ish allaqachon claim qilingan (`running`, ijara
    bilan). Alohida sessiya, natija faylga, xulosa DB ga; ijara ish davomida fon threadda uzaytiriladi."""
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(SimJob, job_id)
        if job is None or job.status != SimStatus.running:
            return
        if job.kind == "cfd" and (cfd_mode or settings.cfd_mode) == "worker":
            return  # worker oladi
        kind, params = job.kind, dict(job.params)
    lease = jobs.renew_forever(SimJob, job_id)
    try:
        if kind == "cfd":
            mode = cfd_mode or settings.cfd_mode
            if mode == "off":
                raise CfdError("CFD o'chirilgan (GES_CFD_MODE=off)")
            case_dir = _case_dir(job_id)
            case = build_case(params, case_dir)
            total = case.max_iterations if hasattr(case, "max_iterations") else case.end_time_s
            run_case(
                case_dir,
                total,
                mode=mode,
                image=settings.cfd_image,
                cpus=settings.cfd_cpus,
                memory=settings.cfd_memory,
                timeout_s=settings.cfd_timeout_s,
                on_progress=lambda p, note: _set_progress(job_id, p, note),
            )
            result = collect_results(case, case_dir)
        elif settings.sim_isolate:
            # analitik: alohida jarayon + vaqt chegarasi (sof Python sikli thread dan to'xtamaydi)
            result = compute.run_isolated(kind, params, settings.sim_timeout_s)
        else:
            result = compute.compute(kind, params)
        _result_path(job_id, kind).write_text(json.dumps(result), encoding="utf-8")
        ok, summary, err = True, result["summary"], ""
    except Exception as e:  # noqa: BLE001 — foydalanuvchiga xato matni ko'rsatiladi
        log.exception("sim job %s failed", job_id)
        ok, summary, err = False, {}, _job_error(kind, job_id, e)
    finally:
        lease.set()
    with SessionLocal() as db:
        job = db.get(SimJob, job_id)
        if job is None:
            return
        job.status = SimStatus.done if ok else SimStatus.failed
        job.summary = summary
        job.error = err
        job.progress = 1.0 if ok else job.progress
        job.finished_at = utcnow()
        job.lease_until = None
        db.commit()


def _job_error(kind: str, job_id: int, e: Exception) -> str:
    """Foydalanuvchiga ko'rsatiladigan xato matni. CFD (SEC-01): ichki istisno matni (fayl yo'llari, solver
    chiqishi, muhit) `job.error` ga tushmaydi — faqat xavfsiz `CfdError` xabari yoki umumiy matn + ish id;
    tafsilot server jurnalida (`log.exception`) va `/sim/{id}/log` da."""
    if kind != "cfd":
        return str(e)[:4000]
    if isinstance(e, CfdError):
        return f"{e} (ish #{job_id})"
    return f"CFD hisobi xato bilan tugadi (ish #{job_id}) — tafsilot: solver jurnali yoki server logi"


@router.get("/sim/cfd-status")
def cfd_status(_: CurrentUser):
    from ges_sim.cfd.runner import openfoam_available

    s = get_settings()
    return {
        "mode": s.cfd_mode,
        "available": s.cfd_mode == "worker"
        or (s.cfd_mode != "off" and openfoam_available() is not None),
        "image": s.cfd_image,
    }


@router.get("/sim/example")
def example(_: CurrentUser):
    return scenario.example_params()


@router.get("/versions/{version_id}/ges-params")
def version_ges_params(version_id: int, user: CurrentUser, db: DB):
    """IFC dagi Pset_GES_* dan agregatlar, quvurlar, suv tashlagich, to'g'on parametrlari."""
    v = get_version_checked(db, version_id, user, Role.viewer)
    # Katta IFC (50 MB) ni har safar o'qish 20–60 s — natija sha bo'yicha keshlanadi (data/derived)
    cache = get_settings().data_dir / "derived" / f"{v.file_sha256}.ges.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        out = ges_params.extract(storage.resolve(v.file_sha256))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "Fayl xotirada topilmadi") from None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


@router.get("/models/{model_id}/sim", response_model=list[SimOut])
def list_jobs(model_id: int, user: CurrentUser, db: DB):
    get_model_checked(db, model_id, user, Role.viewer)
    jobs = db.query(SimJob).filter_by(model_id=model_id).order_by(SimJob.id.desc()).all()
    return [_out(j) for j in jobs]


def _hydro_from_site(params: dict, site: dict | None) -> None:
    """Pasportdagi iqlim (bug'lanish, muz) va sizish — foydalanuvchi bermagan bo'lsa avtomatik."""
    from ges_sim.site import climate_from_site

    r = params.get("reservoir")
    if not isinstance(r, dict) or not site:
        return
    if "climate" not in r:
        c = climate_from_site(site)
        if c:
            r["climate"] = c
    if "seepage_m3s" not in r and site.get("seepage_m3s") not in (None, ""):
        try:
            r["seepage_m3s"] = float(site["seepage_m3s"])
        except (TypeError, ValueError):
            pass


@router.post("/models/{model_id}/sim", response_model=SimOut, status_code=202)
def create_job(model_id: int, body: SimCreate, user: CurrentUser, db: DB):
    """Simulyatsiyani navbatga qo'yadi (L3: DB navbati, restartda yo'qolmaydi; `idempotency_key` bilan takror
    so'rov shu ishni qaytaradi). SIM-02: har qanday tur (analitik, maxsus formula, CFD) — faqat muhandis+
    (ko'ruvchi 403; u ro'yxat, holat va natijani ko'radi). Byudjet, vaqt/xotira chegarasi va
    foydalanuvchi/loyiha kvotasi bilan cheklangan."""
    ratelimit.check("sim", str(user.id), get_settings().rate_sim_per_min)
    model = get_model_checked(db, model_id, user, Role.engineer)  # SIM-02: har qanday ishga tushirish — muhandis+
    settings = get_settings()
    if body.idempotency_key:
        existing = db.query(SimJob).filter_by(author_id=user.id, idempotency_key=body.idempotency_key).one_or_none()
        if existing is not None:
            return _out(existing, with_params=True)
    active_q = db.query(SimJob).filter(SimJob.status.in_([SimStatus.queued, SimStatus.running]))
    if active_q.filter(SimJob.author_id == user.id).count() >= settings.sim_max_active_per_user:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bir vaqtda {settings.sim_max_active_per_user} tadan ko'p simulyatsiya mumkin emas — "
            "avvalgilarini kuting",
        )
    project_model_ids = db.query(Model.id).filter(Model.project_id == model.project_id)
    if active_q.filter(SimJob.model_id.in_(project_model_ids)).count() >= settings.sim_max_active_per_project:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Loyihada bir vaqtda {settings.sim_max_active_per_project} tadan ko'p simulyatsiya mumkin emas",
        )
    if body.version_id is not None:
        v = db.get(Version, body.version_id)
        if v is None or v.model_id != model.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu modelga tegishli emas")
    params = dict(body.params)
    stl_info = None
    if body.kind == "cfd":
        # SEC-01: qat'iy sxema (tur, chegara, noma'lum maydon yo'q) — xato 422, case yozishdan oldin
        try:
            parse_params(params)
        except CfdValidationError as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"CFD parametrlari xato: {format_errors(e)}"
            ) from None
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    try:  # tez validatsiya — xato bo'lsa darhol 400
        if body.kind == "hydro":
            _hydro_from_site(params, model.project.site)
            scenario.parse(params)
        elif body.kind == "cfd":
            if get_settings().cfd_mode == "off":
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "CFD bu serverda o'chirilgan"
                )
            if params.get("kind") == "geometry":
                # Model geometriyasi: tanlangan elementlar → STL (bbox parametrlarga)
                guids = [g for g in params.get("element_guids") or [] if g]
                if body.version_id is None or not guids:
                    raise ValueError(
                        "geometry: version_id va element_guids (tanlangan elementlar) kerak"
                    )
                from ..models import geometry as geom

                v = db.get(Version, body.version_id)
                with tempfile.TemporaryDirectory() as tmp:
                    stl_info = geom.write_stl(
                        storage.resolve(v.file_sha256), guids, Path(tmp) / "body.stl"
                    )
                    params["bbox"] = stl_info["bbox"]
                    params["stl_elements"] = stl_info["elements"]
                    params["stl_triangles"] = stl_info["triangles"]
                    build_case(params, Path(tmp))
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    build_case(params, Path(tmp))
        elif body.kind == "custom":
            # Shablon: saqlangan (template_id) yoki inline; ishga reproduksiya uchun inline saqlanadi
            tid = params.get("template_id")
            if tid is not None:
                t = db.get(SimTemplate, int(tid))
                if t is None or t.project_id != model.project_id:
                    raise ValueError("Shablon topilmadi yoki boshqa loyihaniki")
                params["template"] = t.template
                params.setdefault("template_name", t.name)
            if not isinstance(params.get("template"), dict):
                raise ValueError("custom: template yoki template_id kerak")
            custom.validate_template(params["template"])
        elif body.kind in catalog.REGISTRY:
            params = catalog.parse(body.kind, params)
        else:
            raise ValueError(f"kind: {', '.join(catalog.kinds())}")
    except (KeyError, TypeError, ValueError, NameError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Parametrlar xato: {e}") from e
    job = SimJob(
        model_id=model.id,
        version_id=body.version_id,
        author_id=user.id,
        kind=body.kind,
        name=body.name or _default_name(body.kind, params),
        params=params,
        idempotency_key=body.idempotency_key or None,
        max_attempts=1 if body.kind == "cfd" else 2,  # CFD soatlab — avtomatik qayta urinilmaydi
    )
    db.add(job)
    db.flush()
    if stl_info is not None:
        # STL ni case papkasiga — run_job (yoki worker) build_case dan oldin shu yerda topadi
        from ..models import geometry as geom

        geom.write_stl(
            storage.resolve(db.get(Version, body.version_id).file_sha256),
            [g for g in params["element_guids"] if g],
            _case_dir(job.id) / "constant" / "triSurface" / "body.stl",
        )
    audit.log(
        db,
        user_id=user.id,
        action="sim.create",
        target_type="sim_job",
        target_id=job.id,
        project_id=model.project_id,
        detail={"kind": job.kind, "name": job.name},
    )
    db.commit()
    db.refresh(job)
    jobs.kick()  # jarayon ichidagi ishchi darhol oladi (CFD worker rejimida — tashqi ishchi)
    return _out(job, with_params=True)


def _default_name(kind: str, params: dict) -> str:
    if kind == "cfd":
        return params.get("kind", "cfd")
    if kind == "hydro":
        return params.get("operation", {}).get("mode", "hydro")
    if kind == "custom":
        return params.get("template_name") or params.get("template", {}).get("name") or "maxsus"
    return catalog.REGISTRY[kind]["meta"].title


def _get_job(db, job_id: int, user) -> SimJob:
    job = db.get(SimJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulyatsiya topilmadi")
    get_model_checked(db, job.model_id, user, Role.viewer)
    return job


@router.get("/sim/{job_id}", response_model=SimOut)
def get_job(job_id: int, user: CurrentUser, db: DB):
    return _out(_get_job(db, job_id, user), with_params=True)


@router.get("/sim/{job_id}/result")
def get_result(job_id: int, user: CurrentUser, db: DB):
    job = _get_job(db, job_id, user)
    if job.status != SimStatus.done:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Holati: {job.status.value}")
    p = _result_path(job.id, job.kind)
    if not p.exists() and job.kind == "cfd":
        p = _result_path(job.id)  # eski joy (data/sim/<id>.json)
    if not p.exists():
        raise HTTPException(status.HTTP_410_GONE, "Natija fayli topilmadi")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/sim/{job_id}/log")
def get_log(job_id: int, user: CurrentUser, db: DB, lines: int = 80):
    """CFD: solver logining oxirgi qatorlari (diagnostika)."""
    job = _get_job(db, job_id, user)
    d = get_settings().data_dir / "cfd" / str(job.id)
    out = {}
    for name in ("run.log", "log.blockMesh", "log.simpleFoam", "log.interFoam", "log.setFields"):
        p = d / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
            out[name] = "\n".join(text.splitlines()[-lines:])
    return out


@router.delete("/sim/{job_id}", status_code=204)
def delete_job(job_id: int, user: CurrentUser, db: DB):
    job = _get_job(db, job_id, user)
    if job.author_id != user.id:
        get_model_checked(db, job.model_id, user, Role.approver)
    _result_path(job.id).unlink(missing_ok=True)
    shutil.rmtree(get_settings().data_dir / "cfd" / str(job.id), ignore_errors=True)
    db.delete(job)
    db.commit()
