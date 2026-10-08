"""Dizayn tokenlari: web → desktop (spec §5). Yagona manba — web/src/ui/tokens.ts (THEMES) va
web/src/viewer/palette.ts (PAL). Bu skript ulardan yasaydi:
  * desktop/blender/sath/core/tokens.py — 3D diff/alarm/sog'liq ranglari web bilan bir xil (bpy siz)
  * desktop/blender/template/Sath/theme_sath.xml — Blender Dark ustiga Sath farqlari (bundle sozlashda qo'llanadi, P4 Task 7)
Node kerak emas (CI desktop ishida ham ishlaydi).

python desktop/build/gen_tokens.py          # yozish
python desktop/build/gen_tokens.py --check  # CI: farq bo'lsa exit 1
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS_TS = ROOT / "web" / "src" / "ui" / "tokens.ts"
PALETTE_TS = ROOT / "web" / "src" / "viewer" / "palette.ts"
TOKENS_PY = ROOT / "desktop" / "blender" / "sath" / "core" / "tokens.py"
THEME_XML = ROOT / "desktop" / "blender" / "template" / "Sath" / "theme_sath.xml"

_THEME_OPEN = re.compile(r'^  "?([\w-]+)"?: \{\s*$')
_THEME_ENTRY = re.compile(r'^    "?([\w-]+)"?: "([^"]+)",?\s*(?://.*)?$')
_PAL_ENTRY = re.compile(r'^  (\w+): "([^"]+)",?\s*(?://.*)?$')
_COMMENT = re.compile(r"^\s*(//|/\*|\*)")
_PAL_ARRAY = re.compile(r"^  \w+: \[.*\],?\s*$")  # categorical/heatRamp — massiv, PAL ga kirmaydi
_PAL_NESTED_OPEN = re.compile(r"^  \w+: \{\s*$")  # draft — ichki obyekt
THEME_KEYS = ("axisX", "axisY", "axisZ", "highlight", "sceneBg")  # theme_sath.xml dagi PAL ranglari

PY_HEADER = '''"""Dizayn tokenlari — web/src/ui/tokens.ts (THEMES) va web/src/viewer/palette.ts (PAL, faqat
satr qiymatlar) dan avtomatik: `python desktop/build/gen_tokens.py` (CI: `--check`).
QO'LDA TAHRIRLAMANG. bpy siz (pytest).

Blender 3D ranglari (Object.color, View3DShading.background_color) chiziqli: rgba()/pal_rgba() sRGB
hex ni chiziqliga o'giradi — web (three.js: sRGB → linear) bilan bir xil ko'rinadi; Sath template
sahnasi «Standard» view transform da (AgX ranglarni o'zgartirmasin)."""

from __future__ import annotations

'''

PY_FUNCS = '''

def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def parse(value: str) -> tuple[float, float, float, float]:
    """'#rgb' | '#rrggbb' | '#rrggbbaa' | 'rgba(r, g, b, a)' → sRGB 0..1 va alfa."""
    v = value.strip()
    if v.startswith("#") and len(v) in (4, 7, 9):
        h = "".join(ch * 2 for ch in v[1:]) if len(v) == 4 else v[1:]
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, a)
    if v.startswith("rgba(") and v.endswith(")"):
        r, g, b, a = (float(x) for x in v[5:-1].split(","))
        return (r / 255.0, g / 255.0, b / 255.0, a)
    raise ValueError(f"rang tushunilmadi: {value!r}")


def rgba(token: str, theme: str = "engineer") -> tuple[float, float, float, float]:
    """Web tokeni → chiziqli RGBA (Object.color). Sukut «engineer» — web BIM sahifalari temasi."""
    r, g, b, a = parse(THEMES[theme][token])
    return (_linear(r), _linear(g), _linear(b), a)


def pal_rgba(name: str) -> tuple[float, float, float, float]:
    """web/src/viewer/palette.ts PAL rangi → chiziqli RGBA."""
    r, g, b, a = parse(PAL[name])
    return (_linear(r), _linear(g), _linear(b), a)
'''

THEME_TEMPLATE = """<!-- Sath temasi: Blender Dark + Sath farqlari. Avtomatik (desktop/build/gen_tokens.py, manba
     web/src/viewer/palette.ts), qo'lda tahrirlamang. Bundle sozlash bosqichi qo'llaydi
     (script.execute_preset) — ulanishi keyingi vazifada (P4 Task 7). -->
<bpy>
  <Theme>
    <user_interface>
      <ThemeUserInterface
        axis_x="{axisX}"
        axis_y="{axisY}"
        axis_z="{axisZ}"
        >
      </ThemeUserInterface>
    </user_interface>
    <view_3d>
      <ThemeView3D
        object_active="{highlight}"
        >
        <space>
          <ThemeSpaceGradient>
            <gradients>
              <ThemeGradientColors
                high_gradient="{sceneBg}"
                >
              </ThemeGradientColors>
            </gradients>
          </ThemeSpaceGradient>
        </space>
      </ThemeView3D>
    </view_3d>
  </Theme>
  <ThemeStyle>
  </ThemeStyle>
</bpy>
"""


def _block(text: str, start: str) -> list[tuple[int, str]]:
    """`start` bilan boshlanadigan qatordan keyingi, birinchi `}` (ustun 0) gacha bo'lgan (qator raqami, qator)."""
    lines = text.splitlines()
    i = next((n for n, ln in enumerate(lines) if ln.startswith(start)), None)
    if i is None:
        raise SystemExit(f"gen_tokens: {start!r} topilmadi (web fayli formati o'zgardimi?)")
    for j in range(i + 1, len(lines)):
        if lines[j].startswith("}"):
            return [(n + 1, lines[n]) for n in range(i + 1, j)]
    raise SystemExit(f"gen_tokens: {start!r} bloki yopilmagan")


def _unparsed(src: str, no: int, ln: str) -> SystemExit:
    return SystemExit(f"gen_tokens: {src}:{no}: qator tushunilmadi (format o'zgardimi?): {ln.strip()!r}")


def parse_themes(text: str, src: str = "web/src/ui/tokens.ts") -> dict[str, dict[str, str]]:
    themes: dict[str, dict[str, str]] = {}
    cur: dict[str, str] | None = None
    for no, ln in _block(text, "export const THEMES"):
        if not ln.strip() or _COMMENT.match(ln):
            continue
        m = _THEME_OPEN.match(ln)
        if m:
            cur = themes.setdefault(m.group(1), {})
            continue
        if ln.startswith("  }"):
            cur = None
            continue
        m = _THEME_ENTRY.match(ln)
        if not m or cur is None:
            raise _unparsed(src, no, ln)
        cur[m.group(1)] = m.group(2)
    if not themes or not all(themes.values()):
        raise SystemExit("gen_tokens: tokens.ts THEMES o'qilmadi")
    ref = set(next(iter(themes.values())))
    for name, vals in themes.items():
        if set(vals) != ref:
            diff = sorted(set(vals) ^ ref)
            raise SystemExit(f"gen_tokens: {src}: {name!r} temasi kalitlari boshqalardan farq qiladi: {diff}")
    return themes


def parse_palette(text: str, src: str = "web/src/viewer/palette.ts") -> dict[str, str]:
    pal: dict[str, str] = {}
    nested = False
    for no, ln in _block(text, "export const PAL"):
        if nested:
            nested = not re.match(r"^  \},?\s*$", ln)
            continue
        if not ln.strip() or _COMMENT.match(ln) or _PAL_ARRAY.match(ln):
            continue
        if _PAL_NESTED_OPEN.match(ln):
            nested = True
            continue
        m = _PAL_ENTRY.match(ln)
        if not m:
            raise _unparsed(src, no, ln)
        pal[m.group(1)] = m.group(2)
    if not pal:
        raise SystemExit("gen_tokens: palette.ts PAL o'qilmadi")
    return pal


def render_py(themes: dict[str, dict[str, str]], pal: dict[str, str]) -> str:
    out = [PY_HEADER + "THEMES: dict[str, dict[str, str]] = {"]
    for name, vals in themes.items():
        out.append(f"    {json.dumps(name)}: {{")
        out += [f"        {json.dumps(k)}: {json.dumps(v)}," for k, v in vals.items()]
        out.append("    },")
    out.append("}")
    out.append("PAL: dict[str, str] = {")
    out += [f"    {json.dumps(k)}: {json.dumps(v)}," for k, v in pal.items()]
    out.append("}")
    return "\n".join(out) + "\n" + PY_FUNCS


def render_theme(pal: dict[str, str]) -> str:
    bad = [k for k in THEME_KEYS if not re.fullmatch(r"#[0-9a-fA-F]{6}", pal.get(k, ""))]
    if bad:
        raise SystemExit(f"gen_tokens: palette.ts da #rrggbb yo'q: {bad}")
    return THEME_TEMPLATE.format(**{k: pal[k] for k in THEME_KEYS})


def outputs() -> dict[Path, str]:
    themes = parse_themes(TOKENS_TS.read_text("utf-8"))
    pal = parse_palette(PALETTE_TS.read_text("utf-8"))
    return {TOKENS_PY: render_py(themes, pal), THEME_XML: render_theme(pal)}


def check() -> list[str]:
    """Eskirgan yoki yo'q fayllar (ROOT ga nisbatan). Matn solishtiriladi (bayt emas): read_text qator oxirini normallashtiradi, CRLF checkout xato bermaydi."""
    return [
        p.relative_to(ROOT).as_posix()
        for p, text in outputs().items()
        if not p.exists() or p.read_text("utf-8") != text
    ]


def main() -> int:
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("tokenlar eskirgan:", ", ".join(bad), "-> python desktop/build/gen_tokens.py")
            return 1
        print("web tokenlari va desktop nusxalari sinxron")
        return 0
    for p, text in outputs().items():
        p.write_text(text, encoding="utf-8", newline="\n")
        print("yozildi:", p.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
