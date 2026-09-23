"""CAD import (mesh_import): parallel importlar, bloklar, aralash 2D/3D, birliklar, GUID round-trip, konverterlar."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from ges_server.models import mesh_import  # noqa: E402


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models", json={"name": "M"}, headers=users["engineer"]
    )
    return r.json()["id"]


def _post(client, users, model_id, path: Path, **data):
    with path.open("rb") as fh:
        return client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            headers=users["engineer"],
            data={k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in data.items()},
            files={"file": (path.name, fh, "application/octet-stream")},
        )


def _linework_dxf(path: Path, ox: float, oy: float, insunits: int = 6, size: float = 300) -> Path:
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    msp.add_line((ox, oy), (ox + size, oy), dxfattribs={"layer": "OQ"})
    msp.add_line((ox, oy), (ox, oy + size * 2 / 3), dxfattribs={"layer": "OQ"})
    doc.saveas(path)
    return path


def _offset(objs: list[dict]) -> tuple[float, float]:
    ps = objs[0]["psets"]["Pset_GES_Import"]
    return ps["Asl_siljish_X"], ps["Asl_siljish_Y"]


def test_parallel_dxf_imports_do_not_share_state(tmp_path, monkeypatch):
    """CAD-05: ikki oqim bir vaqtda turli DXF import qiladi — har biri o'z siljishini oladi (global holat yo'q)."""
    a = _linework_dxf(tmp_path / "a.dxf", 1000, 2000)
    b = _linework_dxf(tmp_path / "b.dxf", 50000, 70000)
    assert not hasattr(mesh_import, "_LAST_DXF_INFO")
    barrier = threading.Barrier(2, timeout=60)
    orig = mesh_import._load_dxf

    def slow_load(*args, **kw):
        res = orig(*args, **kw)
        barrier.wait()  # ikkala oqim ham DXF ni o'qib bo'lgach davom etadi — global bo'lsa biri ustiga yozardi
        return res

    monkeypatch.setattr(mesh_import, "_load_dxf", slow_load)
    results: dict[str, list] = {}
    errors: list[BaseException] = []

    def run(key: str, path: Path) -> None:
        try:
            results[key] = mesh_import.load_objects(path)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run, args=k) for k in (("a", a), ("b", b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert not errors, errors
    assert _offset(results["a"]) == (1000.0, 2000.0)
    assert _offset(results["b"]) == (50000.0, 70000.0)


def test_dxf_block_with_3dface_is_expanded_with_transform(tmp_path):
    """CAD-03: blok ichidagi 3DFACE (ichma-ich blok ham) — INSERT joyi, masshtabi, burilishi bilan import qilinadi;
    blok ichidagi «0» qatlam INSERT qatlamiga o'tadi."""
    import numpy as np

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    inner = doc.blocks.new("ICHKI")
    inner.add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], dxfattribs={"layer": "0"})
    outer = doc.blocks.new("TASHQI")
    outer.add_blockref("ICHKI", (10, 0, 0))
    msp = doc.modelspace()
    msp.add_blockref("ICHKI", (100, 200, 5), dxfattribs={"layer": "TOGON", "xscale": 2, "yscale": 2, "rotation": 90})
    msp.add_blockref("TASHQI", (0, 0, 0), dxfattribs={"layer": "DEVOR"})
    dxf = tmp_path / "blok.dxf"
    doc.saveas(dxf)
    objs, info = mesh_import.load_objects_ex(dxf)
    by = {o["name"]: o for o in objs}
    assert set(by) == {"TOGON", "DEVOR"} and info.dxf.inserts == 3

    def world(o):
        t = o["transform"]
        return np.asarray(o["mesh"]["vertices"]) + [t["x"], t["y"], t["z"]]

    w = world(by["TOGON"])  # 90° burilgan, 2× masshtab: x ∈ [98, 100], y ∈ [200, 202], z = 5
    assert np.allclose(w.min(axis=0), [98, 200, 5]) and np.allclose(w.max(axis=0), [100, 202, 5])
    d = world(by["DEVOR"])  # ichma-ich: TASHQI(0,0) → ICHKI(10,0)
    assert np.allclose(d.min(axis=0), [10, 0, 0]) and np.allclose(d.max(axis=0), [11, 1, 0])


def test_dxf_self_referencing_block_is_cycle_safe(tmp_path):
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new("SIKL")
    blk.add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0)], dxfattribs={"layer": "A"})
    blk.add_blockref("SIKL", (5, 0, 0))  # o'zini o'zi chaqiradi
    doc.modelspace().add_blockref("SIKL", (0, 0, 0))
    dxf = tmp_path / "sikl.dxf"
    doc.saveas(dxf)
    objs = mesh_import.load_objects(dxf)
    assert len(objs) == 1 and len(objs[0]["mesh"]["faces"]) == 1


def test_mixed_2d_3d_dxf_reports_dropped_2d(tmp_path):
    """CAD-03: 3D yuzalar + 2D chiziqlar (blok ichida ham) — 2D lar jimgina yo'qolmaydi, soni natijada."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_3dface([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)], dxfattribs={"layer": "TOGON"})
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "OQ"})
    msp.add_text("Izoh", dxfattribs={"layer": "MATN"})
    blk = doc.blocks.new("SHTAMP")
    blk.add_line((0, 0), (1, 1))
    blk.add_circle((0, 0), 1)
    msp.add_blockref("SHTAMP", (20, 0))
    dxf = tmp_path / "aralash.dxf"
    doc.saveas(dxf)
    objs, info = mesh_import.load_objects_ex(dxf)
    assert [o["name"] for o in objs] == ["TOGON"]
    assert info.dxf.skipped_2d == 4
    assert info.dxf.skipped_types == {"CIRCLE": 1, "LINE": 2, "TEXT": 1}
    assert info.warnings and "4 ta 2D element" in info.warnings[0]
    assert info.to_dict()["dxf"]["skipped_2d"] == 4


def test_import_api_returns_dropped_2d_warning(client, users, model_id, tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_3dface([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)], dxfattribs={"layer": "TOGON"})
    msp.add_line((0, 0), (10, 0))
    dxf = tmp_path / "aralash.dxf"
    doc.saveas(dxf)
    r = _post(client, users, model_id, dxf)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 1 and body["import_info"]["dxf"]["skipped_2d"] == 1
    assert body["warnings"] and "2D" in body["warnings"][0]


# --- CAD-04: birlik jimgina taxmin qilinmaydi -----------------------------------------------------------------


def test_small_mm_drawing_is_flagged_not_scaled(tmp_path):
    """$INSUNITS=mm, chizma 150 birlik — avval jimgina ×1000 (metr) qilinardi; endi mm qoladi va belgi qo'yiladi."""
    dxf = _linework_dxf(tmp_path / "kichik.dxf", 0, 0, insunits=4, size=150)
    objs, info = mesh_import.load_objects_ex(dxf)
    assert info.unit == "mm" and info.scale == 0.001 and info.units_uncertain
    assert info.unit_source == "$INSUNITS" and "200 mm" in info.unit_note and info.warnings
    # foydalanuvchi aniq tanlasa (unit_override) — metr
    objs, info = mesh_import.load_objects_ex(dxf, unit="m", auto_unit=False)
    assert info.unit == "m" and info.scale == 1.0 and not info.units_uncertain
    assert info.unit_source == "foydalanuvchi"
    assert objs[0]["psets"]["Pset_GES_Import"]["Birlik"] == "m"


def test_dxf_offset_stored_in_metres(tmp_path):
    """Asl_siljish_X/Y — metrda (mm chizmada ham)."""
    dxf = _linework_dxf(tmp_path / "geo.dxf", 532_000_000, 4_400_000_000, insunits=4)
    objs, info = mesh_import.load_objects_ex(dxf)
    assert not info.units_uncertain
    assert _offset(objs) == (532_000.0, 4_400_000.0)


def test_unknown_units_are_flagged(tmp_path):
    obj = tmp_path / "a.obj"
    obj.write_text("o Kub\nv 0 0 0\nv 1 0 0\nv 1 1 0\nf 1 2 3\n")
    _objs, info = mesh_import.load_objects_ex(obj)
    assert info.units_uncertain and info.unit == "m" and info.unit_source == "aniqlanmadi"
    assert not info.y_up  # OBJ o'qi aniq emas — taklif (Y) qo'llanmaydi


def test_gltf_axis_from_spec_and_fbx_from_metadata(tmp_path):
    import numpy as np
    import trimesh

    s = trimesh.Scene()
    s.add_geometry(trimesh.creation.box(extents=(1, 2, 3)), node_name="Quti")
    glb = tmp_path / "q.glb"
    glb.write_bytes(s.export(file_type="glb"))
    objs, info = mesh_import.load_objects_ex(glb)
    assert info.y_up and info.up_axis == "Y" and not info.units_uncertain
    ext = np.ptp(np.asarray(objs[0]["mesh"]["vertices"]), axis=0)
    assert np.allclose(ext, (1, 3, 2))  # glTF Y (2) → Z
    objs, info = mesh_import.load_objects_ex(glb, y_up=False)  # aniq berilgan qiymat ustun
    assert not info.y_up
    fbx = Path(__file__).parent / "samples" / "box.fbx"
    _objs, info = mesh_import.load_objects_ex(fbx)
    assert info.unit == "m" and info.unit_source == "FBX UnitScaleFactor" and info.y_up


def test_import_api_units_uncertain_and_override(client, users, model_id, tmp_path):
    dxf = _linework_dxf(tmp_path / "kichik.dxf", 0, 0, insunits=4, size=150)
    r = _post(client, users, model_id, dxf)
    assert r.status_code == 201, r.text
    assert r.json()["units_uncertain"] is True and r.json()["import_info"]["unit"] == "mm"
    r = _post(client, users, model_id, dxf, unit="m", unit_override=True)
    assert r.status_code == 201, r.text
    assert r.json()["units_uncertain"] is False and r.json()["import_info"]["unit"] == "m"
