"""CAD import (mesh_import): parallel importlar, bloklar, aralash 2D/3D, birliklar, GUID round-trip, konverterlar."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from ges_server.models import mesh_import  # noqa: E402


def _linework_dxf(path: Path, ox: float, oy: float, insunits: int = 6) -> Path:
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    msp.add_line((ox, oy), (ox + 300, oy), dxfattribs={"layer": "OQ"})
    msp.add_line((ox, oy), (ox, oy + 200), dxfattribs={"layer": "OQ"})
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
