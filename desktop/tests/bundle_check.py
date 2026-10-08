"""Yig'ilgan Sath bundle (stage) tekshiruvi — fon rejimida, bundle ning o'z Blender i va portable prefs i
bilan: Sath template ish joylari (Blender ish joylari va Scripting yo'q), Sath temasi, Bonsai va sath
extension lari, «Standard» view transform, FreeCAD yo'q, hajm. Oynali qism («BIM ish joyida ochiladi») —
`python desktop/tests/run_gui_workspaces.py --bundle <stage>`.

  python desktop/tests/bundle_check.py [--stage desktop/build/_work/sath-bundle/Sath]
"""

from __future__ import annotations

import argparse
import json
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
print("BUNDLE " + json.dumps({
    "addons": sorted(k for k in p.addons.keys() if k.rpartition(".")[2] in ("sath", "bonsai")),
    "tags": sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws")),
    "names": sorted(w.name for w in bpy.data.workspaces),
    "object_active": [round(c * 255) for c in t.view_3d.object_active],
    "theme_filepath": t.filepath,
    "dev_ui": p.view.show_developer_ui,
    "view_transform": bpy.context.scene.view_settings.view_transform,
}), flush=True)
"""


def stage_mb(stage: Path) -> int:
    return sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) // 2**20


def run_probe(stage: Path, *extra: str) -> tuple[dict | None, str]:
    cmd = [str(stage / "blender.exe"), "-b", *extra, "--python-expr", PROBE]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("BUNDLE ")), None)
    if line is None:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None, r.stdout
    return json.loads(line[len("BUNDLE ") :]), r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, default=STAGE)
    a = ap.parse_args()
    # Blender --app-template bilan portable userpref dagi addonlarni yuklamaydi (argumentsiz GUI da sath_boot.py
    # template ga o'tkazadi) — shuning uchun prefs (addon/tema/perf) argumentsiz, startup.blend esa
    # --app-template Sath bilan tekshiriladi.
    prefs, out = run_probe(a.stage)
    tpl, _ = run_probe(a.stage, "--app-template", "Sath")
    if prefs is None or tpl is None:
        print("[BUNDLE-FAIL] tekshiruv skripti natija bermadi")
        return 1
    want_active = [round(c * 255) for c in tokens.parse(tokens.PAL["highlight"])[:3]]
    problems = []
    if not any(ln.startswith("[sath] register") and " ms" in ln for ln in out.splitlines()):
        problems.append("'[sath] register ... ms' perf logi stdout da yo'q")
    if prefs["addons"] != ["bl_ext.user_default.bonsai", "bl_ext.user_default.sath"]:
        problems.append(f"addonlar: {prefs['addons']}")
    if tpl["tags"] != sorted(registry.WORKSPACES):
        problems.append(f"Sath ish joylari: {tpl['tags']}")
    if len(set(tpl["names"])) != len(tpl["names"]) or any(n.startswith("BIM.") for n in tpl["names"]):
        problems.append(f"ish joyi nomlari takrorlangan: {tpl['names']}")
    if set(tpl["names"]) & GONE:
        problems.append(f"olib tashlanmagan: {sorted(set(tpl['names']) & GONE)}")
    if prefs["object_active"] != want_active:
        problems.append(f"tema object_active {prefs['object_active']} != {want_active}")
    if prefs["theme_filepath"]:
        problems.append(f"tema yo'li userpref da qoldi: {prefs['theme_filepath']}")
    if prefs["dev_ui"]:
        problems.append("developer UI yoqiq")
    if tpl["view_transform"] != "Standard":
        problems.append(f"view transform: {tpl['view_transform']}")
    if (a.stage / "freecad").exists():
        problems.append("freecad/ bor")
    print(f"stage: {stage_mb(a.stage)} MB; ish joylari: {tpl['names']}")
    for p in problems:
        print("  -", p)
    print("[BUNDLE-OK]" if not problems else "[BUNDLE-FAIL]")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
