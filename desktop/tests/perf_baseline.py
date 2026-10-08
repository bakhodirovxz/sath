"""Desktop bazaviy o'lchov (P0): sovuq start (vanilla / +Bonsai / +Sath), register vaqti, RSS, katta IFC ochish.
Har o'lchov 3 marta, mediana. Natija docs/benchmark-desktop.md ga yoziladi.

  python desktop/tests/perf_baseline.py [--blender <exe>] [--n 2000]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))
REPEAT = 3


def wall(cmd: list[str]) -> float:
    t = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    return time.perf_counter() - t


def perf_json(exe: Path, n: int) -> dict:
    r = subprocess.run(
        [str(exe), "-b", "--python", str(ROOT / "desktop" / "tests" / "perf_blender.py"), "--", "--n", str(n)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith("PERF "))
    return json.loads(line[5:])


def median(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def blender_label(exe: Path) -> str:
    """Blender versiyasi + exe yo'li (uy papkasi `~` bilan almashtirilgan — lokal foydalanuvchi yo'li commit bo'lmasin)."""
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True).stdout.splitlines()
    ver = out[0].strip() if out else "?"
    try:
        shown = "~/" + exe.resolve().relative_to(Path.home()).as_posix()
    except ValueError:
        shown = exe.name
    return f"{ver} (`{shown}`)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    exe = a.blender
    quit_expr = ["--python-expr", "import bpy; bpy.ops.wm.quit_blender()"]
    vanilla = [wall([str(exe), "-b", "--factory-startup", *quit_expr]) for _ in range(REPEAT)]
    bonsai = [
        wall([str(exe), "-b", "--python-expr",
              "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.bonsai'); bpy.ops.wm.quit_blender()"])
        for _ in range(REPEAT)
    ]  # fmt: skip
    runs = [perf_json(exe, a.n) for _ in range(REPEAT)]
    keys = ["addon_register_ms", "rss_start_mb", "rss_addon_mb", "ifc_open_s", "rss_ifc_mb", "ifc_size_mb"]
    med = {k: median([r.get(k) for r in runs]) for k in keys}
    rows = [
        ("Sovuq start, vanilla (-b, factory)", f"{median(vanilla)} s"),
        ("Sovuq start, + Bonsai", f"{median(bonsai)} s"),
        ("Sath import + register", f"{med['addon_register_ms']} ms"),
        ("RSS: start / Sath bilan", f"{med['rss_start_mb']} / {med['rss_addon_mb']} MB"),
        (f"Sintetik IFC ({a.n} element, {med['ifc_size_mb']} MB) ochish", f"{med['ifc_open_s']} s"),
        ("RSS IFC ochilgandan keyin", f"{med['rss_ifc_mb']} MB"),
    ]
    md = [
        "# Desktop (Blender) unumdorligi — bazaviy o'lchov",
        "",
        f"Sana: {date.today().isoformat()} · Mashina: {platform.processor() or platform.machine()} · "
        f"OS: {platform.system()} {platform.release()} · Blender: {blender_label(exe)}",
        "",
        f"Usul: `python desktop/tests/perf_baseline.py --n {a.n}` — har o'lchov {REPEAT} marta, mediana. "
        "Spec §5 byudjetlari va C++ (`sath_core`) qarorlari shu raqamlarga tayanadi.",
        "",
        "| O'lchov | Qiymat |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in rows],
        "",
    ]
    out = ROOT / "docs" / "benchmark-desktop.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
