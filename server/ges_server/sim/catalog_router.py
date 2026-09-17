"""Simulyatsiya katalogi, maydon pasporti (site), maxsus shablonlar, forma uchun oldindan to'ldirish."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from ges_sim import catalog, custom, materials, schema, site
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, check_project_role, require_project_role
from ..models import storage
from ..models.router import get_model_checked
from ..orm import DraftObject, Project, Role, SimTemplate, Version, utcnow
from . import ges_params

router = APIRouter(prefix="/api", tags=["simulation"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]


@router.get("/sim/catalog")
def sim_catalog(_: CurrentUser):
    """Barcha simulyatsiya turlari: meta, forma maydonlari, formulalar; guruhlar; pasport sxemasi."""
    return {
        "kinds": catalog.catalog(),
        "groups": catalog.GROUPS,
        "site_fields": [f.to_dict() for f in site.SITE_FIELDS],
    }


@router.get("/sim/materials")
def sim_materials(_: CurrentUser):
    """Materiallar katalogi: beton klasslari, sement, po'lat, gruntlar, zonalar bo'yicha tavsiya."""
    return materials.catalog()


class SweepIn(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    key: str  # o'zgartiriladigan maydon
    values: list[float] = Field(min_length=2, max_length=60)


@router.post("/sim/sweep")
def sim_sweep(body: SweepIn, _: CurrentUser):
    """Sezgirlik tahlili: bitta parametrni qiymatlar bo'yicha o'zgartirib, xulosa ko'rsatkichlarini qaytaradi
    (sinxron; katalog hisoblari tez — soniyadan kam). Natija saqlanmaydi (ish yaratilmaydi)."""
    if body.kind not in catalog.REGISTRY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faqat katalog simulyatsiyalari")
    fields = {f.key: f for f in catalog.REGISTRY[body.kind]["fields"]}
    f = fields.get(body.key)
    if f is None or f.type not in ("number", "int"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "key — sonli maydon bo'lishi kerak")
    rows = []
    for v in body.values:
        params = {**body.params, body.key: v}
        try:
            r = catalog.run(body.kind, params)
            summary = {
                k: x
                for k, x in r["summary"].items()
                if isinstance(x, (int, float, str, bool)) or x is None
            }
            rows.append({"value": v, "summary": summary, "error": None})
        except (KeyError, TypeError, ValueError, NameError, ZeroDivisionError) as e:
            rows.append({"value": v, "summary": {}, "error": str(e)})
    outputs = [o for o in catalog.REGISTRY[body.kind]["meta"].outputs]
    return {"key": body.key, "label": f.label, "unit": f.unit, "rows": rows, "outputs": outputs}


@router.get("/sim/custom-example")
def custom_example(_: CurrentUser):
    return custom.example_template()


class CustomPreview(BaseModel):
    template: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)


@router.post("/sim/custom-preview")
def custom_preview(body: CustomPreview, _: CurrentUser):
    """Shablonni saqlamasdan sinab ko'rish (tez, ≤ 20 000 qadam)."""
    t = dict(body.template)
    if int(t.get("steps", 100)) > 20000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sinov uchun steps ≤ 20000")
    try:
        return custom.run(t, body.inputs)
    except (ValueError, NameError, TypeError, ZeroDivisionError, IndexError, KeyError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shablon xatosi: {e}") from e


# --- Maydon pasporti ---
@router.get("/projects/{project_id}/site")
def get_site(project: ViewerProject):
    """Pasport qiymatlari (defaultlar bilan to'ldirilgan) + to'ldirilganlik."""
    filled = project.site or {}
    return {
        "values": {**site.defaults(), **filled},
        "filled": bool(filled),
        "risks": site.risk_summary({**site.defaults(), **filled}) if filled else [],
    }


@router.put("/projects/{project_id}/site")
def put_site(project: EngineerProject, body: dict[str, Any], user: CurrentUser, db: DB):
    """Pasportni saqlash (muhandis). Qiymatlar sxema bo'yicha tekshiriladi."""
    try:
        values = schema.parse(site.SITE_FIELDS, body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    project.site = values
    audit.log(
        db,
        user_id=user.id,
        action="project.site",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"fields": len(values)},
    )
    db.commit()
    return {"values": values, "filled": True, "risks": site.risk_summary(values)}


# --- Forma uchun oldindan to'ldirish: pasport + model (Pset_GES) + jonli (SCADA) ---
def _live_values(db, project: Project) -> dict[str, float]:
    from ..monitoring import twin

    sensors = twin.Sensor
    rows = db.query(sensors).filter_by(project_id=project.id, enabled=True).all()
    slots = twin._slots(db, project, rows)
    out: dict[str, float] = {}
    for key in ("upstream_level", "downstream_level", "inflow", "penstock_flow"):
        v = twin._live(slots.get(key))
        if v is not None:
            out[key] = v
    p_total = sum((twin._live(slots.get(f"unit{i}_power")) or 0) for i in (1, 2, 3, 4))
    if any(slots.get(f"unit{i}_power") for i in (1, 2, 3, 4)):
        out["power"] = p_total
    st = {**site.defaults(), **(project.site or {})}
    if "upstream_level" in out and "downstream_level" in out:
        out["gross_head"] = out["upstream_level"] - out["downstream_level"]
    if "upstream_level" in out:
        out["upstream_depth"] = out["upstream_level"] - float(st["base_elevation_m"])
        out["freeboard"] = float(st["crest_elevation_m"]) - out["upstream_level"]
    return out


# Qoralama (web 3D) obyektlari → model yo'llari (IFC Pset bo'lmasa ham simulyatsiyaga uzatiladi)
_DRAFT_MAP = {
    "dam": {
        "length": "dam.length_m",
        "height": "dam.height_m",
        "crest": "dam.crest_width_m",
        "mu": "dam.upstream_slope",
        "md": "dam.downstream_slope",
    },
    "penstock": {"length": "penstock.length_m", "d": "penstock.diameter_m"},
    "spillway": {"width": "spillway.width_m"},
}
_FIELD_MODEL_FALLBACK = {
    "upstream_slope": "dam.upstream_slope",
    "downstream_slope": "dam.downstream_slope",
    "concrete_class": "dam.concrete_class",
    "material": "penstock.material",
}


def _draft_values(db, model_id: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in db.query(DraftObject).filter_by(model_id=model_id).order_by(DraftObject.id).all():
        mp = _DRAFT_MAP.get(d.kind)
        if not mp:
            continue
        for k, path in mp.items():
            if d.params.get(k) not in (None, ""):
                out.setdefault(path, d.params[k])
        ps = d.psets or {}
        dam = ps.get("Pset_GES_Dam") or {}
        if dam.get("TagBelgisi_m") not in (None, "", 0):
            out.setdefault("dam.base_elevation_m", dam["TagBelgisi_m"])
        if dam.get("GerbBelgisi_m") not in (None, "", 0):
            out.setdefault("dam.crest_elevation_m", dam["GerbBelgisi_m"])
        if dam.get("BetonKlassi"):
            out.setdefault("dam.concrete_class", dam["BetonKlassi"])
        pen = ps.get("Pset_GES_Penstock") or {}
        if pen.get("Material"):
            out.setdefault("penstock.material", pen["Material"])
        d_z = (d.transform or {}).get("z")
        if d.kind == "dam" and d_z is not None:
            out.setdefault("dam.base_elevation_m", d_z)
    return out


def _model_values(
    db, version_id: int | None, project_id: int, model_id: int | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if version_id is None:
        return _draft_values(db, model_id) if model_id else out
    v = db.get(Version, version_id)
    if v is None or v.model.project_id != project_id:
        # Boshqa loyiha versiyasi — Pset ma'lumotlari oshkor bo'lmasin (IDOR)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu loyihaga tegishli emas")
    try:
        g = ges_params.extract(storage.resolve(v.file_sha256))
    except Exception:  # noqa: BLE001
        g = {}
    if model_id:
        out.update(_draft_values(db, model_id))
    if g.get("dams"):
        d = g["dams"][0]
        for k, val in d.items():
            if val not in (None, "", "guid", "name") and k not in ("guid", "name"):
                out.setdefault(f"dam.{k}", val)
    if g.get("penstocks"):
        pen = g["penstocks"][0]
        for k in ("length_m", "diameter_m", "roughness_mm"):
            out.setdefault(f"penstock.{k}", pen[k])
    if g.get("spillways"):
        sp = g["spillways"][0]
        for k in ("crest_m", "width_m", "coefficient"):
            out.setdefault(f"spillway.{k}", sp[k])
    return out


@router.get("/models/{model_id}/sim/prefill")
def sim_prefill(model_id: int, kind: str, user: CurrentUser, db: DB, version_id: int | None = None):
    """Berilgan tur uchun: pasportdan (site), modeldan (model), jonli holatdan (live) qiymatlar."""
    model = get_model_checked(db, model_id, user, Role.viewer)
    project = model.project
    if kind not in catalog.REGISTRY:
        return {"site": {}, "model": {}, "live": {}}
    fields = catalog.REGISTRY[kind]["fields"]
    st = project.site or {}
    live_raw = _live_values(db, project)
    model_raw = _model_values(db, version_id, project.id, model.id)
    live = {f.key: live_raw[f.live] for f in fields if f.live and f.live in live_raw}
    mdl = {}
    for f in fields:
        path = f.model or _FIELD_MODEL_FALLBACK.get(f.key)
        if path and path in model_raw:
            val = model_raw[path]
            if f.type == "select" and str(val) not in [o[0] for o in f.options]:
                continue
            mdl[f.key] = val
    return {
        "site": catalog.site_values(kind, st),
        "model": mdl,
        "live": live,
        "site_filled": bool(st),
    }


# --- Xavfsizlik tekshiruvi (standart ssenariylar to'plami) ---
@router.post("/models/{model_id}/sim/safety-check")
def sim_safety_check(model_id: int, user: CurrentUser, db: DB, version_id: int | None = None):
    """Barcha standart xavfsizlik ssenariylarini (toshqinlar, N−1, zilzila, barqarorlik, filtratsiya, yoriq,
    gidrozarba, ko'chki) pasport + model qiymatlari bilan bir bosishda ishga tushiradi; har biri SimJob sifatida
    saqlanadi (name «Xavfsizlik: …»); natija — mezon bo'yicha ok/warn/fail jadvali va umumiy ball."""
    import json as _json

    from ..orm import SimJob, SimStatus
    from . import safety
    from .router import _result_path

    model = get_model_checked(db, model_id, user, Role.viewer)
    project = model.project
    if not project.site:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maydon pasporti to'ldirilmagan")
    if version_id is None and model.versions:
        version_id = model.versions[-1].id

    def prefill(kind: str) -> dict:
        return sim_prefill(model_id, kind, user, db, version_id)

    def save(sc, params, result) -> int:
        job = SimJob(
            model_id=model.id,
            version_id=version_id,
            author_id=user.id,
            kind=sc.kind,
            name=f"Xavfsizlik: {sc.title}",
            params=params,
            status=SimStatus.done,
            progress=1.0,
            summary=result["summary"],
            finished_at=utcnow(),
        )
        db.add(job)
        db.flush()
        _result_path(job.id).write_text(_json.dumps(result), encoding="utf-8")
        return job.id

    res = safety.run_all(prefill, project.site, save)
    safety.store(model.id, res, version_id)
    audit.log(
        db,
        user_id=user.id,
        action="sim.safety_check",
        target_type="model",
        target_id=model.id,
        project_id=project.id,
        detail={"score": res["score"], "counts": res["counts"], "version_id": version_id},
    )
    db.commit()
    res["version_id"] = version_id
    return res


@router.get("/sim/safety-scenarios")
def sim_safety_scenarios(_: CurrentUser):
    from . import safety

    return [{"id": s.id, "title": s.title, "kind": s.kind, "why": s.why} for s in safety.SCENARIOS]


# --- Maxsus shablonlar ---
class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    template: dict[str, Any]


class TemplateOut(BaseModel):
    id: int
    project_id: int
    author_id: int
    author_username: str
    name: str
    description: str
    template: dict
    created_at: datetime
    updated_at: datetime


def _tout(t: SimTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        project_id=t.project_id,
        author_id=t.author_id,
        author_username=t.author.username,
        name=t.name,
        description=t.description,
        template=t.template,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/projects/{project_id}/sim-templates", response_model=list[TemplateOut])
def list_templates(project: ViewerProject, db: DB):
    return [
        _tout(t)
        for t in db.query(SimTemplate)
        .filter_by(project_id=project.id)
        .order_by(SimTemplate.id)
        .all()
    ]


@router.post("/projects/{project_id}/sim-templates", response_model=TemplateOut, status_code=201)
def create_template(project: EngineerProject, body: TemplateIn, user: CurrentUser, db: DB):
    try:
        custom.validate_template(body.template)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shablon xatosi: {e}") from e
    t = SimTemplate(
        project_id=project.id,
        author_id=user.id,
        name=body.name,
        description=body.description,
        template=body.template,
    )
    db.add(t)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="sim_template.create",
        target_type="sim_template",
        target_id=t.id,
        project_id=project.id,
        detail={"name": t.name},
    )
    db.commit()
    db.refresh(t)
    return _tout(t)


def _get_template(db, template_id: int, user, role: Role) -> SimTemplate:
    t = db.get(SimTemplate, template_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")
    check_project_role(db, t.project_id, user, role)
    return t


@router.get("/sim-templates/{template_id}", response_model=TemplateOut)
def get_template(template_id: int, user: CurrentUser, db: DB):
    return _tout(_get_template(db, template_id, user, Role.viewer))


@router.put("/sim-templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, body: TemplateIn, user: CurrentUser, db: DB):
    t = _get_template(db, template_id, user, Role.engineer)
    try:
        custom.validate_template(body.template)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shablon xatosi: {e}") from e
    t.name, t.description, t.template, t.updated_at = (
        body.name,
        body.description,
        body.template,
        utcnow(),
    )
    audit.log(
        db,
        user_id=user.id,
        action="sim_template.update",
        target_type="sim_template",
        target_id=t.id,
        project_id=t.project_id,
        detail={"name": t.name},
    )
    db.commit()
    db.refresh(t)
    return _tout(t)


@router.delete("/sim-templates/{template_id}", status_code=204)
def delete_template(template_id: int, user: CurrentUser, db: DB):
    t = _get_template(db, template_id, user, Role.engineer)
    if t.author_id != user.id:
        check_project_role(db, t.project_id, user, Role.approver)
    audit.log(
        db,
        user_id=user.id,
        action="sim_template.delete",
        target_type="sim_template",
        target_id=t.id,
        project_id=t.project_id,
        detail={"name": t.name},
    )
    db.delete(t)
    db.commit()
