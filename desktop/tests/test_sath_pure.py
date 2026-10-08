"""sath addonining bpy siz qismlari: sync, pset guruhlash, IFC klass xaritasi, viewpoint matematikasi."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "build"))
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

import sync_blender  # noqa: E402


def test_shared_is_synced():
    assert sync_blender.check() == [], "python desktop/build/sync_blender.py ni ishga tushiring"


def test_common_copies_byte_identical_to_canonical():
    """CODE-01: har umumiy modulning yagona manbasi common/sath_common; nusxalar (addon, server)
    bayt-bayt bir xil — farq bo'lsa CI yiqiladi."""
    pairs = sync_blender.copies()
    dsts = {d.relative_to(ROOT).as_posix() for _, d in pairs}
    for f in ("assimp_load.py", "dxf_prepare.py"):
        assert f"server/ges_server/models/{f}" in dsts
        assert f"desktop/blender/sath/shared/{f}" in dsts
    for src, dst in pairs:
        if src.parent == sync_blender.SRC:
            assert src.read_bytes() == dst.read_bytes(), dst

from sath import flows, viewpoint  # noqa: E402


def test_orphans_text_counts_unlinked_by_class():
    items = [{"class": "IfcPropertySet"}, {"class": "IfcShapeRepresentation"}, {"class": "IfcPropertySet"}]
    lines = flows.orphans_text(items).splitlines()
    assert lines[0] == "Yetim IFC entitylar: 3"
    assert lines[1] == "Bog'lanmagan: IfcPropertySet ×2, IfcShapeRepresentation ×1"


def test_viewpoint_from_view_ifc_space_metres():
    vp = viewpoint.from_view(
        position=(10.0, 20.0, 5.0), direction=(0.0, 1.0, 0.0), distance=4.0, is_ortho=False, guids=["a"]
    )
    assert vp["camera"]["space"] == "ifc"
    assert vp["camera"]["position"] == [10.0, 20.0, 5.0]
    assert vp["camera"]["target"] == [10.0, 24.0, 5.0]
    assert vp["camera"]["projection"] == "Perspective"
    assert vp["selected_guids"] == ["a"] and vp["section"] == []


def test_viewpoint_view_params_from_camera():
    loc, d, dist = viewpoint.view_params({"position": [0, 0, 0], "target": [0, 0, -3]})
    assert loc == (0.0, 0.0, -3.0) and dist == 3.0
    assert tuple(round(x, 6) for x in d) == (0.0, 0.0, -1.0)


def test_diff_colors_maps_added_changed_and_summary():
    colors, text = flows.diff_colors(
        {
            "added": [{"guid": "A"}],
            "changed": [{"guid": "B"}],
            "deleted": [{"guid": "C", "name": "Devor"}],
            "summary": {"added": 1, "changed": 1, "deleted": 1},
        }
    )
    assert colors == {"A": flows.DIFF_COLORS["added"], "B": flows.DIFF_COLORS["changed"]}
    assert "+1" in text and "~1" in text and "Devor" in text


def test_addon_version_from_manifest():
    import re

    assert re.match(r"\d+\.\d+\.\d+", flows.ADDON_VERSION)


def test_sim_values_casts_by_field_type():
    fields = [
        {"key": "q", "type": "number"}, {"key": "n", "type": "int"}, {"key": "b", "type": "bool"},
        {"key": "s", "type": "series"}, {"key": "sel", "type": "select"}, {"key": "t", "type": "text"},
    ]  # fmt: skip
    raw = {"q": "12,5", "n": "3", "b": True, "s": "1, 2;3", "sel": "x", "t": " ab "}
    assert flows.sim_values(fields, raw) == {
        "q": 12.5, "n": 3.0, "b": True, "s": [1.0, 2.0, 3.0], "sel": "x", "t": "ab",
    }  # fmt: skip


def test_sim_result_rows_and_water_level():
    kind = {
        "outputs": [{"key": "max_level", "label": "Maks sath", "unit": "m"}],
        "viz": {"water_level": "level"},
    }
    rows, lvl = flows.sim_result_rows(
        kind,
        {"summary": {"verdict": "OK", "ok": True, "max_level": 101.234}, "series": {"level": [99.0, 101.2]}},
    )
    assert rows[0] == {"name": "Xulosa", "col2": "OK", "state": "ok"}
    assert rows[1] == {"name": "Maks sath", "col2": "101.23 m", "state": ""}
    assert lvl == 101.2


def test_safety_rows():
    head, rows = flows.safety_rows(
        {
            "score": 80, "verdict": "yaxshi",
            "counts": {"ok": 10, "warn": 1, "fail": 1, "skip": 0},
            "rows": [{"title": "Toshqin", "status": "warn", "message": "chegara", "metrics": {"k": 1.234}}],
        }  # fmt: skip
    )
    assert head.startswith("80 / 100") and rows[0]["state"] == "ogohlantirish"
    assert "k = 1.23" in rows[0]["col3"]


def test_sensor_rows_alarm_colors_and_water():
    sensors = [
        {"id": 1, "name": "Sath", "key": "lvl", "kind": "level", "unit": "m", "last_value": 101.5,
         "alarm": "ok", "enabled": True, "element_guid": "G1", "last_ts": "2026-09-17T10:00:00"},
        {"id": 2, "name": "Bosim", "key": "p", "kind": "pressure", "unit": "bar", "last_value": None,
         "alarm": "stale", "enabled": True, "element_guid": "G2"},
        {"id": 3, "name": "O'chiq", "key": "x", "kind": "level", "last_value": 5.0, "alarm": "high",
         "enabled": False, "element_guid": "G3"},
    ]  # fmt: skip
    rows = flows.sensor_rows(sensors)
    assert rows[0]["col2"] == "101.50 m" and rows[0]["state"] == "normal" and rows[0]["guid"] == "G1"
    assert rows[0]["col3"] == "2026-09-17 10:00"
    assert rows[1]["col2"] == "—" and rows[1]["state"] == "uzilgan"
    assert flows.alarm_colors(sensors) == {
        "G1": flows.ALARM_COLORS["ok"], "G2": flows.ALARM_COLORS["stale"],
    }  # fmt: skip
    assert flows.water_sensor_level(sensors) == 101.5


def test_twin_rows_head_and_health():
    state = {
        "status": "ok", "head_gross_m": 45.25, "expected_total_mw": 50.0, "measured_total_mw": 47.5,
        "units": [
            {"name": "Agregat 1", "running": True, "measured_mw": 25.0, "expected_mw": 26.0, "deviation_pct": -3.85, "efficiency": 0.91},
            {"name": "Agregat 2", "running": False, "measured_mw": None, "expected_mw": 24.0, "deviation_pct": None, "efficiency": None},
        ],
        "safety": [{"name": "Gerb zaxirasi", "value": 2.5, "unit": "m", "ok": True}, {"name": "Sirpanish", "value": 1.2, "unit": "", "ok": False}],
    }  # fmt: skip
    assert flows.twin_head(state) == "Napor 45.25 m · 47.5 / 50.0 MW (o'lchangan / kutilgan)"
    rows = flows.twin_rows(state)
    assert rows[0]["name"] == "Agregat 1" and rows[0]["col2"] == "25.0 / 26.0 MW" and rows[0]["col3"] == "−3.9 %" and rows[0]["state"] == "ok"
    assert rows[1]["col2"] == "— / 24.0 MW" and rows[1]["state"] == "stop"
    srows = flows.twin_safety_rows(state["safety"])
    assert srows[0] == {"name": "Gerb zaxirasi", "col2": "2.5 m", "state": "ok"}
    assert srows[1]["state"] == "fail"
    h = {"plant_score": 72, "assets": [
        {"asset_id": 1, "name": "Agregat 1", "element_guid": "G1", "score": 85, "level": "yaxshi", "problems": []},
        {"asset_id": 2, "name": "Agregat 2", "element_guid": None, "score": 35, "level": "kritik", "problems": ["tebranish D zona"]},
    ]}  # fmt: skip
    assert flows.health_head(h) == "Stansiya sog'lig'i: 72 / 100"
    hr = flows.health_rows(h)
    assert hr[0]["col2"] == "85" and hr[0]["state"] == "yaxshi" and hr[0]["guid"] == "G1"
    assert hr[1]["col3"] == "tebranish D zona"
    assert flows.health_colors(h["assets"]) == {"G1": flows.HEALTH_COLORS["yaxshi"]}


def test_reading_at_picks_latest_before_ts():
    pts = [{"ts": "2026-09-17T10:00:00+00:00", "value": 1.0}, {"ts": "2026-09-17T11:00:00+00:00", "value": 2.0}, {"ts": "2026-09-17T12:00:00+00:00", "value": 3.0}]
    assert flows.reading_at(pts, "2026-09-17T11:30:00+00:00") == 2.0
    assert flows.reading_at(pts, "2026-09-17T09:00:00+00:00") is None
    assert flows.reading_at([], "2026-09-17T09:00:00+00:00") is None


def test_ci_annotate_robust(tmp_path, capsys):
    """CI-01: report.xml yo'q/buzilgan bo'lsa traceback emas — ::error:: va exit 2; xato bo'lsa 1, o'tsa 0."""
    import ci_annotate

    assert ci_annotate.main(str(tmp_path / "yoq.xml")) == 2
    assert "::error" in capsys.readouterr().out
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuite><testcase", encoding="utf-8")
    assert ci_annotate.main(str(bad)) == 2
    ok = tmp_path / "ok.xml"
    ok.write_text('<testsuite><testcase classname="a" name="b"/></testsuite>', encoding="utf-8")
    assert ci_annotate.main(str(ok)) == 0
    fail = tmp_path / "fail.xml"
    fail.write_text('<testsuite><testcase classname="a" name="b"><failure message="x">tb</failure></testcase></testsuite>', encoding="utf-8")
    assert ci_annotate.main(str(fail)) == 1


def test_bonsai_pinned_sha256(tmp_path, monkeypatch):
    """CI-03: Bonsai zip qotirilgan sha256 ga mos kelmasa bundle yig'ilmaydi."""
    import hashlib

    import build_blender_bundle as bb
    import pytest

    z = tmp_path / f"bonsai-{bb.BONSAI_VERSION}-py313-win64.zip"
    z.write_bytes(b"soxta")
    with pytest.raises(SystemExit, match="sha256"):
        bb.ensure_bonsai(z, "5.2.2")
    monkeypatch.setattr(bb, "BONSAI_SHA256", hashlib.sha256(b"soxta").hexdigest())
    assert bb.ensure_bonsai(z, "5.2.2") == z
    monkeypatch.setattr(bb, "TOOLS", tmp_path)
    assert bb.ensure_bonsai(None, "5.2.2") == z  # kesh: faqat qotirilgan versiya nomi


def test_unassigned_objects_warning_text():
    objs = [
        ("FBX_Togon", "MESH", False, False), ("GES_Suv", "MESH", False, True), ("Devor", "MESH", True, False),
        ("DXF_OQ_chiziq", "CURVE", False, False), ("Kamera", "CAMERA", False, False),
    ]  # fmt: skip
    names = flows.unassigned_objects(objs)
    assert names == ["FBX_Togon", "DXF_OQ_chiziq"]
    assert flows.unassigned_text(names) == "IFC ga kirmagan obyektlar: 2 — FBX_Togon, DXF_OQ_chiziq"
    assert flows.unassigned_text([f"o{i}" for i in range(6)], limit=2).endswith("o0, o1 … (+4)")
    assert flows.unassigned_text([]) == ""


def test_freecad_removed_from_desktop():
    """P2 (K1): FreeCAD desktopdan chiqdi — dvigatel, workbench nusxasi, legacy workbench/fork skriptlari, FreeCAD
    testlari repoda yo'q; addon kodida FreeCAD importi yo'q (legacy — `archive/freecad-legacy` tegida)."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git yo'q")
    gone = [
        "desktop/blender/sath/fc_engine.py", "desktop/blender/sath/wb", "desktop/GesWorkbench", "desktop/blender/spike",
        "desktop/build/sync_fork.py", "desktop/build/build_portable.py", "desktop/tests/test_freecad_cad.py",
    ]  # fmt: skip
    tracked = subprocess.run(["git", "ls-files", *gone], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert tracked.strip() == "", tracked
    for py in (ROOT / "desktop" / "blender" / "sath").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "import FreeCAD" not in src and "fc_engine" not in src, py


def test_package_name_and_product_in_build_info():
    """CODE-03: Blender bundle nomi va build metama'lumotidagi product (legacy FreeCAD paketi arxivlangan)."""
    import build_blender_bundle as bb

    assert bb.artifact_name("0.3.0") == "Sath-Blender-0.3.0-Windows-x86_64"
    assert bb.build_info("0.3.0")["product"] == "sath-blender"


def test_binaries_in_git_lfs_and_no_local_user_paths():
    """CODE-04: katta binar fayllar Git LFS da (indeksda pointer), ish nusxasida haqiqiy fayl (smudge);
    lokal foydalanuvchi yo'llari (C:/Users/<nom>) va spike loglari repoda yo'q."""
    import re
    import shutil
    import subprocess

    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pat in ("*.FCStd", "*.whl", "*.dwg", "*.fbx", "*.3ds", "*.blend"):
        assert f"{pat} filter=lfs diff=lfs merge=lfs -text" in attrs, pat
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        return
    files = subprocess.run([git, "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    assert not [f for f in files if f.startswith("desktop/blender/spike/") and f.endswith(".log")]
    lfs = subprocess.run([git, "lfs", "ls-files", "-n"], cwd=ROOT, capture_output=True, text=True)
    if lfs.returncode == 0:
        tracked = set(lfs.stdout.splitlines())
        binaries = {f for f in files if re.search(r"\.(fcstd|whl|dwg|fbx|3ds|blend)$", f, re.I)}
        assert binaries and binaries <= tracked, binaries - tracked
        # ish nusxasida pointer emas, haqiqiy fayl (testlar shu fayllarni o'qiydi)
        assert (ROOT / "server" / "tests" / "samples" / "box.fbx").read_bytes()[:7] == b"Kaydara"
    bad = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<)[^\\/\s\"']+[\\/]", re.I)
    for f in files:
        if not f.endswith((".py", ".ps1", ".md", ".toml", ".yml", ".json", ".txt")) or f.endswith("package-lock.json"):
            continue
        p = ROOT / f
        if p.is_file() and bad.search(p.read_text(encoding="utf-8", errors="replace")):
            raise AssertionError(f"lokal foydalanuvchi yo'li: {f}")


def test_desktop_tests_have_no_hardcoded_admin_password(monkeypatch):
    """Desktop testlari admin parolini muhitdan oladi (GES_TEST_PASSWORD), yo'q bo'lsa tushunarli xato."""
    import importlib

    import pytest

    for p in (ROOT / "desktop" / "tests").rglob("*"):
        if p.suffix in (".py", ".ps1") and p.name != "test_sath_pure.py":
            assert "admin123" not in p.read_text(encoding="utf-8-sig"), p
    sys.path.insert(0, str(ROOT / "desktop" / "tests" / "sath_tests"))
    creds = importlib.import_module("creds")
    monkeypatch.delenv("GES_TEST_PASSWORD", raising=False)
    monkeypatch.delenv("GES_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="GES_TEST_PASSWORD"):
        creds.admin_password()
    monkeypatch.setenv("GES_TEST_PASSWORD", "x-parol")
    assert creds.admin_password() == "x-parol"


def test_orphans_text_lists_lost_elements_by_name_and_guid():
    lost = [
        {"id": i, "class": "IfcWall", "name": f"Devor {i}", "guid": f"G{i:03d}", "reason": flows.ORPHAN_LOST}
        for i in range(12)
    ]
    other = [
        {"id": 100, "class": "IfcPropertySet", "name": "", "guid": "", "reason": "hech narsaga bog'lanmagan"},
        {"id": 101, "class": "IfcPropertySet", "name": "", "guid": "", "reason": "hech narsaga bog'lanmagan"},
    ]
    assert flows.orphans_text([]) == ""
    lines = flows.orphans_text(lost + other).splitlines()
    assert lines[0] == "Yetim IFC entitylar: 14"
    assert "IfcWall «Devor 0» [G000]" in lines[2] and any("[G009]" in x for x in lines)
    assert not any("[G010]" in x for x in lines) and any("yana 2 ta" in x for x in lines)
    assert any(x == "Bog'lanmagan: IfcPropertySet ×2" for x in lines)
    assert "qayta hisoblanadi" in lines[-1]
