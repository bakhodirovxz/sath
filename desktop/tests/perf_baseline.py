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
FREECAD_MB = 935  # P0 bundle dagi freecad/ (P2 da to'liq olib tashlangan)


def bundle_breakdown(stage: Path) -> dict[str, int]:
    """Stage hajmi (bayt) toifalar bo'yicha: Blender (qolgani), Bonsai (extension + .local bog'liqliklari: numpy,
    ifcopenshell ...), Sath (extension + template + boot), libredwg asboblari, .pyc (portable/ va template dagi
    barcha .pyc — oldindan kompilyatsiya)."""
    ver = next((d for d in stage.iterdir() if d.is_dir() and d.name.replace(".", "").isdigit()), None)
    tpl = ver / "scripts" / "startup" / "bl_app_templates_system" / "Sath" if ver else stage / "_yoq"
    groups = {
        "Bonsai": [stage / "portable" / "extensions" / "user_default" / "bonsai", stage / "portable" / "extensions" / ".local"],
        "Sath": [stage / "portable" / "extensions" / "user_default" / "sath", tpl, stage / "portable" / "scripts"],
        "libredwg": [stage / "tools"],
    }
    out = {"Blender": 0, "Bonsai": 0, "Sath": 0, "libredwg": 0, ".pyc": 0}
    total = 0
    for f in stage.rglob("*"):
        if not f.is_file():
            continue
        n = f.stat().st_size
        total += n
        compiled = f.suffix == ".pyc" and (stage / "portable" in f.parents or tpl in f.parents)
        if compiled:
            out[".pyc"] += n
            continue
        for g, roots in groups.items():
            if any(r in f.parents for r in roots):
                out[g] += n
                break
    out["Blender"] = total - sum(v for k, v in out.items() if k != "Blender")
    return out


def real_config_files(series: str = "5.2") -> list[Path]:
    """Haqiqiy Blender profilining config papkasidagi fayllar (mtime qo'riqchisi uchun)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "Blender"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Blender"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blender"
    cfg = base / series / "config"
    return sorted(cfg.glob("*")) if cfg.is_dir() else []


def mtimes(files: list[Path]) -> dict[str, int]:
    return {str(f): f.stat().st_mtime_ns for f in files if f.is_file()}


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
    before = mtimes(real_config_files())
    with tempfile.TemporaryDirectory(prefix="sath-perf-profile-") as iso:
        # Profil izolyatsiyasi: bim.load_project haqiqiy recent-ifc-projects.txt ga yozmasin. EXTENSIONS tegilmaydi
        # (Bonsai odatiy repodan topilaveradi). Bola jarayonlar muhitni meros qiladi.
        for k, d in (("CONFIG", "config"), ("DATAFILES", "datafiles")):
            (Path(iso) / d).mkdir()
            os.environ[f"BLENDER_USER_{k}"] = str(Path(iso) / d)
        rc = _main()
        for k in ("BLENDER_USER_CONFIG", "BLENDER_USER_DATAFILES"):
            os.environ.pop(k, None)
    after = mtimes(real_config_files())
    if before != after:
        print("[PERF-FAIL] haqiqiy Blender profili o'zgargan:", {k for k in after if before.get(k) != after[k]})
        return 1
    return rc


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--bundle", type=Path, default=None, help="bundle stage papkasi (hajm, FreeCAD yo'qligi)")
    ap.add_argument("--check", action="store_true", help="byudjet buzilsa exit 1")
    a = ap.parse_args()
    if a.bundle is not None and not (a.bundle / "blender.exe").is_file():
        print(f"[PERF-FAIL] --bundle {a.bundle}: blender.exe yo'q (stage yo'li noto'g'ri)")
        return 2
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
    size_md: list[str] = []
    if a.bundle:
        size = sum(f.stat().st_size for f in a.bundle.rglob("*") if f.is_file()) // 2**20
        no_fc = not (a.bundle / "freecad").exists()
        bd = {k: round(v / 2**20) for k, v in bundle_breakdown(a.bundle).items()}
        rows.append(("Bundle hajmi (ochilgan stage)", f"{BUNDLE_P0_MB} MB (FreeCAD {FREECAD_MB} MB bilan)",
                     f"{size} MB (sof o'zgarish P0 ga nisbatan −{BUNDLE_P0_MB - size} MB)"))  # fmt: skip
        budgets.append(("Bundle FreeCAD siz (−935 MB)", "freecad/ yo'q", "yo'q" if no_fc else "bor", ok(no_fc)))
        budgets.append(("Bundle hajmi", f"<= {budget.BUNDLE_MAX_MB} MB", f"{size} MB",
                        ok(size <= budget.BUNDLE_MAX_MB)))  # fmt: skip
        bad += budget.check_bundle(size, not no_fc)
        size_md = [
            "## Bundle hajmi (ochilgan stage)",
            "",
            f"FreeCAD olib tashlanishi **{FREECAD_MB} MB** tejadi; P0 ({BUNDLE_P0_MB} MB) ga nisbatan sof o'zgarish "
            f"**−{BUNDLE_P0_MB - size} MB** ({size} MB). Qolgan o'sish (taxminiy: P0 uchun toifalar bo'yicha "
            "o'lchov yo'q) Bonsai 0.9.0 va oldindan kompilyatsiya qilingan `.pyc` fayllar bilan bog'liq (ular «FreeCAD "
            "tejami» taqqosiga kirmaydi). Quyidagi toifalar — joriy stage ning o'lchovi.",
            "",
            "| Toifa | MB |",
            "|---|---|",
            *[f"| {k} | {v} |" for k, v in bd.items()],
            f"| **Jami** | **{size}** |",
            "",
        ]
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
        "bu bir martalik .pyc kompilyatsiyasi, byudjet unga qo'llanmaydi. Bundle da .pyc oldindan "
        "kompilyatsiya qilingan (checked-hash, `compileall -f`): zip/installer fayl vaqtini o'zgartirsa ham "
        "birinchi ishga tushishda qayta kompilyatsiya yo'q (`bundle_check` tekshiradi); bundle (GUI, yangi stage) "
        "birinchi ishga tushishda register ~69 ms, keyingisida ~43 ms (2026-10-09, `run_gui_workspaces.py --bundle`).",
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
        *size_md,
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
