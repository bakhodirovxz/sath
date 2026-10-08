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
import tempfile
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


BLENDER = ["-b", "--factory-startup"]  # barcha qatorlar bir xil boshlang'ich rejimda
SCRIPT = str(ROOT / "desktop" / "tests" / "perf_blender.py")
BONSAI = "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.bonsai')"


def perf_json(exe: Path, n: int, ifc: Path) -> dict:
    r = subprocess.run(
        [str(exe), *BLENDER, "--python", SCRIPT, "--", "--n", str(n), "--ifc", str(ifc)],
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
    a_n = a.n
    quit_ = "; bpy.ops.wm.quit_blender()"
    vanilla = [wall([str(exe), *BLENDER, "--python-expr", "import bpy" + quit_]) for _ in range(REPEAT)]
    bonsai = [wall([str(exe), *BLENDER, "--python-expr", BONSAI + quit_]) for _ in range(REPEAT)]
    sath = [
        wall([str(exe), *BLENDER, "--python", SCRIPT, "--", "--cold"])
        for _ in range(REPEAT)
    ]  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="sath-perf-") as tmp:
        ifc = Path(tmp) / f"perf_{a_n}.ifc"
        subprocess.run([str(exe), *BLENDER, "--python", SCRIPT, "--", "--n", str(a_n), "--gen", str(ifc)], check=True, capture_output=True)
        runs = [perf_json(exe, a_n, ifc) for _ in range(REPEAT)]
    keys = ["addon_register_ms", "rss_blender_mb", "rss_bonsai_mb", "rss_sath_mb", "ifc_open_s", "rss_ifc_mb", "ifc_size_mb"]
    med = {k: median([r.get(k) for r in runs]) for k in keys}
    mv, mb, ms = median(vanilla), median(bonsai), median(sath)
    ratio = round(ms / mb, 2)
    rss_delta = round(med["rss_sath_mb"] - med["rss_bonsai_mb"], 1)
    rows = [
        ("Sovuq start, Blender", f"{mv} s"),
        ("Sovuq start, + Bonsai", f"{mb} s"),
        ("Sovuq start, + Bonsai + Sath", f"{ms} s"),
        ("Sovuq start nisbati (+Sath / +Bonsai), byudjet <= 1.2", f"{ratio}x"),
        ("Sath import + register (Bonsai yoqilgan), byudjet < 150 ms", f"{med['addon_register_ms']} ms"),
        ("Idle RSS: Blender / + Bonsai / + Sath", f"{med['rss_blender_mb']} / {med['rss_bonsai_mb']} / {med['rss_sath_mb']} MB"),
        ("Sath RSS ortishi (Bonsai ustiga), byudjet <= 50 MB", f"{rss_delta} MB"),
        (f"Sintetik IFC ({a.n} element, {med['ifc_size_mb']} MB) ochish", f"{med['ifc_open_s']} s"),
        ("RSS IFC ochilgandan keyin (alohida jarayonda yaratilgan IFC)", f"{med['rss_ifc_mb']} MB"),
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
        "Rejim: barcha qatorlar `blender -b --factory-startup` (bir xil toza profil; Bonsai extension "
        "`bl_ext.user_default.bonsai` o'zi yoqiladi va tekshiriladi). Sath repo dan ro'yxatga olinadi. "
        "Eslatma: o'lchovlar ketma-ket, issiq OS keshi bilan (sovuq-disk start emas).",
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
