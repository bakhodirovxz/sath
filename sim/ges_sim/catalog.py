"""Simulyatsiyalar katalogi: turi → meta, forma maydonlari, ishga tushirish funksiyasi.

Web forma `fields` bo'yicha avtomatik quriladi; `hydro` va `cfd` — o'z maxsus panellari bilan (custom_ui).
Guruhlar: gidrologiya, gidravlika, mustahkamlik, favqulodda, ekspluatatsiya, custom.
"""

from __future__ import annotations

from . import (
    advisor,
    cracking,
    dam_stability,
    dispatch,
    flood,
    governor,
    landslide,
    rainfall,
    schema,
    sediment,
    seepage,
    seismic,
    site,
    surge_tank,
    transformer,
    water_hammer,
)

GROUPS = {
    "gidrologiya": "Gidrologiya va energiya",
    "gidravlika": "Gidravlika (bosim, o'tish jarayonlari)",
    "mustahkamlik": "Mustahkamlik va xavfsizlik",
    "favqulodda": "Favqulodda holatlar",
    "ekspluatatsiya": "Ekspluatatsiya va resurs",
    "custom": "Maxsus (formulalar)",
}

_MODULES = [
    water_hammer,
    surge_tank,
    dam_stability,
    cracking,
    seepage,
    seismic,
    flood,
    rainfall,
    landslide,
    sediment,
    advisor,
    governor,
    dispatch,
    transformer,
]

REGISTRY: dict[str, dict] = {}
for m in _MODULES:
    REGISTRY[m.META.id] = {"meta": m.META, "fields": m.FIELDS, "run": m.run}

# Maxsus panelli turlar (forma avtomatik emas)
SPECIAL = {
    "hydro": schema.Meta(
        id="hydro",
        title="Suv ombori rejimi va energiya",
        description="Gidrograf → suv balansi → quvur → turbinalar: sath, sarflar, quvvat, ishlab chiqarish (kun/yil).",
        group="gidrologiya",
        icon="waves",
        formulas=["V' = Q_in − Q_turb − Q_spill", "P = η·ρ·g·Q·H_net", "h_f = f·L/D·v²/2g"],
    ),
    "cfd": schema.Meta(
        id="cfd",
        title="CFD oqim (OpenFOAM)",
        description="Suv tashlagich / quvur / model geometriyasi bo'ylab oqim: tezlik, bosim maydoni, kuchlar.",
        group="gidravlika",
        icon="wind",
        formulas=["Navier–Stokes (RANS k-ε), interFoam (erkin sirt)"],
    ),
    "custom": schema.Meta(
        id="custom",
        title="Maxsus simulyatsiya (formulalar)",
        description="O'z formulalaringiz bilan qadamma-qadam hisob: kirishlar, holat, tenglamalar, chiqishlar, ogohlantirishlar.",
        group="custom",
        icon="code",
        formulas=["Foydalanuvchi belgilaydi"],
    ),
}


def catalog() -> list[dict]:
    out = []
    for e in REGISTRY.values():
        d = e["meta"].to_dict()
        d["fields"] = [f.to_dict() for f in e["fields"]]
        d["custom_ui"] = False
        out.append(d)
    for m in SPECIAL.values():
        d = m.to_dict()
        d["fields"] = []
        d["custom_ui"] = True
        out.append(d)
    return out


def kinds() -> list[str]:
    return list(REGISTRY) + list(SPECIAL)


def parse(kind: str, params: dict) -> dict:
    e = REGISTRY.get(kind)
    if e is None:
        raise ValueError(f"Noma'lum simulyatsiya turi: {kind}")
    return schema.parse(e["fields"], params)


def run(kind: str, params: dict) -> dict:
    e = REGISTRY.get(kind)
    if e is None:
        raise ValueError(f"Noma'lum simulyatsiya turi: {kind}")
    return e["run"](schema.parse(e["fields"], params))


def site_values(kind: str, site_profile: dict | None) -> dict:
    """Maydon pasportidan forma qiymatlari — faqat maydon chegaralariga mos keladiganlari."""
    e = REGISTRY.get(kind)
    if e is None or not site_profile:
        return {}
    raw = site.apply(kind, site_profile)
    by_key = {f.key: f for f in e["fields"]}
    out = {}
    for k, v in raw.items():
        f = by_key.get(k)
        if f is None:
            continue
        if f.type in ("number", "int"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if (f.min is not None and v < f.min) or (f.max is not None and v > f.max):
                continue
        elif f.type == "select" and str(v) not in [o[0] for o in f.options]:
            continue
        out[k] = v
    return out
