"""Yig'ilgan Sath bundle (stage) tekshiruvi — fon rejimida, bundle ning o'z Blender i va portable prefs i
bilan: Sath template ish joylari (Blender ish joylari va Scripting yo'q), Sath temasi, Bonsai va sath
extension lari, «Standard» view transform, FreeCAD yo'q, hajm. Oynali qism («BIM ish joyida ochiladi») —
`python desktop/tests/run_gui_workspaces.py --bundle <stage>` (faol ish joyi BIM ekani ham shu yerda: fon
rejimida Window.workspace almashishi qo'llanmaydi).

  python desktop/tests/bundle_check.py [--stage desktop/build/_work/sath-bundle/Sath]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
from sath.core import registry, tokens  # noqa: E402

STAGE = ROOT / "desktop" / "build" / "_work" / "sath-bundle" / "Sath"
GONE = {"Sculpting", "UV Editing", "Texture Paint", "Shading", "Rendering", "Compositing", "Geometry Nodes",
        "Scripting"}  # fmt: skip
PROBE = """
import bpy, json
p = bpy.context.preferences
t = p.themes[0]
bonsai = p.addons.get("bl_ext.user_default.bonsai")
win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
print("BUNDLE " + json.dumps({
    "addons": sorted(k for k in p.addons.keys() if k.rpartition(".")[2] in ("sath", "bonsai")),
    "tags": sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws")),
    "names": sorted(w.name for w in bpy.data.workspaces),
    "active": win.workspace.get("sath_ws") if win is not None and win.workspace is not None else None,
    "object_active": [round(c * 255) for c in t.view_3d.object_active],
    "theme_filepath": t.filepath,
    "dev_ui": p.view.show_developer_ui,
    "bonsai_ws": bonsai.preferences.should_setup_workspace if bonsai is not None else None,
    "view_transform": bpy.context.scene.view_settings.view_transform,
}), flush=True)
"""
# sath_boot.py ning yo'li: ishga tushgan Blender da read_homefile(app_template="Sath") (addon/tema prefs saqlanadi)
BOOT = "import bpy; bpy.ops.wm.read_homefile(app_template='Sath')" + chr(10)
NEED = ("__init__.py", "workspaces.py", "theme_sath.xml", "startup.blend")


def env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("BLENDER_USER_")}  # portable/ dan ustun


def pyc_flags(path: Path) -> int:
    return int.from_bytes(path.read_bytes()[4:8], "little")  # PEP 552: 3 = checked-hash, 0 = timestamp


def pyc_problems(stage: Path, tpl_dir: Path | None) -> list[str]:
    """Sath template, sath extension va sath_boot .pyc lari checked-hash bo'lishi shart (zip/installer vaqtni
    saqlamasa ham birinchi ishga tushishda qayta kompilyatsiya bo'lmasin)."""
    out = []
    groups = {
        "sath extension": list((stage / "portable" / "extensions" / "user_default" / "sath").rglob("*.pyc")),
        "template": list((tpl_dir / "__pycache__").glob("*.pyc")) if tpl_dir is not None else [],
        "sath_boot": list((stage / "portable" / "scripts").rglob("*.pyc")),
    }
    for label, files in groups.items():
        if not files:
            out.append(f".pyc yo'q: {label}")
            continue
        bad = [f.name for f in files if pyc_flags(f) != 3]
        if bad:
            out.append(f"{label}: checked-hash emas ({len(bad)}/{len(files)}): {bad[:3]}")
    return out


def stage_mb(stage: Path) -> int:
    return sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) // 2**20


def run_probe(stage: Path, *args: str) -> tuple[dict | None, str]:
    cmd = [str(stage / "blender.exe"), "-b", "--python-exit-code", "1", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, env=env())
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("BUNDLE ")), None)
    if line is None:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None, r.stdout
    return json.loads(line[len("BUNDLE ") :]), r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, default=STAGE)
    a = ap.parse_args()
    problems = []
    tpl_dir = next(a.stage.glob("*.*/scripts/startup/bl_app_templates_system/Sath"), None)
    if tpl_dir is None:
        problems.append("Sath template papkasi yo'q")
    else:
        problems += [f"template da yo'q: {n}" for n in NEED if not (tpl_dir / n).exists()]
    if not (a.stage / "portable" / "config" / "userpref.blend").is_file():
        problems.append("portable/config/userpref.blend yo'q")
    nsi = (ROOT / "desktop" / "build" / "nsis" / "sath.nsi").read_text(encoding="utf-8")
    if "--app-template" in nsi:  # --app-template addon/tema prefs ni tashlaydi; sath_boot.py o'zi o'tkazadi
        problems.append("sath.nsi da --app-template bor")
    problems += pyc_problems(a.stage, tpl_dir)
    if problems:
        print(chr(10).join("  - " + p for p in problems))
        print("[BUNDLE-FAIL]")
        return 1
    # Yuboriladigan yo'l: argumentsiz ishga tushish + sath_boot.py (read_homefile app_template=Sath).
    got, out = run_probe(a.stage, "--python-expr", BOOT + PROBE)
    # startup.blend ning o'zi (ilgaksiz): Sath ish joylari faylda bormi.
    disk, _ = run_probe(a.stage, "--factory-startup", str(tpl_dir / "startup.blend"), "--python-expr", PROBE)
    if got is None or disk is None:
        print("[BUNDLE-FAIL] tekshiruv skripti natija bermadi")
        return 1
    want_active = [round(c * 255) for c in tokens.parse(tokens.PAL["highlight"])[:3]]
    want_tags = sorted(registry.WORKSPACES)
    if not any(ln.startswith("[sath] register") and " ms" in ln for ln in out.splitlines()):
        problems.append("'[sath] register ... ms' perf logi stdout da yo'q")
    if got["addons"] != ["bl_ext.user_default.bonsai", "bl_ext.user_default.sath"]:
        problems.append(f"addonlar: {got['addons']}")
    if got["bonsai_ws"] is not False:
        problems.append(f"Bonsai should_setup_workspace: {got['bonsai_ws']}")
    if got["tags"] != want_tags:
        problems.append(f"Sath ish joylari: {got['tags']}")
    if disk["tags"] != want_tags:
        problems.append(f"startup.blend faylida Sath ish joylari: {disk['tags']}")
    for label, d in (("boot", got), ("startup.blend", disk)):
        names = d["names"]
        if len(set(names)) != len(names) or any(re.search(r"\.\d{3}$", n) for n in names):
            problems.append(f"{label}: ish joyi nomlari takrorlangan: {names}")
    if set(got["names"]) & GONE:
        problems.append(f"olib tashlanmagan: {sorted(set(got['names']) & GONE)}")
    if got["object_active"] != want_active:
        problems.append(f"tema object_active {got['object_active']} != {want_active}")
    if got["theme_filepath"]:
        problems.append(f"tema yo'li userpref da qoldi: {got['theme_filepath']}")
    if got["dev_ui"]:
        problems.append("developer UI yoqiq")
    if got["view_transform"] != "Standard":
        problems.append(f"view transform: {got['view_transform']}")
    if (a.stage / "freecad").exists():
        problems.append("freecad/ bor")
    print(f"stage: {stage_mb(a.stage)} MB; ish joylari: {got['names']}; startup.blend: {disk['tags']}")
    for p in problems:
        print("  -", p)
    print("[BUNDLE-OK]" if not problems else "[BUNDLE-FAIL]")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
