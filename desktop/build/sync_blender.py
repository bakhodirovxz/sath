"""GesWorkbench dagi FreeCAD siz modullarni Blender addoniga nusxalaydi (yagona manba — workbench).

python desktop/build/sync_blender.py          # nusxalash
python desktop/build/sync_blender.py --check  # CI: farq bo'lsa exit 1
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "desktop" / "GesWorkbench" / "ges_workbench"
DST = ROOT / "desktop" / "blender" / "sath" / "shared"
FILES = ["server_client.py", "dxf_prepare.py", "assimp_load.py"]
WB_FILES = ["ges_objects.py"]  # fc_engine uchun: sath/wb/
WB_DST = ROOT / "desktop" / "blender" / "sath" / "wb"
INIT = '"""GesWorkbench dan nusxa (desktop/build/sync_blender.py). Qo\'lda tahrirlamang."""\n'


def check() -> list[str]:
    """Farq qilgan yoki yo'q fayllar."""
    bad = [
        f for f in FILES if not (DST / f).exists() or not filecmp.cmp(SRC / f, DST / f, shallow=False)
    ]
    bad += [
        "wb/" + f
        for f in WB_FILES
        if not (WB_DST / f).exists() or not filecmp.cmp(SRC / f, WB_DST / f, shallow=False)
    ]
    return bad


def sync() -> None:
    for dst, files in ((DST, FILES), (WB_DST, WB_FILES)):
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "__init__.py").write_text(INIT, encoding="utf-8")
        for f in files:
            shutil.copyfile(SRC / f, dst / f)


if __name__ == "__main__":
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("sath nusxalari eskirgan:", ", ".join(bad), "-> python desktop/build/sync_blender.py")
            sys.exit(1)
        print("sath/shared va wb sinxron")
    else:
        sync()
        print("nusxalandi:", ", ".join(FILES + WB_FILES))
