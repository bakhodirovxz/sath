"""DWG → DXF konverter (LibreDWG dwg2dxf yoki ODA File Converter) ni topish — FreeCAD siz."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""


def _candidate_dirs() -> list[Path]:
    dirs = []
    for env in ("GES_TOOLS_DIR", "GES_FC_HOME"):
        v = os.environ.get(env)
        if v:
            dirs += [Path(v), Path(v) / "tools", Path(v) / "tools" / "libredwg"]
    dirs += [
        Path(__file__).resolve().parent / "tools",  # bundle ichida
        Path.home() / "Tools",
        Path("C:/Tools"),
        Path("C:/Program Files/ODA"),
        Path("/opt/tools"),
        Path("/usr/local/bin"),
    ]
    return [d for d in dirs if d.is_dir()]


def _find(name: str) -> str | None:
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


def dwg_to_dxf(dwg: Path, out_dir: Path) -> Path:
    """DWG → DXF (dwg2dxf, bo'lmasa ODA). RuntimeError: konverter yo'q / xato."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dxf = out_dir / (dwg.stem + ".dxf")
    exe = find_dwg2dxf()
    if exe:
        r = subprocess.run(
            [exe, "-y", "-o", str(dxf), str(dwg)], capture_output=True, text=True, timeout=300
        )
        if not dxf.exists():
            raise RuntimeError(f"dwg2dxf xatosi: {r.stderr[-300:]}")
        return dxf
    oda = find_oda()
    if oda:
        subprocess.run(
            [oda, str(dwg.parent), str(out_dir), "ACAD2018", "DXF", "0", "1", dwg.name],
            capture_output=True,
            timeout=600,
        )
        if dxf.exists():
            return dxf
        raise RuntimeError("ODA File Converter DXF yaratmadi")
    raise RuntimeError("DWG konverter topilmadi: LibreDWG dwg2dxf ni ~/Tools/libredwg ga qo'ying")
