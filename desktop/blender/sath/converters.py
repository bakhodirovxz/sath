"""DWG → DXF konverter (LibreDWG dwg2dxf yoki ODA File Converter) ni topish — FreeCAD siz."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""


def _candidate_dirs() -> list[Path]:
    dirs = []
    for env in ("GES_TOOLS_DIR", "GES_FC_HOME"):
        v = os.environ.get(env)
        if v:
            dirs += [Path(v), Path(v) / "tools", Path(v) / "tools" / "libredwg"]
    from .fc_engine import bundle_dir

    b = bundle_dir()
    if b is not None:
        dirs += [b / "tools", b / "tools" / "libredwg"]  # Sath bundle
    dirs += [
        Path(__file__).resolve().parent / "tools",
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


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _check(dxf: Path, started: float, r: subprocess.CompletedProcess, tool: str) -> Path:
    """Natija yangi (shu chaqiruvda yozilgan), bo'sh emas va konverter xatosiz tugagan bo'lishi shart."""
    tail = ((r.stderr or "") + (r.stdout or ""))[-300:]
    if r.returncode != 0:
        raise RuntimeError(f"{tool} xatosi (kod {r.returncode}): {tail}")
    if not dxf.is_file() or dxf.stat().st_size == 0:
        raise RuntimeError(f"{tool} DXF yaratmadi: {tail}")
    if dxf.stat().st_mtime < started - 2:  # fayl tizimi vaqt aniqligi uchun 2 s zaxira
        raise RuntimeError(f"{tool}: natija eski fayl ({dxf.name}) — konvertatsiya bajarilmadi")
    return dxf


def dwg_to_dxf(dwg: Path, out_dir: Path) -> Path:
    """DWG → DXF (dwg2dxf, bo'lmasa ODA). RuntimeError: konverter yo'q / xato.

    CAD-06: har chaqiruv out_dir ichida yangi papka (mkdtemp) oladi — oldingi importdan qolgan DXF natija
    sifatida qabul qilinmaydi; ODA ga foydalanuvchi papkasi emas, faqat shu DWG nusxasi turgan yangi kirish
    papkasi beriladi; qaytish kodi va natija vaqti tekshiriladi. Natija papkasini chaqiruvchi tozalaydi."""
    dwg = Path(dwg)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="dwg-", dir=out_dir))
    started = time.time()
    exe = find_dwg2dxf()
    if exe:
        dxf = work / (dwg.stem + ".dxf")
        r = _run([exe, "-y", "-o", str(dxf), str(dwg)], 300)
        return _check(dxf, started, r, "dwg2dxf")
    oda = find_oda()
    if oda:
        # ODA File Converter: <kirish papkasi> <chiqish papkasi> <versiya> <tur> <rekursiv> <audit> [filtr]
        in_dir, res_dir = work / "in", work / "out"
        in_dir.mkdir()
        res_dir.mkdir()
        shutil.copy2(dwg, in_dir / dwg.name)
        try:
            r = _run([oda, str(in_dir), str(res_dir), "ACAD2018", "DXF", "0", "1", dwg.name], 600)
        finally:
            shutil.rmtree(in_dir, ignore_errors=True)
        return _check(res_dir / (dwg.stem + ".dxf"), started, r, "ODA File Converter")
    shutil.rmtree(work, ignore_errors=True)
    raise RuntimeError("DWG konverter topilmadi: LibreDWG dwg2dxf ni ~/Tools/libredwg ga qo'ying")
