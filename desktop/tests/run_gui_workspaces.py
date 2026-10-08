"""Oynali sinov (CI da emas): Sath app template ish joylari — blender_gui_workspaces.py ni GUI Blender da
ishga tushiradi. Repo rejimi: template vaqtinchalik BLENDER_USER_SCRIPTS/startup/bl_app_templates_user ga
nusxalanadi, `--app-template Sath`, addon repo dan. Bundle rejimi: --bundle <stage> (argumentsiz ishga
tushiriladi — sath_boot.py template ga o'tkazadi, extension lar bundle dan).

  python desktop/tests/run_gui_workspaces.py [--blender <exe>] [--bundle desktop/build/_work/sath-bundle/Sath]
  $env:SATH_SCREENSHOT="$PWD\\ws_bim.png"  # ixtiyoriy: BIM bosqichida oyna skrinshoti
Natija: [GUI-OK] — exit 0; [GUI-FAIL] — 1; [GUI-SKIP] (bundle bosqichi yo'q/to'liq emas) — 2."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "desktop" / "tests" / "blender_gui_workspaces.py"
TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"
BLENDER_SERIES = "5.2"  # haqiqiy profil papkasi (bundle rejimida bosqichdagi versiya papkasidan olinadi)
DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--bundle", type=Path, default=None, help="bundle stage (blender.exe + portable/)")
    ap.add_argument("--timeout", type=int, default=240)
    a = ap.parse_args()
    env = dict(os.environ)
    appdata = os.environ.get("APPDATA")
    if sys.platform == "win32" and not appdata:
        print("[GUI-FAIL] APPDATA yo'q — haqiqiy profilni himoya qilib bo'lmaydi")
        return 1
    root = a.bundle if a.bundle else a.blender.parent  # versiya papkasi (masalan 5.2) blender.exe yonida
    series = BLENDER_SERIES
    if root.is_dir():
        series = next((d.name for d in sorted(root.iterdir()) if d.is_dir() and re.fullmatch(r"\d+\.\d+", d.name)), series)
    if sys.platform == "win32":
        base = Path(appdata) / "Blender Foundation" / "Blender"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Blender"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blender"
    real = base / series / "config" / "userpref.blend"
    before = real.stat().st_mtime_ns if real.is_file() else None
    if a.bundle:  # bundle: faqat o'zining portable/ i; hech qanday BLENDER_USER_* o'rnatilmaydi
        for k in [k for k in env if k.startswith("BLENDER_USER_")]:
            env.pop(k)
        need = (a.bundle / "portable" / "config", a.bundle / "portable" / "extensions" / "user_default" / "sath")
        if not (a.bundle / "blender.exe").is_file() or not all(n.is_dir() for n in need):
            print(f"[GUI-SKIP] bundle bosqichi to'liq emas: {a.bundle} (build_blender_bundle.py --keep-stage)")
            return 2  # portable/ siz Blender %APPDATA% ga tushadi — ishga tushirilmaydi
    with tempfile.TemporaryDirectory(prefix="sath-gui-ws-") as tmp:
        if not a.bundle:
            for k, d in (("CONFIG", "config"), ("EXTENSIONS", "extensions"), ("DATAFILES", "datafiles")):
                (Path(tmp) / d).mkdir()  # vaqtinchalik profil — foydalanuvchining haqiqiy sozlamalariga tegilmaydi
                env[f"BLENDER_USER_{k}"] = str(Path(tmp) / d)
        if a.bundle:
            env["SATH_GUI_BUNDLE"] = "1"
            cmd = [str(a.bundle / "blender.exe"), "--python", str(CHECK)]
        else:
            scripts = Path(tmp) / "scripts"
            dst = scripts / "startup" / "bl_app_templates_user" / "Sath"
            shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns("__pycache__", "startup.blend"))
            env["BLENDER_USER_SCRIPTS"] = str(scripts)
            cmd = [str(a.blender), "--app-template", "Sath", "--python", str(CHECK)]
        try:
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=a.timeout)  # fmt: skip
        except subprocess.TimeoutExpired:  # run() bolani o'ldiradi
            print(f"[GUI-FAIL] {a.timeout}s ichida tugamadi")
            return 1
    out = r.stdout + r.stderr
    after = real.stat().st_mtime_ns if real.is_file() else None
    if after != before:
        print(f"[GUI-FAIL] haqiqiy userpref.blend o'zgargan: {real}")
        return 1
    keep = ("[GUI", "GUI-WS", "Traceback", "  File", "AssertionError", "Error:", "[sath]")
    for ln in out.splitlines():
        if ln.startswith(keep):
            print(ln)
    return 0 if "[GUI-OK]" in out else 1


if __name__ == "__main__":
    sys.exit(main())
