"""Sath splash rasmlari (Blender app template): splash.png 501x282, splash_2x.png 1002x564.

python desktop/blender/template/make_splash.py [--version 0.3.0] [--out desktop/blender/template/Sath]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (24, 27, 33)
ACCENT = (38, 132, 174)  # suv ko'ki
FG = (236, 240, 244)
DIM = (150, 160, 172)


def _font(size: int):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(w: int, h: int, version: str) -> Image.Image:
    k = w / 501
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    # suv sathi to'lqinlari (pastki qism)
    for i, y in enumerate((0.62, 0.70, 0.78, 0.86)):
        c = tuple(int(BG[j] + (ACCENT[j] - BG[j]) * (0.35 - i * 0.07)) for j in range(3))
        d.rectangle([0, int(h * y), w, h], fill=c)
    # to'g'on silueti
    dam = [(int(w * 0.58), int(h * 0.62)), (int(w * 0.66), int(h * 0.30)), (int(w * 0.70), int(h * 0.30)),
           (int(w * 0.84), int(h * 0.62))]  # fmt: skip
    d.polygon(dam, fill=(58, 64, 74))
    d.text((int(28 * k), int(40 * k)), "Sath", font=_font(int(64 * k)), fill=FG)
    d.text((int(30 * k), int(118 * k)), "Gidroelektrostansiya BIM · raqamli egizak", font=_font(int(15 * k)), fill=DIM)
    d.text((int(30 * k), int(140 * k)), "Blender + FreeCAD dvigatel · IFC (Bonsai)", font=_font(int(13 * k)), fill=DIM)
    d.text((int(30 * k), int(h - 28 * k)), f"v{version}", font=_font(int(12 * k)), fill=DIM)
    return im


def icon(size: int) -> Image.Image:
    """Ko'k doira ustida oq «S» — Sath.exe ikonkasi."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], fill=ACCENT)
    f = _font(int(size * 0.68))
    tw = d.textlength("S", font=f)
    d.text(((size - tw) / 2, size * 0.08), "S", font=f, fill=FG)
    return im


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.0.0")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "Sath"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    draw(501, 282, a.version).save(out / "splash.png")
    draw(1002, 564, a.version).save(out / "splash_2x.png")
    ico = out.parent / "sath.ico"
    icon(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("splash:", out / "splash.png", out / "splash_2x.png", "| icon:", ico)
