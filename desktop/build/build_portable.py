"""Sath desktop paketini yig'ish (Windows): portable zip + NSIS installer.

Fork (Sath-FreeCAD) overlay skripti bilan tayyor FreeCAD 1.1.3 binarini Sath ga aylantiradi
(brending, Mod/Ges, Sath.exe, keraksiz modullar olib tashlanadi), so'ng:
  * desktop/dist/Sath-<ver>-Windows-x86_64.zip            — portable (Sath.bat)
  * desktop/dist/Sath-<ver>-Windows-x86_64-installer.exe  — NSIS installer (makensis bo'lsa)

    python desktop/build/build_portable.py [--freecad-dir "C:\\Program Files\\FreeCAD 1.1"]
        [--fork-dir ../Sath-FreeCAD] [--no-installer] [--no-zip] [--fast]

--fast  — installer siqilmaydi (sinov uchun, ~600 MB, 1–2 daqiqa); siqilgan (lzma) ~10–20 daqiqa.
FreeCAD ni to'liq kompilyatsiya qilish shart emas — rasmiy 1.1.3 binari fork tegi bilan bir xil.
To'liq build: fork dagi GitHub Actions "Sath build" (natijasi ham shu nomlar bilan chiqadi).

Ishchi uchun: installer ni ishga tushiradi (yoki zip ni ochib Sath.bat). Dastur Sath
workbench bilan ochiladi -> "Serverga ulanish" -> server manzili + login.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Natija papkasi: GES_DIST_DIR (masalan E:\Sath\desktop-dist — C diskda joy kam bo'lsa)
DIST = Path(os.environ.get("GES_DIST_DIR") or ROOT / "desktop" / "dist")
WORK = Path(os.environ.get("GES_WORK_DIR") or ROOT / "desktop" / "build" / "_work")
DEFAULT_FORK = ROOT.parent / "Sath-FreeCAD"
DEFAULT_FREECAD = Path(r"C:\Program Files\FreeCAD 1.1")
# LibreDWG (dwg2dxf) — DWG ochish uchun paket ichiga qo'shiladi: tools/libredwg/ (GPL, ichki foydalanish)
LIBREDWG_CANDIDATES = [
    Path(os.environ.get("LIBREDWG_DIR", "")),
    Path.home() / "Tools" / "libredwg",
    Path(r"C:\Tools\libredwg"),
]
LIBREDWG_FILES = ("dwg2dxf.exe", "dxf2dwg.exe", "dwgread.exe", "README.txt", "COPYING")
NSIS_CANDIDATES = [
    Path(os.environ.get("NSIS_DIR", "")) / "makensis.exe",
    Path.home() / "Tools" / "NSIS" / "makensis.exe",
    Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
    Path(r"C:\Program Files\NSIS\makensis.exe"),
]


def bundle_libredwg(stage: Path) -> bool:
    """~/Tools/libredwg (yoki LIBREDWG_DIR) dan dwg2dxf + DLL larni stage/tools/libredwg ga nusxalaydi.
    Workbench Init.py ishga tushganda shu papkani topib DWG konverter sozlamasini o'zi to'ldiradi."""
    src = next((d for d in LIBREDWG_CANDIDATES if d and (d / "dwg2dxf.exe").is_file()), None)
    if src is None:
        print(
            "LibreDWG topilmadi (~/Tools/libredwg/dwg2dxf.exe yoki LIBREDWG_DIR) — DWG ochish uchun "
            "ishchi konverterni o'zi qo'yadi",
            file=sys.stderr,
        )
        return False
    dst = stage / "tools" / "libredwg"
    dst.mkdir(parents=True, exist_ok=True)
    files = [src / n for n in LIBREDWG_FILES if (src / n).is_file()] + list(src.glob("*.dll"))
    for p in files:
        shutil.copy2(p, dst / p.name)
    print(f"libredwg: {len(files)} fayl -> tools/libredwg")
    return True


def bundle_ezdxf(stage: Path) -> bool:
    """ezdxf (sof Python, MIT) -> Mod/Ges/vendor — DXF/DWG ni AutoCAD ko'rinishida ochish (bloklar, o'lchamlar,
    matn, shtrix). FreeCAD ning o'z python.exe si bilan o'rnatiladi (versiya mos bo'lsin)."""
    py = stage / "bin" / "python.exe"
    if not py.exists():
        print("python.exe topilmadi — ezdxf o'tkazib yuborildi", file=sys.stderr)
        return False
    dest = stage / "Mod" / "Ges" / "vendor"
    r = subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--upgrade",
            "--target",
            str(dest),
            "ezdxf>=1.3",
            "assimp-py>=1.0",  # FBX, LWO, X, … (Fayl -> Ochish)
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("ezdxf o'rnatilmadi (internet?):", r.stderr[-300:], file=sys.stderr)
        return False
    for junk in (dest / "bin",):
        shutil.rmtree(junk, ignore_errors=True)
    print("ezdxf -> Mod/Ges/vendor")
    return True


def find_makensis() -> Path | None:
    for p in NSIS_CANDIDATES:
        if p.is_file():
            return p
    found = shutil.which("makensis")
    return Path(found) if found else None


def build(
    freecad_dir: Path, fork_dir: Path, installer: bool, make_zip: bool, fast: bool
) -> list[Path]:
    overlay = fork_dir / "package" / "ges" / "overlay.py"
    if not overlay.exists():
        raise SystemExit(f"Fork topilmadi: {fork_dir} (package/ges/overlay.py yo'q)")
    # Workbench manbasi shu repo — fork nusxasini yangilab olamiz
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "desktop" / "build" / "sync_fork.py"),
            "--fork-dir",
            str(fork_dir),
        ],
        check=True,
    )
    stage = WORK / "Sath"
    WORK.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(overlay), "--src", str(freecad_dir), "--out", str(stage)], check=True
    )
    bundle_libredwg(stage)
    bundle_ezdxf(stage)
    version = (stage / "Sath-VERSION.txt").read_text(encoding="utf-8").strip()
    name = f"Sath-{version}-Windows-x86_64"
    DIST.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    if make_zip:
        out = DIST / f"{name}.zip"
        print("zip:", out)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in stage.rglob("*"):
                if p.is_file():
                    z.write(p, Path(name) / p.relative_to(stage))
        outputs.append(out)
    if installer:
        makensis = find_makensis()
        if not makensis:
            print(
                "makensis topilmadi — installer o'tkazib yuborildi (NSIS_DIR yoki ~/Tools/NSIS)",
                file=sys.stderr,
            )
        else:
            nsi_dir = fork_dir / "package" / "WindowsInstaller"
            exe_name = f"{name}-installer.exe"
            cmd = [str(makensis), "/V2"]
            if fast:
                cmd.append("/DFC_TEST_BUILD")
            cmd += [f"/DExeFile={exe_name}", f"/DFILES_FREECAD={stage}", "Sath-installer.nsi"]
            print("makensis:", exe_name, "(siqilgan)" if not fast else "(siqilmagan, sinov)")
            subprocess.run(cmd, cwd=nsi_dir, check=True)
            out = DIST / exe_name
            shutil.move(nsi_dir / exe_name, out)
            outputs.append(out)
    return outputs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--freecad-dir",
        type=Path,
        default=DEFAULT_FREECAD,
        help="O'rnatilgan FreeCAD 1.1.3 papkasi",
    )
    ap.add_argument(
        "--fork-dir", type=Path, default=Path(os.environ.get("GES_FORK_DIR", DEFAULT_FORK))
    )
    ap.add_argument("--no-installer", action="store_true")
    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--fast", action="store_true", help="Installer siqilmasin (sinov)")
    a = ap.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows paketi — Windows da yig'iladi (yoki fork CI)")
    for out in build(
        a.freecad_dir.resolve(), a.fork_dir.resolve(), not a.no_installer, not a.no_zip, a.fast
    ):
        print("tayyor:", out, f"{out.stat().st_size / 1048576:.0f} MB")
