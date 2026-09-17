"""OpenFOAM case ni ishga tushirish (Docker yoki lokal) va natijalarni JSON ga o'qish."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .case import RHO, G, GeometryCase, PenstockCase, SpillwayCase

DEFAULT_IMAGE = "opencfd/openfoam-default:2406"


def openfoam_available() -> str | None:
    """'local' — lokal OpenFOAM (WM_PROJECT_DIR), 'docker' — docker bor, None — yo'q."""
    if os.environ.get("WM_PROJECT_DIR") and shutil.which("simpleFoam"):
        return "local"
    if shutil.which("docker"):
        return "docker"
    return None


def run_case(
    case_dir: Path,
    total: float,
    *,
    mode: str | None = None,
    image: str = DEFAULT_IMAGE,
    on_progress: Callable[[float, str], None] | None = None,
    timeout_s: int = 3600,
    cpus: float = 2.0,
) -> None:
    """Allrun ni bajaradi; `total` — progress uchun (iteratsiya soni yoki endTime).
    Log dan "Time = X" o'qib on_progress(x/total, satr) chaqiradi. Xato — RuntimeError."""
    mode = mode or openfoam_available()
    if mode is None:
        raise RuntimeError("OpenFOAM topilmadi: docker yoki lokal o'rnatma kerak")
    case_dir = case_dir.resolve()
    if mode == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            f"--cpus={cpus}",
            "-v",
            f"{case_dir}:/work",
            "-w",
            "/work",
            image,
            "bash",
            "-c",
            "source /openfoam/bash.rc 2>/dev/null; cd /work && sh ./Allrun",
        ]
    else:
        cmd = ["bash", "-c", "sh ./Allrun"]
    log_path = case_dir / "run.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, cwd=case_dir, stdout=log, stderr=subprocess.STDOUT)
        start = time.time()
        last = -1.0
        while proc.poll() is None:
            time.sleep(2)
            if time.time() - start > timeout_s:
                proc.kill()
                raise RuntimeError(f"CFD vaqt chegarasidan oshdi ({timeout_s}s)")
            p = _progress(case_dir, total)
            if on_progress and p > last:
                on_progress(p, _last_time_line(case_dir))
                last = p
    if not (case_dir / "DONE").exists():
        tail = _tail(log_path)
        raise RuntimeError("OpenFOAM xato bilan tugadi:\n" + tail)
    if on_progress:
        on_progress(1.0, "tugadi")


def _solver_log(case_dir: Path) -> Path | None:
    for name in ("log.simpleFoam", "log.interFoam"):
        p = case_dir / name
        if p.exists():
            return p
    return None


def _last_time_line(case_dir: Path) -> str:
    p = _solver_log(case_dir)
    if not p:
        return "mesh…"
    try:
        with open(p, "rb") as fh:
            fh.seek(max(fh.tell() - 4000, 0), 0)
            fh.seek(-min(4000, p.stat().st_size), 2)
            chunk = fh.read().decode("utf-8", errors="replace")
        m = re.findall(r"^Time = ([0-9.e+-]+)", chunk, re.M)
        return f"Time = {m[-1]}" if m else "solver…"
    except OSError:
        return ""


def _progress(case_dir: Path, total: float) -> float:
    line = _last_time_line(case_dir)
    m = re.search(r"Time = ([0-9.e+-]+)", line)
    if not m:
        return 0.02 if (case_dir / "log.blockMesh").exists() else 0.0
    return min(float(m.group(1)) / total, 0.99)


def _tail(path: Path, n: int = 30) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


# ---------- Natijalarni o'qish ----------


def _read_raw(path: str | None) -> list[list[float]]:
    rows: list[list[float]] = []
    if not path:
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            try:
                rows.append([float(x) for x in line.replace("(", " ").replace(")", " ").split()])
            except ValueError:
                continue
    return rows


def _latest(pattern: str) -> str | None:
    files = glob.glob(pattern)
    if not files:
        return None
    # postProcessing/<func>/<time>/file — eng katta time
    return max(
        files, key=lambda f: float(Path(f).parent.name) if _isnum(Path(f).parent.name) else -1
    )


def _isnum(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _decimate(rows: list, max_points: int) -> list:
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    return [rows[int(i * step)] for i in range(max_points)]


def collect_results(case, case_dir: Path) -> dict:
    if isinstance(case, PenstockCase):
        return _collect_penstock(case, case_dir)
    if isinstance(case, SpillwayCase):
        return _collect_spillway(case, case_dir)
    if isinstance(case, GeometryCase):
        return _collect_geometry(case, case_dir)
    raise TypeError(type(case))


def _collect_geometry(case: GeometryCase, d: Path) -> dict:
    """Gorizontal kesim (z markaz) — bosim/tezlik xaritasi; jism sirtidagi bosim; kuchlar."""
    ax = 0 if case.flow_axis == "x" else 1
    p_plane = _read_raw(_latest(str(d / "postProcessing/plane/*/p_plane.raw")) or "")
    u_plane = _read_raw(_latest(str(d / "postProcessing/plane/*/U_plane.raw")) or "")
    p_body = _read_raw(_latest(str(d / "postProcessing/plane/*/p_body.raw")) or "")
    plane = _decimate(
        [
            {
                "x": round(pp[ax], 4),
                "y": round(pp[1 - ax], 4),
                "p": round(pp[3] * RHO, 1),
                "u": round((u[3] ** 2 + u[4] ** 2 + u[5] ** 2) ** 0.5, 4),
            }
            for pp, u in zip(p_plane, u_plane, strict=False)
        ],
        6000,
    )
    body_p = [r[3] * RHO for r in p_body]
    force = _read_forces(d)
    umax = max((pt["u"] for pt in plane), default=0.0)
    return {
        "kind": "geometry",
        "inputs": case.summary_inputs(),
        "plane": plane,
        "body_pressure": {
            "points": _decimate(
                [
                    {
                        "x": round(r[0], 3),
                        "y": round(r[1], 3),
                        "z": round(r[2], 3),
                        "p": round(r[3] * RHO, 1),
                    }
                    for r in p_body
                ],
                4000,
            )
        },
        "summary": {
            "force_n": force,
            "drag_n": force[ax] if force else None,
            "max_velocity": round(umax, 4),
            "inlet_velocity": case.velocity_ms,
            "body_p_min_pa": round(min(body_p), 1) if body_p else None,
            "body_p_max_pa": round(max(body_p), 1) if body_p else None,
            "cells": _cell_count(d),
        },
    }


def _read_forces(d: Path) -> list[float] | None:
    """postProcessing/forces/<t>/force.dat oxirgi qatori: total (x y z) — N."""
    path = _latest(str(d / "postProcessing/forces/*/force.dat"))
    if not path:
        return None
    last = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        last = line
    if not last:
        return None
    nums = [float(v) for v in last.replace("(", " ").replace(")", " ").split() if _isnum(v)]
    return [round(v, 2) for v in nums[1:4]] if len(nums) >= 4 else None


def _collect_penstock(case: PenstockCase, d: Path) -> dict:
    axis = _read_raw(_latest(str(d / "postProcessing/sample/*/axis_*.xy")) or "")
    radial = _read_raw(_latest(str(d / "postProcessing/sample/*/radial_*.xy")) or "")
    p_plane = _read_raw(_latest(str(d / "postProcessing/plane/*/p_plane.raw")) or "")
    u_plane = _read_raw(_latest(str(d / "postProcessing/plane/*/U_plane.raw")) or "")
    # sets raw ustunlar: koordinata p Ux Uy Uz;  plane raw: x y z p  /  x y z Ux Uy Uz
    axis_x = [r[0] for r in axis]
    axis_head = [r[1] / G for r in axis]  # kinematik bosim (m²/s²) → napor, m
    axis_u = [(r[2] ** 2 + r[3] ** 2 + r[4] ** 2) ** 0.5 for r in axis]
    radial_r = [r[0] for r in radial]
    radial_u = [(r[2] ** 2 + r[3] ** 2 + r[4] ** 2) ** 0.5 for r in radial]
    dp_head = (axis_head[0] - axis_head[-1]) if len(axis_head) > 1 else 0.0
    L_sampled = (axis_x[-1] - axis_x[0]) if len(axis_x) > 1 else case.length_m
    plane = _decimate(
        [
            {
                "x": round(p[0], 4),
                "y": round(p[1], 4),
                "p": round(p[3] * RHO, 1),
                "u": round((u[3] ** 2 + u[4] ** 2 + u[5] ** 2) ** 0.5, 4),
            }
            for p, u in zip(p_plane, u_plane, strict=False)
        ],
        6000,
    )
    return {
        "kind": "penstock",
        "inputs": case.summary_inputs(),
        "axis": {
            "x": [round(v, 4) for v in axis_x],
            "head_m": [round(v, 5) for v in axis_head],
            "u": [round(v, 4) for v in axis_u],
        },
        "radial": {"r": [round(v, 4) for v in radial_r], "u": [round(v, 4) for v in radial_u]},
        "plane": plane,
        "summary": {
            "head_loss_m": round(dp_head, 5),
            "head_loss_per_100m": round(dp_head / L_sampled * 100, 5) if L_sampled else None,
            "pressure_drop_pa": round(dp_head * RHO * G, 1),
            "max_velocity": round(max(axis_u + radial_u, default=0.0), 4),
            "inlet_velocity": round(case.inlet_velocity, 4),
            "cells": _cell_count(d),
        },
    }


def _collect_spillway(case: SpillwayCase, d: Path) -> dict:
    water = _read_raw(_latest(str(d / "postProcessing/surface/*/alpha.water_water.raw")) or "")
    alpha_plane = _read_raw(
        _latest(str(d / "postProcessing/surface/*/alpha.water_plane.raw")) or ""
    )
    u_plane = _read_raw(_latest(str(d / "postProcessing/surface/*/U_plane.raw")) or "")
    # Suv sirti profili: x bo'yicha 0.1 m bo'laklar, har birida eng yuqori y (havo pufaklarini e'tiborsiz)
    prof: dict[int, float] = {}
    for r in water:
        k = int(r[0] / 0.1)
        prof[k] = max(prof.get(k, -1), r[1])
    profile = [{"x": round(k * 0.1, 2), "y": round(y, 3)} for k, y in sorted(prof.items())]
    plane = _decimate(
        [
            {
                "x": round(a[0], 3),
                "y": round(a[1], 3),
                "alpha": round(a[3], 3),
                "u": round((u[3] ** 2 + u[4] ** 2 + u[5] ** 2) ** 0.5, 3),
            }
            for a, u in zip(alpha_plane, u_plane, strict=False)
        ],
        8000,
    )
    # Ostona ustidagi chuqurlik: ostona o'rtasida
    xm = case.upstream_m + case.crest_length_m / 2
    over = [p for p in profile if abs(p["x"] - xm) < 0.3]
    depth_over_crest = (max(p["y"] for p in over) - case.crest_height_m) if over else None
    q_out = _outlet_flow(d)
    max_u = max((p["u"] for p in plane if p["alpha"] > 0.5), default=0.0)
    return {
        "kind": "spillway",
        "inputs": case.summary_inputs(),
        "profile": profile,
        "plane": plane,
        "summary": {
            "unit_discharge_in": round(case.q, 4),
            "unit_discharge_out": round(q_out, 4) if q_out is not None else None,
            "depth_over_crest_m": round(depth_over_crest, 3)
            if depth_over_crest is not None
            else None,
            "critical_depth_m": round((case.q**2 / G) ** (1 / 3), 3),
            "max_velocity": round(max_u, 3),
            "cells": _cell_count(d),
        },
    }


def _outlet_flow(d: Path) -> float | None:
    f = _latest(str(d / "postProcessing/outletFlow/*/surfaceFieldValue.dat"))
    if not f:
        return None
    rows = _read_raw(f)
    if not rows:
        return None
    # oxirgi 10 % qiymatlarning o'rtachasi (statsionar holat); chiqishda flux musbat
    tail = rows[max(len(rows) - max(len(rows) // 10, 1), 0) :]
    return abs(sum(r[1] for r in tail) / len(tail))


def _cell_count(d: Path) -> int | None:
    log = d / "log.blockMesh"
    if not log.exists():
        return None
    m = re.search(r"nCells:\s*(\d+)", log.read_text(encoding="utf-8", errors="replace"))
    return int(m.group(1)) if m else None
