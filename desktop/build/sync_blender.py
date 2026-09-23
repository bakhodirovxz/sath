"""Umumiy (sof Python) modullarni yagona manbadan nusxalaydi (CODE-01).

Kanonik manba — common/sath_common/ (kelajakdagi `sath-common` wheel, docs/plan.md K1). Nusxalar:
  * Blender addoni: desktop/blender/sath/shared/
  * FreeCAD workbench (legacy): desktop/GesWorkbench/ges_workbench/
  * server: server/ges_server/models/ (Docker obrazida faqat server/ bor)
FreeCAD ga bog'liq ges_objects.py ning manbasi GesWorkbench, nusxasi — sath/wb/.

python desktop/build/sync_blender.py          # nusxalash
python desktop/build/sync_blender.py --check  # CI: farq bo'lsa exit 1
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "common" / "sath_common"
DST = ROOT / "desktop" / "blender" / "sath" / "shared"
FILES = ["server_client.py", "dxf_prepare.py", "assimp_load.py", "ifc_classes.py"]
WB_SRC = ROOT / "desktop" / "GesWorkbench" / "ges_workbench"
WB_FILES = ["ges_objects.py"]  # fc_engine uchun: sath/wb/ (manba — GesWorkbench, FreeCAD ga bog'liq)
WB_DST = ROOT / "desktop" / "blender" / "sath" / "wb"
SERVER_DST = ROOT / "server" / "ges_server" / "models"
# Addondan tashqari nusxalar: papka → fayllar (manba SRC)
EXTRA: dict[Path, list[str]] = {
    WB_SRC: FILES,
    SERVER_DST: ["dxf_prepare.py", "assimp_load.py"],
}
INIT = '"""common/sath_common dan nusxa (desktop/build/sync_blender.py). Qo\'lda tahrirlamang."""\n'
WB_INIT = '"""GesWorkbench dan nusxa (desktop/build/sync_blender.py). Qo\'lda tahrirlamang."""\n'


def copies() -> list[tuple[Path, Path]]:
    """(manba, nusxa) juftlari — hammasi bayt-bayt bir xil bo'lishi shart."""
    pairs = [(SRC / f, DST / f) for f in FILES]
    pairs += [(SRC / f, d / f) for d, files in EXTRA.items() for f in files]
    pairs += [(WB_SRC / f, WB_DST / f) for f in WB_FILES]
    return pairs


def check() -> list[str]:
    """Farq qilgan yoki yo'q nusxalar (ROOT ga nisbatan yo'l)."""
    return [
        dst.relative_to(ROOT).as_posix()
        for src, dst in copies()
        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False)
    ]


def sync() -> None:
    for d, init in ((DST, INIT), (WB_DST, WB_INIT)):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text(init, encoding="utf-8")
    for src, dst in copies():
        shutil.copyfile(src, dst)


if __name__ == "__main__":
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("nusxalar eskirgan:", ", ".join(bad), "-> python desktop/build/sync_blender.py")
            sys.exit(1)
        print("common/sath_common nusxalari sinxron")
    else:
        sync()
        print("nusxalandi:", ", ".join(dst.relative_to(ROOT).as_posix() for _, dst in copies()))
