"""Blender headless test runner: addonni repo dan yuklaydi, testni ishga tushiradi.

  blender -b --python desktop/tests/blender_headless.py -- --test smoke [--bonsai]
Testlar: desktop/tests/sath_tests/<nom>.py, `run(ctx)`; ctx = {"addon": modul}. Exit 0 = OK.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = ROOT / "desktop" / "blender" / "sath"


def unpack_wheels() -> None:
    """Extension wheel larini (ezdxf, assimp-py) Blender o'rnatgandek sys.path ga qo'shadi (test uchun)."""
    import zipfile

    target = ROOT / "desktop" / "build" / "_work" / "blender_wheels"
    for whl in sorted((ADDON_DIR / "wheels").glob("*.whl")):
        mark = target / (whl.name + ".ok")
        if not mark.exists():
            with zipfile.ZipFile(whl) as z:
                z.extractall(target)
            mark.parent.mkdir(parents=True, exist_ok=True)
            mark.touch()
    if target.is_dir() and str(target) not in sys.path:
        sys.path.insert(0, str(target))


def load_addon():
    """sath ni oddiy paket sifatida (extension bo'lmasdan) ro'yxatga oladi."""
    unpack_wheels()
    installed = "bl_ext.user_default.sath"
    if installed in bpy.context.preferences.addons:  # o'rnatilgan extension bilan to'qnashmasin
        bpy.ops.preferences.addon_disable(module=installed)
    sys.path.insert(0, str(ADDON_DIR.parent))
    mod = importlib.import_module("sath")
    mod.register()
    return mod


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    name = argv[argv.index("--test") + 1] if "--test" in argv else "smoke"
    if "--bonsai" in argv:
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
    os.environ.setdefault("GES_FC_HOME", os.path.join(os.path.expanduser("~"), "Tools", "fc-py313"))
    addon = load_addon()
    sys.path.insert(0, str(ROOT / "desktop" / "tests" / "sath_tests"))
    try:
        importlib.import_module(name).run({"addon": addon})
        print(f"[OK] {name}", flush=True)
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print(f"[FAIL] {name}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
