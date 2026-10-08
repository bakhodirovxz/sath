"""Sath desktop bundle (kompilyatsiyasiz): rasmiy Blender 5.2 + Sath app template/splash + Sath.exe (ikonka)
+ portable prefs (Bonsai va sath extension lari yoqilgan) + libredwg. FreeCAD yo'q (P2: GES geometriyasi sof Python).

python desktop/build/build_blender_bundle.py [--blender ~/Tools/blender-5.2] [--bonsai <zip>] [--no-zip]
        [--installer] [--keep-stage]
Natija: desktop/dist/Sath-Blender-<ver>-Windows-x86_64.zip (+ -installer.exe, .build.json — product: sath-blender).
Stage: desktop/build/_work/sath-bundle/Sath.
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

PRODUCT = "sath-blender"  # CODE-03: build metama'lumotidagi mahsulot


def artifact_name(ver: str) -> str:
    return f"Sath-Blender-{ver}-Windows-x86_64"  # server nom prefiksidan mahsulotni aniqlaydi


def build_info(ver: str) -> dict:
    return {"product": PRODUCT, "version": ver, "platform": "windows-x86_64", "name": artifact_name(ver)}


def write_build_info(ver: str) -> Path:
    """Sath-BUILD.json paket ichida va <nom>.build.json dist da (publish/yangilanish product ni o'qiydi)."""
    text = json.dumps(build_info(ver), ensure_ascii=False, indent=2) + "\n"
    (STAGE / "Sath-BUILD.json").write_text(text, encoding="utf-8")
    DIST.mkdir(exist_ok=True)
    side = DIST / f"{artifact_name(ver)}.build.json"
    side.write_text(text, encoding="utf-8")
    return side


def version() -> str:
    text = (ADDON / "blender_manifest.toml").read_text("utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else "0.0.0"


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def clean_env() -> dict:
    """Stage Blender i uchun: BLENDER_USER_* Blender da portable/ dan ustun — prefs/extension lar bundle dan
    tashqariga (hatto haqiqiy profilga) yozilmasin."""
    return {k: v for k, v in os.environ.items() if not k.startswith("BLENDER_USER_")}


def build_addon_zip(blender: Path) -> Path:
    run([sys.executable, BUILD / "sync_blender.py"])
    DIST.mkdir(exist_ok=True)
    run([blender, "--command", "extension", "build", "--source-dir", ADDON, "--output-dir", DIST])
    return DIST / f"sath-{version()}.zip"


# CI-03: Bonsai versiyasi va sha256 qotirilgan (eng oxirgisi emas). Yangilash: yangi zip ni sinab, ikkalasini
# birga o'zgartiring (sha256sum bonsai-<ver>-py313-win64.zip).
BONSAI_VERSION = "0.9.0"
BONSAI_SHA256 = "54c440ec7ee5b5bea3459a6ee117e2356378ea4fd01357b5530474236408bd2e"


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _check_bonsai(path: Path) -> Path:
    digest = _sha256(path)
    if digest != BONSAI_SHA256:
        path_note = f"{path} sha256={digest}"
        raise SystemExit(f"Bonsai zip sha256 qotirilgan qiymatga mos emas ({BONSAI_VERSION}): {path_note}")
    return path


def ensure_bonsai(explicit: Path | None, blender_version: str) -> Path:
    """Bonsai extension zip (BONSAI_VERSION, sha256 tekshiruvi bilan): berilgan yo'l, ~/Tools dagi nusxa yoki
    extensions.blender.org dan (faqat API dagi versiya qotirilganga teng bo'lsa) yuklab olish."""
    if explicit and explicit.exists():
        return _check_bonsai(explicit)
    cached = TOOLS / f"bonsai-{BONSAI_VERSION}-py313-win64.zip"
    if cached.exists():
        return _check_bonsai(cached)
    api = (
        "https://extensions.blender.org/api/v1/extensions/"
        f"?blender_version={blender_version}&platform=windows-x64"
    )
    with urllib.request.urlopen(api, timeout=60) as r:  # noqa: S310
        data = json.load(r)
    ext = next(e for e in data["data"] if e["id"] == "bonsai")
    if ext["version"] != BONSAI_VERSION:
        raise SystemExit(
            f"extensions.blender.org da Bonsai {ext['version']}, qotirilgani {BONSAI_VERSION} — --bonsai <zip> bering "
            "yoki BONSAI_VERSION/BONSAI_SHA256 ni yangilang"
        )
    dest = TOOLS / f"bonsai-{BONSAI_VERSION}-py313-win64.zip"
    part = dest.with_name(dest.name + ".part")
    print("  Bonsai yuklab olinmoqda:", ext["archive_url"], flush=True)
    urllib.request.urlretrieve(ext["archive_url"], part)  # noqa: S310
    try:
        _check_bonsai(part)
    except SystemExit:
        part.unlink(missing_ok=True)
        raise
    os.replace(part, dest)
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
    shutil.rmtree(dst, ignore_errors=True)  # shablondan olib tashlangan/qayta nomlangan fayllar qolmasin
    shutil.copytree(TEMPLATE / "Sath", dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def install_extensions(bonsai_zip: Path, sath_zip: Path) -> None:
    (STAGE / "portable").mkdir(exist_ok=True)  # Blender 4.2+: portable prefs/extensions shu papkada
    for z in (bonsai_zip, sath_zip):
        run([STAGE / "blender.exe", "-b", "--command", "extension", "install-file",
             "--repo", "user_default", "--enable", z], env=clean_env())  # fmt: skip


def setup_prefs(template_dir: Path) -> None:
    run([STAGE / "blender.exe", "-b", "--python-exit-code", "1", "--app-template", "Sath", "--python",
         TEMPLATE / "setup_bundle.py", "--", template_dir], env=clean_env())  # fmt: skip


def precompile() -> None:
    """Sath template, sath va Bonsai uchun .pyc oldindan (sovuq birinchi ishga tushish tezroq). Stage Blender ning
    o'z Python i (teg mos); checked-hash — fayl vaqtiga bog'liq emas (zip/installer vaqtni saqlamasa ham yaroqli)."""
    py = next((blender_ver_dir() / "python" / "bin").glob("python*.exe"), None)
    if py is None:
        raise SystemExit("stage da Blender Python i topilmadi")
    dirs = [blender_ver_dir() / "scripts" / "startup" / "bl_app_templates_system" / "Sath",
            STAGE / "portable" / "extensions", STAGE / "portable" / "scripts"]  # fmt: skip
    # -f: mavjud timestamp-based .pyc (install-file paytida yozilgan) ham checked-hash ga qayta yoziladi
    run([py, "-I", "-m", "compileall", "-q", "-f", "-j", "0", "--invalidation-mode", "checked-hash", *dirs])


def stage_mb() -> int:
    return sum(f.stat().st_size for f in STAGE.rglob("*") if f.is_file()) // 2**20


def check_stage() -> None:
    """P4: FreeCAD siz (K1), Sath template ish joylari va temasi bilan; hajm logda."""
    if (STAGE / "freecad").exists():
        raise SystemExit("stage da freecad/ bor — FreeCAD bundle dan chiqqan bo'lishi kerak (P2)")
    tpl = blender_ver_dir() / "scripts" / "startup" / "bl_app_templates_system" / "Sath"
    need = ("__init__.py", "workspaces.py", "theme_sath.xml", "startup.blend")
    missing = [n for n in need if not (tpl / n).exists()]
    if missing:
        raise SystemExit(f"Sath template da yo'q: {missing}")
    print(f"stage: {stage_mb()} MB (FreeCAD siz)", flush=True)


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


def write_readme(ver: str) -> None:
    (STAGE / "Sath-VERSION.txt").write_text(f"Sath {ver}\n", encoding="utf-8")
    (STAGE / "Sath-README.txt").write_text(
        f"""Sath {ver} — gidroelektrostansiya BIM (Blender 5.2 + Bonsai)

Ishga tushirish: Sath.exe (yoki blender.exe). Sozlamalar va extension lar `portable\\` papkasida —
kompyuterdagi boshqa Blender bilan aralashmaydi. 3D Viewport → N panel → «Sath» yorlig'i.
Ish joylari: BIM (asosiy), Compare, Simulation, SCADA; tiklash — Sath menyusi → «Ish joylarini tiklash».
Server: Sath → Server → manzil, login, parol → Ulanish.
DWG/DXF: tools\\libredwg (dwg2dxf).
""",
        encoding="utf-8",
    )


def make_zip(ver: str) -> Path:
    out = DIST / f"{artifact_name(ver)}.zip"
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
    out = DIST / f"{artifact_name(ver)}-installer.exe"
    run([makensis, f"/DVERSION={ver}", f"/DSTAGE={STAGE}", f"/DOUT={out}",
         f"/DICON={TEMPLATE / 'sath.ico'}", BUILD / "nsis" / "sath.nsi"])  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=Path(os.environ.get("GES_BLENDER_DIR", TOOLS / "blender-5.2")))
    ap.add_argument("--bonsai", type=Path, default=None)
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
    shutil.rmtree(STAGE / "freecad", ignore_errors=True)  # eski stage (--keep-stage) dagi FreeCAD
    copy_libredwg()
    write_readme(ver)
    precompile()
    write_build_info(ver)
    check_stage()
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
