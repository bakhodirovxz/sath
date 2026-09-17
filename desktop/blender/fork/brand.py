"""Blender manbasiga Sath brendini qo'llash (CI da build dan oldin): oyna sarlavhasi, Windows resurs
(ProductName/FileDescription/CompanyName), exe ikonkasi, splash.

python desktop/blender/fork/brand.py <blender-manba-papkasi> [--check]
Har almashtirish topilmasa xato — upstream o'zgarganini darhol ko'rsatadi.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "template"

# (fayl, eski, yangi) — Blender v5.2.x
REPLACEMENTS = [
    (
        "source/blender/windowmanager/intern/wm_window.cc",
        '    return "Blender";\n',
        '    return "Sath";\n',
    ),
    (
        "source/blender/windowmanager/intern/wm_window.cc",
        '  win_title.append(fmt::format(" - Blender {}", BKE_blender_version_string()));\n',
        '  win_title.append(fmt::format(" - Sath (Blender {})", BKE_blender_version_string()));\n',
    ),
    (
        "release/windows/icons/winblender.rc",
        '      VALUE "CompanyName", "Blender Foundation"\n',
        '      VALUE "CompanyName", "Sath jamoasi"\n',
    ),
    (
        "release/windows/icons/winblender.rc",
        '      VALUE "FileDescription", "Blender"\n',
        '      VALUE "FileDescription", "Sath"\n',
    ),
    (
        "release/windows/icons/winblender.rc",
        '      VALUE "ProductName", "Blender"\n',
        '      VALUE "ProductName", "Sath"\n',
    ),
]
# (manba fayl bizda, nishon fayl Blender da)
COPIES = [
    (HERE.parent / "template" / "sath.ico", "release/windows/icons/winblender.ico"),
    (TEMPLATE / "Sath" / "splash_2x.png", "release/datafiles/splash.png"),
]


def apply(root: Path, check: bool = False) -> int:
    missing = 0
    for rel, old, new in REPLACEMENTS:
        p = root / rel
        if not p.exists():
            print("YO'Q:", rel)
            missing += 1
            continue
        s = p.read_text(encoding="utf-8")
        if old not in s:
            if new in s:
                print("allaqachon:", rel, "|", new.strip()[:60])
                continue
            print("TOPILMADI:", rel, "|", old.strip()[:60])
            missing += 1
            continue
        if not check:
            p.write_text(s.replace(old, new, 1), encoding="utf-8")
        print("ok:", rel, "|", new.strip()[:60])
    for src, rel in COPIES:
        dst = root / rel
        if not src.exists():
            print("MANBA YO'Q:", src)
            missing += 1
            continue
        if not dst.exists():
            print("YO'Q:", rel)
            missing += 1
            continue
        if not check:
            shutil.copyfile(src, dst)
        print("nusxa:", src.name, "->", rel)
    return missing


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--check", action="store_true", help="faqat tekshirish, yozmaslik")
    a = ap.parse_args()
    n = apply(a.root, a.check)
    if n:
        print(f"{n} ta almashtirish bajarilmadi — upstream o'zgargan bo'lishi mumkin")
        sys.exit(1)
    print("brend qo'llandi")
