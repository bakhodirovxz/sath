"""Tashqi konverterlarni (DWG → DXF) avtomatik topib FreeCAD sozlamalariga yozish.

FreeCAD DWG ni o'zi o'qimaydi — LibreDWG `dwg2dxf` yoki ODA File Converter kerak va yo'li
Edit → Preferences → Import/Export → DWG da ko'rsatilgan bo'lishi shart. Ishchi buni qo'lda qilmasin:
dastur ochilganda quyidagi joylardan qidiriladi va topilsa sozlama o'zi to'ldiriladi:
  * dastur papkasi: <Sath>/tools/libredwg/dwg2dxf.exe (portable/installer bilan birga keladi)
  * %GES_TOOLS_DIR%, ~/Tools, C:\Tools (ichki papkalar ham), PATH
  * ODA File Converter: C:\Program Files\ODA\*\ODAFileConverter.exe
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import FreeCAD

DRAFT = "User parameter:BaseApp/Preferences/Mod/Draft"
EXE = ".exe" if os.name == "nt" else ""


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        home = Path(FreeCAD.getHomePath())
        dirs += [home / "tools" / "libredwg", home / "tools", home]
    except Exception:  # noqa: BLE001
        pass
    env = os.environ.get("GES_TOOLS_DIR")
    if env:
        dirs.append(Path(env))
    dirs += [
        Path.home() / "Tools",
        Path("C:/Tools"),
        Path("C:/Program Files/ODA"),
        Path("/opt/tools"),
        Path("/usr/bin"),
        Path("/usr/local/bin"),
    ]
    return [d for d in dirs if d.is_dir()]


def _find(name: str) -> str | None:
    """PATH, keyin nomzod papkalar (2 daraja chuqurlikkacha)."""
    found = shutil.which(name)
    if found:
        return found
    for d in _candidate_dirs():
        for p in (d / (name + EXE), *d.glob(f"*/{name}{EXE}"), *d.glob(f"*/*/{name}{EXE}")):
            if p.is_file():
                return str(p)
    return None


def find_dwg2dxf() -> str | None:
    return _find("dwg2dxf")


def find_oda() -> str | None:
    return _find("ODAFileConverter")


def ensure_dwg_converter(force: bool = False) -> str | None:
    """Sozlamada yaroqli konverter bo'lmasa (yoki force) topib yozadi. Qaytaradi: yo'l yoki None."""
    grp = FreeCAD.ParamGet(DRAFT)
    current = grp.GetString("TeighaFileConverter", "")
    if current and Path(current).is_file() and not force:
        return current
    path = find_dwg2dxf() or find_oda()
    if not path:
        return None
    grp.SetString("TeighaFileConverter", path)
    # 0 = avtomatik (LibreDWG → ODA → QCAD): topilganini ishlatadi
    grp.SetInt("DWGConversion", 0)
    FreeCAD.Console.PrintMessage(f"Sath: DWG konverter sozlandi — {path}\n")
    return path
