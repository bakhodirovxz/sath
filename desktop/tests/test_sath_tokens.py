"""Web dizayn tokenlari → desktop (P4, spec §5): core/tokens.py va theme_sath.xml generatsiyasi sinxron,
ranglar web bilan bir xil (sRGB → chiziqli)."""

import sys
import xml.dom.minidom
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "build"))
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

import gen_tokens  # noqa: E402
from sath.core import tokens  # noqa: E402


def test_generated_files_in_sync():
    assert gen_tokens.check() == [], "python desktop/build/gen_tokens.py ni ishga tushiring"


def test_themes_and_palette_parsed():
    assert list(tokens.THEMES) == ["engineer", "operator", "operator-hc"]
    keys = set(tokens.THEMES["engineer"])
    assert len(keys) >= 70
    assert keys == set(tokens.THEMES["operator"]) == set(tokens.THEMES["operator-hc"])
    need = {"diff-add", "diff-change", "alarm-critical", "alarm-medium", "alarm-stale", "text-muted", "canvas"}
    assert need <= keys
    assert tokens.THEMES["engineer"]["overlay"].startswith("rgba(")
    # palette.ts: «BIM versiya farqi (tokens --diff-* bilan bir xil)» — web 3D diff = tokenlar
    assert tokens.PAL["diffAdd"] == tokens.THEMES["engineer"]["diff-add"]
    assert tokens.PAL["diffChange"] == tokens.THEMES["engineer"]["diff-change"]
    assert "primitive" not in tokens.PAL and "heatRamp" not in tokens.PAL  # ichki obyekt/massiv emas


def test_parse_and_linear_conversion():
    assert tokens.parse("#ff8000") == (1.0, 128 / 255, 0.0, 1.0)
    assert tokens.parse("#fff") == (1.0, 1.0, 1.0, 1.0)
    assert tokens.parse("#00000080")[3] == pytest.approx(128 / 255)
    assert tokens.parse("rgba(48, 48, 48, 0.75)") == (48 / 255, 48 / 255, 48 / 255, 0.75)
    r, g, b, a = tokens.rgba("diff-add")  # #2ecc71
    assert r == pytest.approx(((0x2E / 255 + 0.055) / 1.055) ** 2.4) and a == 1.0
    assert tokens.pal_rgba("diffAdd") == tokens.rgba("diff-add")
    assert tokens.rgba("canvas", "operator") != tokens.rgba("canvas")
    with pytest.raises(ValueError):
        tokens.parse("red")
    with pytest.raises(KeyError):
        tokens.rgba("yoq-token")


def test_parser_fails_loudly_on_format_change():
    with pytest.raises(SystemExit):
        gen_tokens.parse_themes("export const OTHER = {\n};\n")
    with pytest.raises(SystemExit):
        gen_tokens.parse_palette("export const PAL = {\n} as const;\n")


def test_theme_xml_is_blender_dark_overrides_from_palette():
    text = gen_tokens.THEME_XML.read_text("utf-8")
    xml.dom.minidom.parseString(text)  # to'g'ri XML
    assert f'object_active="{tokens.PAL["highlight"]}"' in text
    assert f'high_gradient="{tokens.PAL["sceneBg"]}"' in text
    assert f'axis_x="{tokens.PAL["axisX"]}"' in text
    assert "<ThemeStyle>" in text  # Blender execute_preset ThemeStyle elementisiz yiqiladi
