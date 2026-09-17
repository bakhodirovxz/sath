"""Xavfsizlik tekshiruvi — standart ssenariylar to'plami bir bosishda (KMK 2.06.05 / ICOLD amaliyoti):
loyihaviy va tekshiruv toshqini, N−1 darvoza, darvozalar yopiq, zilzila → barqarorlik (statik/seysmik),
filtratsiya, yoriq, gidrozarba, ko'chki to'lqini. Har ssenariy pasport + model («Modeldan») qiymatlari bilan
katalog hisobini ishga tushiradi, natija SimJob sifatida saqlanadi va mezon bo'yicha baholanadi.

Natija: [{id, title, kind, status: ok|fail|warn|skip, metrics, message, job_id}] + umumiy ball."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ges_sim import catalog

Params = dict[str, Any]


@dataclass
class Scenario:
    id: str
    title: str
    kind: str
    why: str  # nima tekshiriladi (foydalanuvchiga)
    overrides: Callable[[Params, dict], Params]  # (params, kontekst) → o'zgartirilgan params
    judge: Callable[[dict, Params], tuple[str, str]]  # (summary, params) → (status, xabar)
    metrics: list[str] = field(default_factory=list)  # summary kalitlari (jadval uchun)


def _n1_gate(p: Params) -> float:
    n = int(p.get("gates") or 2)
    return max(0.0, (n - 1) / n) if n > 1 else 0.0


def _flood_judge(min_freeboard: float):
    def judge(s: dict, _p: Params) -> tuple[str, str]:
        fb = float(s.get("freeboard_m") or 0)
        if s.get("overtopped"):
            return "fail", f"suv gerbdan {-fb:.2f} m oshadi (t = {s.get('overtop_start_h')} soat)"
        if fb < min_freeboard:
            return "warn", f"zaxira {fb:.2f} m < {min_freeboard} m"
        return "ok", f"zaxira {fb:.2f} m, maks. sath {s.get('max_level_m')} m"

    return judge


def _stab_judge(s: dict, p: Params) -> tuple[str, str]:
    fo, fs = float(s.get("fs_overturning") or 0), float(s.get("fs_sliding") or 0)
    ro, rs = float(p.get("req_overturning") or 1.5), float(p.get("req_sliding") or 1.5)
    if fo < ro or fs < rs:
        return "fail", f"K_ag'd {fo:.2f} (talab {ro}), K_sirp {fs:.2f} (talab {rs})"
    heel = s.get("sigma_heel_mpa")
    if heel is not None and float(heel) < 0:
        return "warn", f"yuqori tovonda cho'zilish {float(heel):.2f} MPa"
    return "ok", f"K_ag'd {fo:.2f}, K_sirp {fs:.2f}"


def _ok_judge(s: dict, _p: Params) -> tuple[str, str]:
    return ("ok" if s.get("ok") is not False else "fail"), str(s.get("verdict") or "")


def _seismic_judge(s: dict, _p: Params) -> tuple[str, str]:
    return "ok", f"PGA {s.get('pga_g')} g, k_h {s.get('kh')}"


SCENARIOS: list[Scenario] = [
    Scenario(
        "flood_design",
        "Loyihaviy toshqin (0.1 %)",
        "flood",
        "NPU dan boshlab loyihaviy toshqin; darvozalar ochiq, turbinalar ishlaydi — zaxira ≥ 1 m",
        lambda p, c: {
            **p,
            "initial_level_m": c["npu"],
            "peak_m3s": c["q01"],
            "gate_opening": 1.0,
            "breach": "none",
        },
        _flood_judge(1.0),
        ["max_level_m", "freeboard_m", "peak_outflow_m3s"],
    ),
    Scenario(
        "flood_check",
        "Tekshiruv toshqini (0.01 %)",
        "flood",
        "FPU dan boshlab tekshiruv toshqini, turbinalar to'xtagan — gerbdan oshmasin",
        lambda p, c: {
            **p,
            "initial_level_m": c["fpu"],
            "peak_m3s": c["q001"],
            "gate_opening": 1.0,
            "turbine_m3s": 0.0,
            "breach": "none",
        },
        _flood_judge(0.0),
        ["max_level_m", "freeboard_m", "peak_outflow_m3s"],
    ),
    Scenario(
        "flood_n1",
        "Tekshiruv toshqini, N−1 darvoza",
        "flood",
        "Bitta darvoza ishlamay qolgan (avariya) — gerbdan oshmasin",
        lambda p, c: {
            **p,
            "initial_level_m": c["fpu"],
            "peak_m3s": c["q001"],
            "gate_opening": _n1_gate(p),
            "turbine_m3s": 0.0,
            "breach": "none",
        },
        _flood_judge(0.0),
        ["max_level_m", "freeboard_m"],
    ),
    Scenario(
        "flood_closed",
        "Darvozalar yopiq (favqulodda)",
        "flood",
        "Loyihaviy toshqinda darvozalar ochilmadi — gerbdan oshishgacha vaqt (ma'lumot uchun)",
        lambda p, c: {
            **p,
            "initial_level_m": c["npu"],
            "peak_m3s": c["q01"],
            "gate_opening": 0.0,
            "turbine_m3s": 0.0,
            "breach": "none",
        },
        lambda s, p: (
            "warn" if s.get("overtopped") else "ok",
            f"oshishgacha {s.get('overtop_start_h')} soat" if s.get("overtopped") else "oshmaydi",
        ),
        ["max_level_m", "overtop_start_h"],
    ),
    Scenario(
        "seismic",
        "Zilzila (pasport seysmikligi)",
        "seismic",
        "Maydon seysmikligi (MSK-64) → PGA, to'g'on k_h, inshootlar spektral tezlanishi",
        lambda p, c: p,
        _seismic_judge,
        ["pga_g", "kh", "dam_sa_g"],
    ),
    Scenario(
        "stab_static",
        "To'g'on barqarorligi — statik, NPU",
        "dam_stability",
        "Ag'darilish/sirpanish zaxirasi ≥ 1.5, tag kuchlanishlari",
        lambda p, c: {
            **p,
            "headwater_m": c["npu"],
            "kh": 0.0,
            "req_overturning": 1.5,
            "req_sliding": 1.5,
        },
        _stab_judge,
        ["fs_overturning", "fs_sliding", "sigma_toe_mpa"],
    ),
    Scenario(
        "stab_seismic",
        "To'g'on barqarorligi — zilzila, NPU",
        "dam_stability",
        "Zilzila k_h bilan (talab ≥ 1.1)",
        lambda p, c: {
            **p,
            "headwater_m": c["npu"],
            "kh": c.get("kh") or p.get("kh") or 0.1,
            "req_overturning": 1.1,
            "req_sliding": 1.1,
        },
        _stab_judge,
        ["fs_overturning", "fs_sliding", "sigma_heel_mpa"],
    ),
    Scenario(
        "stab_flood",
        "To'g'on barqarorligi — FPU (toshqin)",
        "dam_stability",
        "Tekshiruv toshqini sathida (talab ≥ 1.3)",
        lambda p, c: {
            **p,
            "headwater_m": c["fpu"],
            "kh": 0.0,
            "req_overturning": 1.3,
            "req_sliding": 1.3,
        },
        _stab_judge,
        ["fs_overturning", "fs_sliding"],
    ),
    Scenario(
        "seepage",
        "Filtratsiya / suffoziya",
        "seepage",
        "Chiqish gradiyenti va suffoziya zaxirasi ≥ 1.5",
        lambda p, c: p,
        _ok_judge,
        ["exit_gradient", "fs_piping", "q_total_l_s"],
    ),
    Scenario(
        "cracking",
        "Yoriq xavfi",
        "cracking",
        "Cho'zilish kuchlanishlari, issiqlik indeksi, moyil joylar",
        lambda p, c: p,
        _ok_judge,
        ["max_tension_mpa", "crack_zone_pct", "min_k_hydraulic"],
    ),
    Scenario(
        "water_hammer",
        "Gidrozarba (yuk tashlash)",
        "water_hammer",
        "Zadvijka yopilishida maksimal napor — quvur mustahkamligi zaxirasi ≥ 1.5, kavitatsiya yo'q",
        lambda p, c: p,
        _ok_judge,
        ["h_max_m", "safety_factor", "p_max_bar"],
    ),
    Scenario(
        "landslide",
        "Tog' ko'chishi → to'lqin",
        "landslide",
        "Pasportdagi ko'chki hajmi — to'lqin gerbdan oshmasin",
        lambda p, c: p,
        _ok_judge,
        ["a_max_m", "runup_m", "overtop_m"],
    ),
]


def context(site: dict) -> dict:
    """Ssenariylar uchun umumiy kattaliklar (pasportdan)."""
    npu = float(site.get("normal_level_m") or 0)
    return {
        "npu": npu,
        "fpu": float(site.get("max_level_m") or npu),
        "q01": float(site.get("flood_01_m3s") or 0),
        "q001": float(site.get("flood_001_m3s") or site.get("flood_01_m3s") or 0),
    }


def run_all(
    prefill: Callable[[str], dict],
    site: dict,
    save: Callable[[Scenario, Params, dict], int | None] | None = None,
) -> dict:
    """prefill(kind) → {site, model} qiymatlari; save(scenario, params, result) → job_id (ixtiyoriy)."""
    ctx = context(site)
    rows = []
    for sc in SCENARIOS:
        if sc.kind not in catalog.REGISTRY:
            continue
        pf = prefill(sc.kind)
        params: Params = {**pf.get("site", {}), **pf.get("model", {})}
        try:
            params = sc.overrides(params, ctx)
            if sc.kind == "flood" and not (params.get("curve_elev") and params.get("curve_vol")):
                raise ValueError("sath–hajm egri chizig'i yo'q (pasport)")
            result = catalog.run(sc.kind, params)
        except (KeyError, TypeError, ValueError, NameError, ZeroDivisionError) as e:
            rows.append(
                {
                    "id": sc.id,
                    "title": sc.title,
                    "kind": sc.kind,
                    "why": sc.why,
                    "status": "skip",
                    "message": f"hisoblanmadi: {e}",
                    "metrics": {},
                    "job_id": None,
                }
            )
            continue
        s = result["summary"]
        if sc.id == "seismic":
            ctx["kh"] = s.get("kh")
        status, msg = sc.judge(s, params)
        job_id = save(sc, params, result) if save else None
        rows.append(
            {
                "id": sc.id,
                "title": sc.title,
                "kind": sc.kind,
                "why": sc.why,
                "status": status,
                "message": msg,
                "metrics": {k: s.get(k) for k in sc.metrics if k in s},
                "job_id": job_id,
            }
        )
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_fail = sum(1 for r in rows if r["status"] == "fail")
    n_warn = sum(1 for r in rows if r["status"] == "warn")
    n_done = n_ok + n_fail + n_warn
    score = round(100 * (n_ok + 0.5 * n_warn) / n_done) if n_done else 0
    return {
        "rows": rows,
        "score": score,
        "counts": {"ok": n_ok, "warn": n_warn, "fail": n_fail, "skip": len(rows) - n_done},
        "verdict": "Xavfsiz — barcha mezonlar bajarildi"
        if n_fail == 0 and n_warn == 0
        else (f"{n_fail} ta mezon bajarilmadi" if n_fail else f"{n_warn} ta ogohlantirish"),
    }


def _path(model_id: int):
    from ..config import get_settings

    d = get_settings().data_dir / "sim"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"safety_{model_id}.json"


def store(model_id: int, res: dict, version_id: int | None) -> None:
    """Oxirgi tekshiruv xulosasi (model kartochkasi uchun)."""
    from datetime import datetime, timezone

    brief = {
        "score": res["score"],
        "counts": res["counts"],
        "verdict": res["verdict"],
        "version_id": version_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "fails": [r["title"] for r in res["rows"] if r["status"] == "fail"],
    }
    _path(model_id).write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")


def last(model_id: int) -> dict | None:
    p = _path(model_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def to_json(res: dict) -> str:
    return json.dumps(res, ensure_ascii=False)
