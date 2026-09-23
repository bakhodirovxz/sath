"""CFD parametrlari — har tur uchun qat'iy Pydantic sxemasi (SEC-01).

OpenFOAM dictionary fayllari f-string bilan yoziladi, shuning uchun foydalanuvchi qiymati hech qachon xom
satr bo'lib faylga tushmasligi kerak: raqamlar faqat `StrictInt`/`StrictFloat` (satr, bool, NaN/inf rad
etiladi), chegaralar `ge/gt/le`, noma'lum maydon — xato (`extra="forbid"`), matnli qiymatlar faqat ro'yxatdan
(`Literal`). Server API (422) va `build_case` (himoya chizig'i — DB dagi eski/qo'lda kiritilgan ish) ikkalasi
shu sxemadan o'tkazadi.

Solver fayllariga yozilmaydigan metama'lumotlar (`element_guid`, `element_guids`, server qo'shadigan
`stl_elements`/`stl_triangles`) ham sxemada — ular faqat web/3D uchun, case yozishda ishlatilmaydi.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, Strict, ValidationError

__all__ = ["CFD_PARAM_MODELS", "ValidationError", "format_errors", "parse_params"]

# Raqamlar: faqat JSON number (float maydonga int ham qabul qilinadi), satr/bool yo'q, NaN/inf yo'q
Int = Annotated[int, Strict()]
Guid = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z_$\-]+$")]


def _num(default: float | None, *, gt: float | None = None, ge: float | None = None, le: float) -> Any:
    """Qat'iy float maydon: default, chegaralar, NaN/inf yo'q."""
    return Field(default=default, gt=gt, ge=ge, le=le, allow_inf_nan=False, strict=True)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    # 3D da natijani qo'yish uchun (web); solver fayllariga yozilmaydi
    element_guid: Guid | None = None
    resolution: float = _num(1.0, ge=0.3, le=3.0)


class _StlElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # server o'zi yozadi (geometry.write_stl), solver fayllariga tushmaydi — nomsiz element (None) ham bo'lishi mumkin
    guid: str = Field(max_length=64)
    name: str | None = Field(default="", max_length=2048)
    type: str | None = Field(default="", max_length=128)


class PenstockParams(_Base):
    kind: Literal["penstock"] = "penstock"
    length_m: float = _num(20.0, gt=0, le=10_000)
    diameter_m: float = _num(2.4, gt=0, le=50)
    flow_m3s: float = _num(20.0, gt=0, le=10_000)
    roughness_mm: float = _num(0.1, ge=0, le=100)
    max_iterations: Int = Field(default=400, ge=10, le=20_000)


class SpillwayParams(_Base):
    kind: Literal["spillway"] = "spillway"
    crest_height_m: float = _num(3.0, gt=0, le=500)
    head_m: float = _num(1.0, gt=0, le=100)
    crest_length_m: float = _num(4.0, gt=0, le=1_000)
    upstream_m: float = _num(10.0, gt=0, le=5_000)
    downstream_m: float = _num(12.0, gt=0, le=5_000)
    unit_discharge_m2s: float | None = _num(None, gt=0, le=1_000)
    end_time_s: float = _num(15.0, gt=0, le=3_600)


Coord = Annotated[float, Strict(), Field(allow_inf_nan=False, ge=-1e7, le=1e7)]


class GeometryParams(_Base):
    kind: Literal["geometry"] = "geometry"
    element_guids: list[Guid] = Field(default_factory=list, max_length=500)
    # server yozadi (tanlangan elementlarning bbox i, metr) — [[x0,y0,z0],[x1,y1,z1]]
    bbox: list[Annotated[list[Coord], Field(min_length=3, max_length=3)]] = Field(
        default_factory=lambda: [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], min_length=2, max_length=2
    )
    velocity_ms: float = _num(2.0, gt=0, le=50)
    flow_axis: Literal["x", "y"] = "x"
    refinement: Int = Field(default=2, ge=1, le=3)
    max_iterations: Int = Field(default=300, ge=10, le=20_000)
    submerged: bool = True
    # server qo'shadigan metama'lumot (STL tarkibi)
    stl_elements: list[_StlElement] | None = Field(default=None, max_length=500)
    stl_triangles: Int | None = Field(default=None, ge=0)


CFD_PARAM_MODELS: dict[str, type[_Base]] = {
    "penstock": PenstockParams,
    "spillway": SpillwayParams,
    "geometry": GeometryParams,
}


def parse_params(params: Any) -> _Base:
    """JSON parametrlarni tur bo'yicha qat'iy tekshiradi. Xato — `ValueError` (tur noma'lum) yoki
    `pydantic.ValidationError` (u ham `ValueError` avlodi)."""
    if not isinstance(params, dict):
        raise ValueError("CFD parametrlari obyekt (dict) bo'lishi kerak")
    kind = params.get("kind", "penstock")
    cls = CFD_PARAM_MODELS.get(kind) if isinstance(kind, str) else None
    if cls is None:
        raise ValueError("Noma'lum CFD turi (penstock | spillway | geometry)")
    return cls.model_validate(params)


_MSG = {
    "int_type": "butun son bo'lishi kerak",
    "float_type": "son bo'lishi kerak",
    "bool_type": "true/false bo'lishi kerak",
    "string_type": "matn bo'lishi kerak",
    "list_type": "ro'yxat bo'lishi kerak",
    "finite_number": "chekli son bo'lishi kerak",
    "extra_forbidden": "noma'lum parametr",
    "literal_error": "ruxsat etilmagan qiymat",
    "string_pattern_mismatch": "ruxsat etilmagan belgilar",
    "too_short": "elementlar soni kam",
    "too_long": "elementlar soni ko'p",
}


def _limit_msg(err: dict) -> str | None:
    ctx = err.get("ctx") or {}
    t = err["type"]
    if t == "greater_than":
        return "musbat bo'lishi kerak" if ctx.get("gt") == 0 else f"{ctx.get('gt')} dan katta bo'lishi kerak"
    if t == "greater_than_equal":
        return f"kamida {ctx.get('ge')}"
    if t == "less_than_equal":
        return f"ko'pi bilan {ctx.get('le')}"
    return None


def format_errors(e: ValidationError) -> str:
    """Pydantic xatolarini qisqa o'zbekcha matnga: `max_iterations: butun son bo'lishi kerak; ...`.
    Kiritilgan qiymat matnga qo'shilmaydi (log/javobga xom satr tushmasin)."""
    parts = []
    for err in e.errors(include_url=False, include_input=False):
        loc = ".".join(str(x) for x in err.get("loc", ())) or "params"
        msg = _limit_msg(err) or _MSG.get(err["type"]) or err.get("msg", "xato")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts[:10])
