"""sath addoni import mantig'i (bpy siz): birlik/o'q (CAD-04), DXF o'qish, DWG konverter, GUID, manifest."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import cad_read  # noqa: E402

SAMPLES = ROOT / "server" / "tests" / "samples"


def _dxf(path: Path, insunits: int | None) -> Path:
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new("R2018")
    if insunits is not None:
        doc.header["$INSUNITS"] = insunits
    doc.modelspace().add_line((0, 0), (1, 0))
    doc.saveas(path)
    return path


# --- CAD-04 ------------------------------------------------------------------------------------------------------


def test_resolve_fbx_from_metadata_and_override():
    r = cad_read.resolve(SAMPLES / "box.fbx")
    assert (r.scale, r.y_up, r.warnings) == (1.0, True, [])
    r = cad_read.resolve(SAMPLES / "box.fbx", unit="mm", axis="Z")
    assert (r.scale, r.y_up) == (0.001, False)


def test_resolve_3ds_is_not_flipped_and_warns(tmp_path):
    r = cad_read.resolve(SAMPLES / "cube.3ds")  # 3ds Max — Z yuqoriga (avval doim Y→Z o'girilardi)
    assert not r.y_up and r.scale == 1.0
    assert any("birlik" in w.lower() for w in r.warnings) and any("o'q" in w for w in r.warnings)


def test_resolve_dxf_units_and_freecad_factor(tmp_path):
    r = cad_read.resolve(_dxf(tmp_path / "m.dxf", 6), default_unit="mm")
    assert r.scale == 1.0 and not r.warnings and not r.y_up
    # FreeCAD importDXF $INSUNITS=m ni mm ga keltiradi (1 → 1000) — Blender ga ×0.001
    assert cad_read.freecad_dxf_factor(r) == pytest.approx(0.001)
    r = cad_read.resolve(_dxf(tmp_path / "u.dxf", 0), default_unit="mm")  # birliksiz — mm deb, ogohlantirish
    assert r.scale == 0.001 and r.warnings
    assert cad_read.freecad_dxf_factor(r) == pytest.approx(0.001)
    r = cad_read.resolve(tmp_path / "u.dxf", unit="m")  # foydalanuvchi: bu metr
    assert cad_read.freecad_dxf_factor(r) == pytest.approx(1.0) and not r.warnings


def test_transform_vertices():
    assert cad_read.transform_vertices([(1, 2, 3)], 0.5, True) == [(0.5, -1.5, 1.0)]
    assert cad_read.transform_vertices([(1, 2, 3)], 2.0, False) == [(2.0, 4.0, 6.0)]
