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


# --- CAD-06: DWG konverter — yangi papka, qaytish kodi, eski fayl qabul qilinmaydi --------------------------------

from sath import converters  # noqa: E402


class _Proc:
    def __init__(self, rc: int, err: str = ""):
        self.returncode, self.stderr, self.stdout = rc, err, ""


def _setup_converter(monkeypatch, tool: str, behave):
    monkeypatch.setattr(converters, "find_dwg2dxf", lambda: "dwg2dxf" if tool == "dwg2dxf" else None)
    monkeypatch.setattr(converters, "find_oda", lambda: "ODAFileConverter" if tool == "oda" else None)
    calls = []

    def fake(cmd, timeout):
        calls.append(list(cmd))
        return behave(cmd)

    monkeypatch.setattr(converters, "_run", fake)
    return calls


def _user_dwg(tmp_path) -> Path:
    user = tmp_path / "loyiha"
    user.mkdir()
    (user / "plan.dwg").write_bytes(b"AC1032")
    (user / "plan.dxf").write_text("eski")  # foydalanuvchi papkasidagi eski DXF
    (user / "boshqa.dwg").write_bytes(b"AC1032")
    return user / "plan.dwg"


def test_dwg2dxf_fresh_output_dir(tmp_path, monkeypatch):
    def ok(cmd):
        Path(cmd[3]).write_text("0\nEOF\n")
        return _Proc(0)

    _setup_converter(monkeypatch, "dwg2dxf", ok)
    out = tmp_path / "work"
    out.mkdir()
    (out / "plan.dxf").write_text("oldingi importdan qolgan")
    a = converters.dwg_to_dxf(_user_dwg(tmp_path), out)
    b = converters.dwg_to_dxf(tmp_path / "loyiha" / "plan.dwg", out)
    assert a != b and a.parent.parent == out and a.read_text() == "0\nEOF\n"


def test_dwg2dxf_stale_file_or_error_is_rejected(tmp_path, monkeypatch):
    dwg = _user_dwg(tmp_path)
    out = tmp_path / "work"
    _setup_converter(monkeypatch, "dwg2dxf", lambda cmd: _Proc(0))  # hech narsa yozmadi
    (tmp_path / "work").mkdir()
    (out / "plan.dxf").write_text("eski")
    with pytest.raises(RuntimeError, match="yaratmadi"):
        converters.dwg_to_dxf(dwg, out)

    def fail(cmd):
        Path(cmd[3]).write_text("yarim")
        return _Proc(1, "xato")

    _setup_converter(monkeypatch, "dwg2dxf", fail)
    with pytest.raises(RuntimeError, match="kod 1"):
        converters.dwg_to_dxf(dwg, out)


def test_oda_gets_isolated_input_dir_and_rc_checked(tmp_path, monkeypatch):
    dwg = _user_dwg(tmp_path)
    seen = {}

    def oda(cmd):
        in_dir, out_dir = Path(cmd[1]), Path(cmd[2])
        seen["inputs"] = sorted(p.name for p in in_dir.iterdir())
        seen["in_dir"] = in_dir
        (out_dir / "plan.dxf").write_text("0\nEOF\n")
        return _Proc(seen.get("rc", 0))

    calls = _setup_converter(monkeypatch, "oda", oda)
    res = converters.dwg_to_dxf(dwg, tmp_path / "work")
    assert Path(calls[0][1]) != dwg.parent and seen["inputs"] == ["plan.dwg"]  # faqat shu DWG nusxasi
    assert not seen["in_dir"].exists() and res.is_file()  # kirish nusxasi o'chirildi
    seen["rc"] = 2
    with pytest.raises(RuntimeError, match="kod 2"):
        converters.dwg_to_dxf(dwg, tmp_path / "work")


def test_no_converter(tmp_path, monkeypatch):
    _setup_converter(monkeypatch, "none", lambda cmd: _Proc(0))
    with pytest.raises(RuntimeError, match="topilmadi"):
        converters.dwg_to_dxf(_user_dwg(tmp_path), tmp_path / "w")
    assert list((tmp_path / "w").iterdir()) == []


# --- CAD-07: GUID nomdan / fayl xususiyatlaridan -----------------------------------------------------------------


def test_name_and_guid():
    g = "2O2Fr$t4X7Zf8NOew3FLOH"
    assert cad_read.name_and_guid(f"Devor [{g}]", {}) == ("Devor", g)
    assert cad_read.name_and_guid("Devor", {"Devor": g}) == ("Devor", g)
    assert cad_read.name_and_guid("Devor [qisqa]", {}) == ("Devor [qisqa]", None)


def test_file_guids_from_fbx_user_props(tmp_path):
    fbx = tmp_path / "a.fbx"
    fbx.write_text(
        'Objects:  {\n\tModel: 1, "Model::Quvur", "Mesh" {\n\t\tProperties70:  {\n'
        '\t\t\tP: "sath_guid", "KString", "", "U", "0K7w7JLKn3sgmPz7rVkzq1"\n\t\t}\n\t}\n}\n',
        encoding="utf-8",
    )
    assert cad_read.file_guids(fbx) == {"Quvur": "0K7w7JLKn3sgmPz7rVkzq1"}


def test_file_guids_obj_names_truncated_by_assimp(tmp_path):
    obj = tmp_path / "e.obj"
    obj.write_text(
        "o Togon [2O2Fr$t4X7Zf8NOew3FLOH]\nv 0 0 0\no Devor [0K7w7JLKn3sgmPz7rVkzq1]\no Devor [1K7w7JLKn3sgmPz7rVkzq1]\n"
    )
    assert cad_read.file_guids(obj) == {"Togon": "2O2Fr$t4X7Zf8NOew3FLOH"}  # Devor — noaniq, olinmaydi
