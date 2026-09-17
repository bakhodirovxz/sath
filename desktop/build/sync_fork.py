"""GES workbench ni FreeCAD fork iga (src/Mod/Ges) sinxronlash.

Manba — shu repo: desktop/GesWorkbench (testlar shu yerda). Fork (Sath-FreeCAD) o'z CMake
build ida Mod/Ges ni shu nusxadan oladi; CMakeLists.txt va branding/ papkasi fork niki, ularga
tegilmaydi.

    python desktop/build/sync_fork.py [--fork-dir ../Sath-FreeCAD] [--check]

--check — nusxalamaydi, farq bo'lsa 1 bilan chiqadi (CI uchun).
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "desktop" / "GesWorkbench"
DEFAULT_FORK = next(  # FreeCAD forki: yangi yoki eski nomli papka
    (p for p in (ROOT.parent / "Sath-FreeCAD", ROOT.parent / "GES-BIM-FreeCAD") if p.is_dir()),
    ROOT.parent / "Sath-FreeCAD",
)
# Fork da o'ziga tegishli, sinxronlanmaydigan narsalar
FORK_OWN = {"CMakeLists.txt", "branding"}
SKIP = {"__pycache__", ".pytest_cache"}


def files(base: Path) -> dict[str, Path]:
    out = {}
    for p in base.rglob("*"):
        rel = p.relative_to(base)
        if any(part in SKIP for part in rel.parts) or rel.parts[0] in FORK_OWN:
            continue
        if p.is_file():
            out[rel.as_posix()] = p
    return out


def sync(fork_dir: Path, check: bool) -> int:
    dest = fork_dir / "src" / "Mod" / "Ges"
    if not (fork_dir / "src" / "Mod").is_dir():
        raise SystemExit(f"Fork topilmadi: {fork_dir} (src/Mod yo'q)")
    src_files = files(SRC)
    dst_files = files(dest) if dest.exists() else {}
    changed = [
        r
        for r, p in src_files.items()
        if r not in dst_files or not filecmp.cmp(p, dst_files[r], shallow=False)
    ]
    removed = [r for r in dst_files if r not in src_files]
    if check:
        for r in changed:
            print("farq:", r)
        for r in removed:
            print("ortiqcha:", r)
        print(
            "OK: fork sinxron"
            if not (changed or removed)
            else f"{len(changed) + len(removed)} ta farq"
        )
        return 1 if (changed or removed) else 0
    for r in changed:
        target = dest / r
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_files[r], target)
        print("yangilandi:", r)
    for r in removed:
        os.remove(dest / r)
        print("o'chirildi:", r)
    print(f"tayyor: {len(changed)} yangilandi, {len(removed)} o'chirildi -> {dest}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fork-dir", type=Path, default=Path(os.environ.get("GES_FORK_DIR", DEFAULT_FORK))
    )
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    sys.exit(sync(a.fork_dir.resolve(), a.check))
