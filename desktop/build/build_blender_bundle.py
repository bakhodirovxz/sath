"""Sath desktop bundle (kompilyatsiyasiz): rasmiy Blender 5.2 + Sath app template/splash + Sath.exe (ikonka)
+ portable prefs (Bonsai va sath extension lari yoqilgan) + FreeCAD dvigatel (conda py313, kesilgan) + libredwg.

python desktop/build/build_blender_bundle.py [--blender ~/Tools/blender-5.2] [--fc-home ~/Tools/fc-py313]
        [--bonsai <zip>] [--no-freecad] [--no-zip] [--installer] [--keep-stage]
Natija: desktop/dist/Sath-<ver>-Windows-x86_64.zip (+ -installer.exe). Stage: desktop/build/_work/sath-bundle/Sath
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "desktop" / "build"
DIST = ROOT / "desktop" / "dist"
ADDON = ROOT / "desktop" / "blender" / "sath"
TEMPLATE = ROOT / "desktop" / "blender" / "template"
TOOLS = Path.home() / "Tools"
WORK = BUILD / "_work" / "sath-bundle"
STAGE = WORK / "Sath"

# FreeCAD conda muhitidan bundle ga KIRMAYDIGAN narsalar (dvigatel: Part/Draft/Import/BIM/Mesh yetarli)
FC_PRUNE_DIRS = {
    "conda-meta", "pkgs", "Library/include", "Library/doc", "Library/translations", "Library/qml",
    "Library/share/doc", "Library/share/man", "Library/share/locale", "Library/share/cmake",
    "Library/share/opencascade/doc", "Library/share/opencascade/samples", "Library/lib/cmake",
    "Library/lib/pkgconfig", "Library/Mod/Robot", "Library/Mod/CAM", "Library/Mod/OpenSCAD",
    "Library/Mod/Idf", "Library/Mod/Inspection", "Library/Mod/ReverseEngineering", "Library/Mod/Start",
    "Library/Mod/Help", "Library/Mod/Test", "Library/Mod/Tux", "Library/Mod/Web", "Library/Mod/Points",
    "Library/Mod/Surface", "Library/Mod/Fem", "Library/Mod/Assembly", "Library/Mod/AddonManager",
    "Library/Mod/Plot", "Library/Mod/Show", "Tools", "Scripts",
}  # fmt: skip
FC_PRUNE_NAMES = {"__pycache__", "tests", "test"}
FC_PRUNE_SUFFIX = {".lib", ".pdb", ".a", ".h", ".hpp", ".hxx", ".lxx", ".gxx"}
# Library/bin dagi keraksiz DLL/EXE lar (prefikslar): MKL (conda numpy — Blender numpy ishlatiladi), libclang
# (shiboken generator), VTK/viskores/gmsh (FEM), PCL/flann (Points/ReverseEngineering), video kodeklar, Qt SW GL
FC_PRUNE_BIN_PREFIX = (
    "mkl_", "libclang", "vtk", "viskores", "gmsh", "pcl_", "flann", "avcodec", "avformat", "avutil",
    "avdevice", "avfilter", "swscale", "swresample", "aom", "libx264", "libx265", "dav1d", "opengl32sw",
    "rav1e", "svt", "vpx", "opus", "libvorbis", "libogg",
)  # fmt: skip
FC_KEEP_EXE = ("freecad",)


def version() -> str:
    text = (ADDON / "blender_manifest.toml").read_text("utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else "0.0.0"


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def build_addon_zip(blender: Path) -> Path:
    run([sys.executable, BUILD / "sync_blender.py"])
    DIST.mkdir(exist_ok=True)
    run([blender, "--command", "extension", "build", "--source-dir", ADDON, "--output-dir", DIST])
    return DIST / f"sath-{version()}.zip"


def ensure_bonsai(explicit: Path | None, blender_version: str) -> Path:
    """Bonsai extension zip: berilgan yo'l, ~/Tools dagi nusxa yoki extensions.blender.org dan yuklab olish."""
    if explicit and explicit.exists():
        return explicit
    cached = sorted(TOOLS.glob("bonsai-*py313*.zip")) + sorted(TOOLS.glob("add-on-bonsai-*.zip"))
    if cached:
        return cached[-1]
    api = (
        "https://extensions.blender.org/api/v1/extensions/"
        f"?blender_version={blender_version}&platform=windows-x64"
    )
    with urllib.request.urlopen(api, timeout=60) as r:  # noqa: S310
        data = json.load(r)
    ext = next(e for e in data["data"] if e["id"] == "bonsai")
    dest = TOOLS / f"bonsai-{ext['version']}-py313-win64.zip"
    print("  Bonsai yuklab olinmoqda:", ext["archive_url"], flush=True)
    urllib.request.urlretrieve(ext["archive_url"], dest)  # noqa: S310
    return dest


def blender_version(blender_dir: Path) -> str:
    out = subprocess.run(
        [str(blender_dir / "blender.exe"), "-b", "--version"], capture_output=True, text=True
    )
    m = re.search(r"Blender (\d+\.\d+\.\d+)", out.stdout)
    return m.group(1) if m else "5.2.0"


def copy_blender(blender_dir: Path) -> None:
    print("Blender nusxalanmoqda...", flush=True)
    shutil.copytree(blender_dir, STAGE, ignore=shutil.ignore_patterns("portable", "__pycache__"))


def make_exe(ico: Path) -> None:
    """Sath.exe = blender-launcher.exe (konsolsiz) nusxasi + Sath ikonkasi."""
    src = STAGE / "blender-launcher.exe"
    if not src.exists():
        src = STAGE / "blender.exe"
    exe = STAGE / "Sath.exe"
    shutil.copyfile(src, exe)
    run([sys.executable, BUILD / "set_exe_icon.py", exe, ico])


def blender_ver_dir() -> Path:
    """Stage dagi «5.2» kabi versiya papkasi (CI forki boshqa versiya bo'lishi mumkin)."""
    for p in STAGE.iterdir():
        if p.is_dir() and re.fullmatch(r"\d+\.\d+", p.name):
            return p
    raise RuntimeError("Blender versiya papkasi (masalan 5.2) topilmadi: " + str(STAGE))


def install_template(ver: str) -> Path:
    run([sys.executable, TEMPLATE / "make_splash.py", "--version", ver, "--out", TEMPLATE / "Sath"])
    dst = blender_ver_dir() / "scripts" / "startup" / "bl_app_templates_system" / "Sath"
    shutil.copytree(TEMPLATE / "Sath", dst, dirs_exist_ok=True)
    return dst


def install_extensions(bonsai_zip: Path, sath_zip: Path) -> None:
    (STAGE / "portable").mkdir(exist_ok=True)  # Blender 4.2+: portable prefs/extensions shu papkada
    for z in (bonsai_zip, sath_zip):
        run([STAGE / "blender.exe", "-b", "--command", "extension", "install-file",
             "--repo", "user_default", "--enable", z])  # fmt: skip


def setup_prefs(template_dir: Path) -> None:
    run([STAGE / "blender.exe", "-b", "--app-template", "Sath", "--python",
         TEMPLATE / "setup_bundle.py", "--", template_dir])  # fmt: skip


def _fc_ignore(root: Path):
    def ignore(d, names):
        rel = Path(d).relative_to(root).as_posix()
        out = set()
        in_bin = rel in ("Library/bin", "Library/lib")
        for n in names:
            p = f"{rel}/{n}" if rel != "." else n
            low = n.lower()
            if p in FC_PRUNE_DIRS or n in FC_PRUNE_NAMES or Path(n).suffix.lower() in FC_PRUNE_SUFFIX:
                out.add(n)
            elif in_bin and low.startswith(FC_PRUNE_BIN_PREFIX):
                out.add(n)
            elif in_bin and low.endswith(".exe") and not low.startswith(FC_KEEP_EXE):
                out.add(n)
        return out

    return ignore


def copy_freecad(fc_home: Path) -> None:
    print("FreeCAD dvigatel nusxalanmoqda (kesilgan)...", flush=True)
    shutil.copytree(fc_home, STAGE / "freecad", ignore=_fc_ignore(fc_home))


def copy_libredwg() -> bool:
    cands = (TOOLS / "libredwg", Path("C:/Tools/libredwg"))
    src = next((p for p in cands if (p / "dwg2dxf.exe").exists()), None)
    if src is None:
        print("  libredwg topilmadi — DWG konverter bundle ga kirmadi", flush=True)
        return False
    dst = STAGE / "tools" / "libredwg"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and f.suffix.lower() in (".exe", ".dll", ".txt"):
            shutil.copyfile(f, dst / f.name)
    return True


def write_readme(ver: str, with_fc: bool) -> None:
    (STAGE / "Sath-VERSION.txt").write_text(f"Sath {ver}\n", encoding="utf-8")
    fc = "FreeCAD dvigatel" if with_fc else "FreeCAD siz"
    (STAGE / "Sath-README.txt").write_text(
        f"""Sath {ver} — gidroelektrostansiya BIM (Blender 5.2 + Bonsai + {fc})

Ishga tushirish: Sath.exe (yoki blender.exe). Sozlamalar va extension lar `portable\` papkasida —
kompyuterdagi boshqa Blender bilan aralashmaydi. 3D Viewport → N panel → «Sath» yorlig'i.
Server: Sath → Server → manzil, login, parol → Ulanish.
DWG/DXF: tools\libredwg (dwg2dxf). FreeCAD: freecad\ (GES obyektlari, DXF import).
""",
        encoding="utf-8",
    )


def make_zip(ver: str) -> Path:
    out = DIST / f"Sath-{ver}-Windows-x86_64.zip"
    print("zip:", out, flush=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in STAGE.rglob("*"):
            if f.is_file():
                z.write(f, f"Sath/{f.relative_to(STAGE).as_posix()}")
    return out


def find_makensis() -> Path | None:
    for p in (TOOLS / "NSIS" / "makensis.exe", Path(r"C:\Program Files (x86)\NSIS\makensis.exe")):
        if p.exists():
            return p
    found = shutil.which("makensis")
    return Path(found) if found else None


def make_installer(ver: str) -> Path | None:
    makensis = find_makensis()
    if not makensis:
        print("  makensis topilmadi — installer yig'ilmadi", flush=True)
        return None
    out = DIST / f"Sath-{ver}-Windows-x86_64-installer.exe"
    run([makensis, f"/DVERSION={ver}", f"/DSTAGE={STAGE}", f"/DOUT={out}",
         f"/DICON={TEMPLATE / 'sath.ico'}", BUILD / "nsis" / "sath.nsi"])  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=Path(os.environ.get("GES_BLENDER_DIR", TOOLS / "blender-5.2")))
    ap.add_argument("--fc-home", type=Path, default=Path(os.environ.get("GES_FC_HOME", TOOLS / "fc-py313")))
    ap.add_argument("--bonsai", type=Path, default=None)
    ap.add_argument("--no-freecad", action="store_true")
    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--installer", action="store_true")
    ap.add_argument("--keep-stage", action="store_true", help="mavjud stage ni qayta ishlatish (tez sinov)")
    a = ap.parse_args()
    ver = version()
    if not (a.blender / "blender.exe").exists():
        print("Blender topilmadi:", a.blender)
        return 1
    if not a.keep_stage and STAGE.exists():
        shutil.rmtree(STAGE)
    if not STAGE.exists():
        copy_blender(a.blender)
    sath_zip = build_addon_zip(a.blender / "blender.exe")
    bonsai_zip = ensure_bonsai(a.bonsai, blender_version(a.blender))
    template_dir = install_template(ver)
    make_exe(TEMPLATE / "sath.ico")
    if (STAGE / "portable").exists():
        shutil.rmtree(STAGE / "portable")
    install_extensions(bonsai_zip, sath_zip)
    boot_dir = STAGE / "portable" / "scripts" / "startup"
    boot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE / "sath_boot.py", boot_dir / "sath_boot.py")  # argumentsiz ham Sath template
    setup_prefs(template_dir)
    if not a.no_freecad:
        if (STAGE / "freecad").exists():
            shutil.rmtree(STAGE / "freecad")
        copy_freecad(a.fc_home)
    copy_libredwg()
    write_readme(ver, not a.no_freecad)
    if not a.no_zip:
        z = make_zip(ver)
        print(f"tayyor: {z} ({z.stat().st_size // 2**20} MB)")
    if a.installer:
        inst = make_installer(ver)
        if inst:
            print(f"tayyor: {inst} ({inst.stat().st_size // 2**20} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
