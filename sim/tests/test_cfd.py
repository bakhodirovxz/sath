import os
import shutil
from pathlib import Path

import pytest
from ges_sim.cfd import PenstockCase, SpillwayCase, build_case, run_case
from ges_sim.cfd.runner import _read_raw, collect_results
from ges_sim.penstock import PenstockSpec, head_loss


def test_penstock_case_files(tmp_path):
    case = build_case(
        {
            "kind": "penstock",
            "length_m": 10,
            "diameter_m": 2.0,
            "flow_m3s": 15,
            "roughness_mm": 0.2,
        },
        tmp_path,
    )
    assert isinstance(case, PenstockCase)
    assert case.inlet_velocity == pytest.approx(15 / (3.14159265 * 1.0), rel=1e-4)
    for f in (
        "system/blockMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "0/U",
        "0/p",
        "0/k",
        "0/epsilon",
        "0/nut",
        "system/sample",
        "system/plane",
        "Allrun",
    ):
        assert (tmp_path / f).exists(), f
    bm = (tmp_path / "system/blockMeshDict").read_text()
    assert "type wedge" in bm and "type empty" in bm and "(10 0 0)" in bm
    assert "nutkRoughWallFunction" in (tmp_path / "0/nut").read_text()
    assert "simpleFoam" in (tmp_path / "system/controlDict").read_text()
    assert "\r" not in (tmp_path / "Allrun").read_bytes().decode()  # Linux uchun LF


def test_penstock_smooth_wall_and_validation(tmp_path):
    build_case({"kind": "penstock", "roughness_mm": 0}, tmp_path)
    assert "nutkWallFunction" in (tmp_path / "0/nut").read_text()
    with pytest.raises(ValueError):
        build_case({"kind": "penstock", "diameter_m": -1}, tmp_path)
    with pytest.raises(ValueError):
        build_case({"kind": "boshqa"}, tmp_path)
    with pytest.raises(ValueError):
        build_case({"kind": "spillway", "resolution": 10}, tmp_path)


def test_spillway_case_files(tmp_path):
    case = build_case(
        {"kind": "spillway", "crest_height_m": 3, "head_m": 1.2, "crest_length_m": 5}, tmp_path
    )
    assert isinstance(case, SpillwayCase)
    assert case.q == pytest.approx(1.7 * 1.2**1.5)
    bm = (tmp_path / "system/blockMeshDict").read_text()
    assert bm.count("hex (") == 5 and "weir" in bm and "atmosphere" in bm
    assert "interFoam" in (tmp_path / "system/controlDict").read_text()
    assert "variableHeightFlowRateInletVelocity" in (tmp_path / "0/U").read_text()
    assert f"{case.q:.6g}" in (tmp_path / "0/U").read_text()
    sf = (tmp_path / "system/setFieldsDict").read_text()
    assert "4.2" in sf  # boshlang'ich suv sathi = 3 + 1.2
    assert (tmp_path / "constant/g").read_text().count("-9.81") == 1
    assert build_case({"kind": "spillway", "unit_discharge_m2s": 2.5}, tmp_path).q == 2.5


def test_read_raw_and_collect_from_synthetic(tmp_path):
    # OpenFOAM chiqishini taqlid qilib parserni tekshiramiz (Docker siz)
    case = PenstockCase(length_m=10, diameter_m=2, flow_m3s=15)
    (tmp_path / "postProcessing/sample/100").mkdir(parents=True)
    (tmp_path / "postProcessing/plane/100").mkdir(parents=True)
    rows = "\n".join(f"{x:.2f} {1.0 - 0.05 * x:.4f} 4.7 0 0" for x in [0.5, 2, 4, 6, 8, 9.5])
    (tmp_path / "postProcessing/sample/100/axis_p_U.xy").write_text(rows)
    (tmp_path / "postProcessing/sample/100/radial_p_U.xy").write_text(
        "0 0.5 5.0 0 0\n0.9 0.5 3.0 0 0\n"
    )
    (tmp_path / "postProcessing/plane/100/p_plane.raw").write_text(
        "# p\n# x y z p\n1 0.2 0 0.9\n2 0.4 0 0.8\n"
    )
    (tmp_path / "postProcessing/plane/100/U_plane.raw").write_text(
        "# U\n1 0.2 0 4 0 0\n2 0.4 0 3 0 0\n"
    )
    (tmp_path / "log.blockMesh").write_text("  nCells: 636\n")
    r = collect_results(case, tmp_path)
    assert r["summary"]["cells"] == 636
    assert r["summary"]["head_loss_m"] == pytest.approx(
        (1.0 - 0.025 - (1.0 - 0.475)) / 9.81, rel=1e-3
    )
    assert r["summary"]["max_velocity"] == 5.0
    assert r["radial"]["u"] == [5.0, 3.0]
    assert r["plane"][0] == {
        "x": 1.0,
        "y": 0.2,
        "p": pytest.approx(0.9 * 998.2, rel=1e-3),
        "u": 4.0,
    }
    assert _read_raw(None) == [] and _read_raw("") == []


@pytest.mark.skipif(
    os.environ.get("GES_TEST_CFD") != "1" or not shutil.which("docker"),
    reason="Haqiqiy OpenFOAM hisobi: GES_TEST_CFD=1 va docker kerak (≈30 s)",
)
def test_penstock_real_run_matches_darcy_weisbach(tmp_path):
    case = build_case(
        {
            "kind": "penstock",
            "length_m": 12,
            "diameter_m": 2.4,
            "flow_m3s": 20,
            "resolution": 0.6,
            "max_iterations": 150,
        },
        tmp_path,
    )
    run_case(tmp_path, case.max_iterations, mode="docker", timeout_s=900)
    r = collect_results(case, Path(tmp_path))
    dw = head_loss(20, PenstockSpec(12, 2.4, 0.1, 0.0))
    # kirishdagi rivojlanayotgan oqim tufayli CFD biroz kattaroq; ±40 % oralig'ida
    assert 0.7 * dw < r["summary"]["head_loss_m"] < 1.4 * dw
    assert r["summary"]["cells"] and len(r["axis"]["x"]) == 100


def test_geometry_case_files(tmp_path):
    """Model geometriyasi (STL) atrofida oqim: snappyHexMesh + simpleFoam case, kuchlar funksiyasi."""
    c = build_case(
        {
            "kind": "geometry",
            "bbox": [[10, -17, 12], [22, -7, 13]],
            "velocity_ms": 1.5,
            "flow_axis": "x",
        },
        tmp_path,
    )
    lo, hi = c.domain()
    assert lo[0] < 10 - 20 and hi[0] > 22 + 50  # oldinda 2L, orqada 5L (L=12)
    snappy = (tmp_path / "system/snappyHexMeshDict").read_text()
    assert "body.stl" in snappy and "locationInMesh" in snappy and "refinementSurfaces" in snappy
    assert "forces" in (tmp_path / "system/controlDict").read_text()
    assert (
        "inlet  { type fixedValue; value uniform (1.5 0.0 0.0); }" in (tmp_path / "0/U").read_text()
    )
    assert "snappyHexMesh -overwrite" in (tmp_path / "Allrun").read_text()
    with pytest.raises(ValueError):
        build_case({"kind": "geometry", "bbox": [[0, 0, 0], [0, 1, 1]]}, tmp_path)
    with pytest.raises(ValueError):
        build_case({"kind": "geometry", "bbox": [[0, 0, 0], [1, 1, 1]], "flow_axis": "z"}, tmp_path)
