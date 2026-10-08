"""Desktop unumdorligi (P0 bazaviy, P4 byudjetlar): sovuq start (vanilla / +Bonsai / +Sath + ish joylari),
register vaqti va og'ir importlar, RSS, ish joylari qurish, katta IFC ochish, bundle hajmi. Har o'lchov 3
marta, mediana. Natija docs/benchmark-desktop.md ga (P0 ustuni bilan); --check — spec §5 byudjeti buzilsa
exit 1. Chegaralar — desktop/blender/sath/core/budget.py.

  python desktop/tests/perf_baseline.py [--blender <exe>] [--n 2000] [--bundle <stage>] [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
from sath.core import budget  # noqa: E402

DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))
REPEAT = 3
BLENDER = ["-b", "--factory-startup"]  # barcha qatorlar bir xil boshlang'ich rejimda
SCRIPT = str(ROOT / "desktop" / "tests" / "perf_blender.py")
BONSAI = "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.bonsai')"
# P0 bazaviy o'lchov (2026-10-08, shu mashina; Sath P0 holatida) — taqqoslash uchun
P0 = {
    "cold_blender_s": 1.03, "cold_bonsai_s": 4.63, "cold_sath_s": 4.62, "register_ms": 31.4,
    "rss_blender_mb": 160.71, "rss_bonsai_mb": 350.68, "rss_sath_mb": 351.93, "ifc_open_s": 3.1,
    "rss_ifc_mb": 598.32,
}  # fmt: skip
BUNDLE_P0_MB = 2392  # Sath-0.3.0 bundle (ochilgan; FreeCAD 935 MB bilan) — P2 gacha


def wall(cmd: list[str]) -> float:
    t = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    return time.perf_counter() - t


def tagged(exe: Path, args: list[str], tag: str) -> dict:
    r = subprocess.run([str(exe), *BLENDER, "--python", SCRIPT, "--", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", check=True)  # fmt: skip
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith(tag + " "))
    return json.loads(line[len(tag) + 1 :])


def median(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def blender_label(exe: Path) -> str:
    """Blender versiyasi + exe yo'li (uy papkasi `~` bilan — lokal foydalanuvchi yo'li commit bo'lmasin)."""
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True).stdout.splitlines()
    ver = out[0].strip() if out else "?"
    try:
        shown = "~/" + exe.resolve().relative_to(Path.home()).as_posix()
    except ValueError:
        shown = exe.name
    return f"{ver} (`{shown}`)"


def ok(cond: bool) -> str:
    return "bajarildi" if cond else "**OSHDI**"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--bundle", type=Path, default=None, help="bundle stage papkasi (hajm, FreeCAD yo'qligi)")
    ap.add_argument("--check", action="store_true", help="byudjet buzilsa exit 1")
    a = ap.parse_args()
    exe = a.blender
    quit_ = "; bpy.ops.wm.quit_blender()"
    vanilla = [wall([str(exe), *BLENDER, "--python-expr", "import bpy" + quit_]) for _ in range(REPEAT)]
    bonsai = [wall([str(exe), *BLENDER, "--python-expr", BONSAI + quit_]) for _ in range(REPEAT)]
    sath = [wall([str(exe), *BLENDER, "--python", SCRIPT, "--", "--cold"]) for _ in range(REPEAT)]
    with tempfile.TemporaryDirectory(prefix="sath-perf-") as tmp:
        ifc = Path(tmp) / f"perf_{a.n}.ifc"
        subprocess.run([str(exe), *BLENDER, "--python", SCRIPT, "--", "--n", str(a.n), "--gen", str(ifc)],
                       check=True, capture_output=True)  # fmt: skip
        runs = [tagged(exe, ["--n", str(a.n), "--ifc", str(ifc)], "PERF") for _ in range(REPEAT)]
    heavy = tagged(exe, ["--budget"], "BUDGET")["heavy"]  # Bonsai siz (u numpy ni oldindan yuklaydi)
    ws_ms = median([tagged(exe, ["--ws"], "WS")["ensure_ms"] for _ in range(REPEAT)])
    keys = ["addon_register_ms", "rss_blender_mb", "rss_bonsai_mb", "rss_sath_mb", "ifc_open_s", "rss_ifc_mb",
            "ifc_size_mb"]  # fmt: skip
    med = {k: median([r.get(k) for r in runs]) for k in keys}
    mv, mb, ms = median(vanilla), median(bonsai), median(sath)
    ratio = round(ms / mb, 2)
    rss_delta = round(med["rss_sath_mb"] - med["rss_bonsai_mb"], 1)
    reg = med["addon_register_ms"]
    rows = [
        ("Sovuq start, Blender", f"{P0['cold_blender_s']} s", f"{mv} s"),
        ("Sovuq start, + Bonsai", f"{P0['cold_bonsai_s']} s", f"{mb} s"),
        ("Sovuq start, + Bonsai + Sath (+ ish joylari)", f"{P0['cold_sath_s']} s", f"{ms} s"),
        ("Sath import + register (Bonsai yoqilgan)", f"{P0['register_ms']} ms", f"{reg} ms"),
        ("Idle RSS: Blender / + Bonsai / + Sath",
         f"{P0['rss_blender_mb']} / {P0['rss_bonsai_mb']} / {P0['rss_sath_mb']} MB",
         f"{med['rss_blender_mb']} / {med['rss_bonsai_mb']} / {med['rss_sath_mb']} MB"),
        (f"Sintetik IFC ({a.n} element, {med['ifc_size_mb']} MB) ochish", f"{P0['ifc_open_s']} s",
         f"{med['ifc_open_s']} s"),
        ("RSS IFC ochilgandan keyin", f"{P0['rss_ifc_mb']} MB", f"{med['rss_ifc_mb']} MB"),
        ("Sath ish joylari qurish (ensure, 4 ta)", "—", f"{ws_ms} ms"),
    ]  # fmt: skip
    bad = budget.check(register_ms=reg, cold_ratio=ratio, rss_delta_mb=rss_delta, heavy=heavy)
    budgets = [
        ("Sath import + register", f"< {budget.REGISTER_MS:.0f} ms", f"{reg} ms", ok(reg < budget.REGISTER_MS)),
        ("Og'ir importlar register da (" + ", ".join(budget.HEAVY_MODULES) + ")", "yo'q",
         ", ".join(heavy) or "yo'q", ok(not heavy)),
        ("Sovuq start nisbati (+Sath / +Bonsai)", f"<= {budget.COLD_START_RATIO}x", f"{ratio}x",
         ok(ratio <= budget.COLD_START_RATIO)),
        ("Sath RSS ortishi (Bonsai ustiga)", f"<= {budget.IDLE_RSS_DELTA_MB:.0f} MB", f"{rss_delta} MB",
         ok(rss_delta <= budget.IDLE_RSS_DELTA_MB)),
    ]  # fmt: skip
    if a.bundle:
        size = sum(f.stat().st_size for f in a.bundle.rglob("*") if f.is_file()) // 2**20
        no_fc = not (a.bundle / "freecad").exists()
        rows.append(("Bundle hajmi (ochilgan stage)", f"{BUNDLE_P0_MB} MB (FreeCAD 935 MB bilan)",
                     f"{size} MB (−{BUNDLE_P0_MB - size} MB)"))  # fmt: skip
        budgets.append(("Bundle FreeCAD siz (~0.9 GB kichik)", "freecad/ yo'q", "yo'q" if no_fc else "bor",
                        ok(no_fc)))  # fmt: skip
        if not no_fc:
            bad.append("bundle da freecad/ bor")
    md = [
        "# Desktop (Blender) unumdorligi — o'lchov va byudjetlar",
        "",
        f"Sana: {date.today().isoformat()} · Mashina: {platform.processor() or platform.machine()} · "
        f"OS: {platform.system()} {platform.release()} · Blender: {blender_label(exe)}",
        "",
        f"Usul: `python desktop/tests/perf_baseline.py --n {a.n}" + (" --bundle <stage>" if a.bundle else "")
        + f" --check` — har o'lchov {REPEAT} marta, mediana. P0 ustuni — 2026-10-08 bazaviy o'lchov "
        "(Sath P0 holatida). Byudjetlar — spec §5 (`desktop/blender/sath/core/budget.py`).",
        "",
        "Rejim: barcha qatorlar `blender -b --factory-startup` (bir xil toza profil; Bonsai extension "
        "`bl_ext.user_default.bonsai` o'zi yoqiladi). Sath repo dan ro'yxatga olinadi; «+ Sath» sovuq starti "
        "app template ish joylarini ham quradi. Og'ir importlar Bonsai siz o'lchanadi (Bonsai numpy va "
        "ifcopenshell ni o'zi yuklaydi). O'lchovlar ketma-ket, issiq OS keshi bilan (sovuq-disk start emas). "
        "Har ishga tushishda Sath logi: `[sath] register … ms (byudjet < 150): import …, host … [modullar: …]`.",
        "",
        "Eslatma (issiq va sovuq register): byudjet `< 150 ms` **issiq** register ga tegishli (`__pycache__` bor, "
        "oddiy qayta ishga tushish). `__pycache__` tozalangan birinchi ishga tushishda (extension o'rnatilgandan "
        "keyin) register ~260–310 ms (2026-10-09 o'lchovi: 265 / 276 / 307 ms; import ~115–155, host ~140) — "
        "bu bir martalik .pyc kompilyatsiyasi, byudjet unga qo'llanmaydi; bundle da .pyc ni oldindan "
        "kompilyatsiya qilish alohida ish.",
        "",
        "| O'lchov | P0 | Hozir |",
        "|---|---|---|",
        *[f"| {k} | {p} | {v} |" for k, p, v in rows],
        "",
        "## Byudjetlar (spec §5)",
        "",
        "| Byudjet | Chegara | Hozir | Holat |",
        "|---|---|---|---|",
        *[f"| {k} | {c} | {v} | {s} |" for k, c, v, s in budgets],
        "",
        "Xulosa: " + ("barcha byudjetlar bajarildi." if not bad else "buzilgan — " + "; ".join(bad) + "."),
        "",
    ]
    out = ROOT / "docs" / "benchmark-desktop.md"
    out.write_text("\n".join(md), encoding="utf-8", newline="\n")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsoli (cp1251) «−» ni chop eta olmaydi
    print(out.read_text(encoding="utf-8"))
    return 1 if a.check and bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
