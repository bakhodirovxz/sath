"""P4 byudjetlari (headless, spec §5): Sath import + register < 150 ms (Bonsai siz va bilan, 3 urinishdan eng
yaxshisi), register da og'ir modullar (numpy, ifcopenshell, ezdxf, assimp_py) yuklanmaydi, perf logi (yadro
qismlari va modullar) chiqadi. Har o'lchov alohida toza Blender jarayonida (perf_blender.py --budget)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import bpy

PERF = Path(__file__).resolve().parents[1] / "perf_blender.py"


def _run(bonsai: bool) -> tuple[dict, str]:
    cmd = [bpy.app.binary_path, "-b", "--factory-startup", "--python", str(PERF), "--", "--budget"]
    if bonsai:
        cmd.append("--bonsai")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = r.stdout.splitlines()
    line = next((ln for ln in lines if ln.startswith("BUDGET ")), None)
    assert line is not None, r.stdout[-3000:] + r.stderr[-2000:]
    log = next((ln for ln in lines if ln.startswith("[sath] register")), "")
    return json.loads(line[len("BUDGET ") :]), log


def run(ctx):
    from sath.core import budget

    for bonsai in (False, True):
        runs = [_run(bonsai) for _ in range(3)]
        times = [r["register_ms"] for r, _log in runs]
        label = "Bonsai bilan" if bonsai else "Bonsai siz"
        assert min(times) < budget.REGISTER_MS, f"register ({label}): {times} ms"
        heavy = sorted({h for r, _log in runs for h in r["heavy"]})
        assert heavy == [], f"register da og'ir importlar ({label}): {heavy} — funksiya ichiga ko'chiring"
        for _r, log in runs:
            assert "(byudjet < 150)" in log and "[modullar: " in log and "bim " in log, log
        print(f"budgets ({label}): register {times} ms | {runs[0][1]}", flush=True)
