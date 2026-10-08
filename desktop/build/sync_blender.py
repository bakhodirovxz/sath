"""Umumiy (sof Python) modullarni yagona manbadan nusxalaydi (CODE-01).

Kanonik manba — common/sath_common/ (kelajakdagi `sath-common` wheel, docs/plan.md K1). Nusxalar:
  * Blender addoni: desktop/blender/sath/shared/
  * server: server/ges_server/models/ (Docker obrazida faqat server/ bor)
sim/ges_sim dagi sof (faqat math) formulalar ham addonga nusxalanadi — server bilan bir xil (SIM-01).

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
CORE_FILES = ["server_client.py", "dxf_prepare.py", "assimp_load.py", "ifc_classes.py", "cad_common.py"]
FILES = CORE_FILES + ["geom.py", "ges_kinds.py"]  # geom (P2) — sof numpy geometriya; faqat addon nusxasi
# sim/ges_sim dagi sof (faqat math) modullar — server bilan bir xil formula (SIM-01)
SIM_SRC = ROOT / "sim" / "ges_sim"
SIM_FILES = ["cavitation.py"]
SERVER_DST = ROOT / "server" / "ges_server" / "models"
# Addondan tashqari nusxalar: papka → fayllar (manba SRC)
EXTRA: dict[Path, list[str]] = {
    SERVER_DST: ["dxf_prepare.py", "assimp_load.py", "cad_common.py"],
}
INIT = '"""common/sath_common dan nusxa (desktop/build/sync_blender.py). Qo\'lda tahrirlamang."""\n'


def copies() -> list[tuple[Path, Path]]:
    """(manba, nusxa) juftlari — hammasi bayt-bayt bir xil bo'lishi shart."""
    pairs = [(SRC / f, DST / f) for f in FILES]
    pairs += [(SIM_SRC / f, DST / f) for f in SIM_FILES]
    pairs += [(SRC / f, d / f) for d, files in EXTRA.items() for f in files]
    return pairs


def check() -> list[str]:
    """Farq qilgan yoki yo'q nusxalar (ROOT ga nisbatan yo'l)."""
    return [
        dst.relative_to(ROOT).as_posix()
        for src, dst in copies()
        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False)
    ]


def sync() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    (DST / "__init__.py").write_text(INIT, encoding="utf-8")
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
