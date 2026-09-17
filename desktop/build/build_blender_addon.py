"""Sath Blender extension zip: desktop/dist/sath-<ver>.zip (wheels bilan).

python desktop/build/build_blender_addon.py   # GES_BLENDER env bilan blender.exe yo'lini berish mumkin
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "desktop" / "blender" / "sath"
DIST = ROOT / "desktop" / "dist"
BLENDER = os.environ.get(
    "GES_BLENDER", os.path.join(os.path.expanduser("~"), "Tools", "blender-5.2", "blender.exe")
)

if __name__ == "__main__":
    subprocess.run([sys.executable, str(ROOT / "desktop" / "build" / "sync_blender.py")], check=True)
    DIST.mkdir(exist_ok=True)
    subprocess.run(
        [BLENDER, "--command", "extension", "build", "--source-dir", str(SRC), "--output-dir", str(DIST)],
        check=True,
    )
    print("tayyor:", [p.name for p in DIST.glob("sath-*.zip")])
