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
    assert "type wedge" in bm and "type empty" in bm and "(10.0 0 0)" in bm
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


@pytest.mark.parametrize(
    "params",
    [
        {"kind": "penstock", "max_iterations": "1;\nfoo"},
        {"kind": "spillway", "end_time_s": '#include "/data/secret.key"'},
        {"kind": "geometry", "refinement": "2; #include"},
        {"kind": "geometry", "flow_axis": "x;"},
        {"kind": "penstock", "extra": 1},
        {"kind": "spillway", "end_time_s": float("inf")},
    ],
)
def test_build_case_rejects_raw_strings(tmp_path, params):
    """SEC-01: build_case (worker yo'li) ham qat'iy sxemadan o'tadi — hech narsa yozilmaydi."""
    with pytest.raises(ValueError):
        build_case(params, tmp_path)
    assert not any(tmp_path.iterdir())


def test_case_objects_coerce_numbers(tmp_path):
    """Sxemasiz (qo'lda) yaratilgan case ham xom satrni dictionary ga yoza olmaydi."""
    with pytest.raises(ValueError):
        SpillwayCase(end_time_s="1;\nfoo")
    with pytest.raises(ValueError):
        PenstockCase(max_iterations="400")
    case = build_case({"kind": "spillway", "end_time_s": 12}, tmp_path)
    cd = (tmp_path / "system/controlDict").read_text()
    assert "endTime         12;" in cd and "writeInterval   12;" in cd
    assert isinstance(case.end_time_s, float)


# ---------- OPS-05: timeout solverni haqiqatan to'xtatadi ----------

_CHILD = """
import os, subprocess, sys, time
hb = sys.argv[1]
if len(sys.argv) > 2:  # nevara: yurak urishini faylga yozadi
    while True:
        with open(hb, "a") as fh:
            fh.write("x")
        time.sleep(0.05)
subprocess.Popen([sys.executable, __file__, hb, "child"])
time.sleep(60)
"""


def _heartbeat_stopped(path, wait=1.0) -> bool:
    import time

    time.sleep(wait)  # o'ldirilgan jarayon oxirgi yozuvni tugatsin
    a = path.stat().st_size if path.exists() else 0
    time.sleep(wait)
    b = path.stat().st_size if path.exists() else 0
    return a == b


def test_local_timeout_kills_whole_process_tree(tmp_path, monkeypatch):
    import sys

    from ges_sim.cfd import runner

    script = tmp_path / "solver.py"
    script.write_text(_CHILD, encoding="utf-8")
    hb = tmp_path / "hb.txt"
    monkeypatch.setattr(runner, "LOCAL_CMD", [sys.executable, str(script), str(hb)])
    import time

    t0 = time.time()
    with pytest.raises(runner.CfdError, match="vaqt chegarasidan"):
        runner.run_case(tmp_path, 100, mode="local", timeout_s=1, poll_s=0.2)
    assert time.time() - t0 < 30
    assert hb.exists() and _heartbeat_stopped(hb)  # nevara jarayon ham o'ldirilgan


def test_docker_timeout_kills_named_container(tmp_path, monkeypatch):
    import json
    import sys

    from ges_sim.cfd import runner

    calls = tmp_path / "calls.jsonl"
    fake = tmp_path / "fake_docker.py"
    fake.write_text(
        "import json, sys, time\n"
        f"open({str(calls)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
        "if sys.argv[1] == 'run':\n    time.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "DOCKER", [sys.executable, str(fake)])
    case = tmp_path / "case7"
    case.mkdir()
    with pytest.raises(runner.CfdError):
        runner.run_case(case, 100, mode="docker", timeout_s=1, poll_s=0.2, cpus=3, memory="4g", user="1000:1000")
    lines = [json.loads(x) for x in calls.read_text(encoding="utf-8").splitlines()]
    run = next(c for c in lines if c[0] == "run")
    name = run[run.index("--name") + 1]
    assert name.startswith("sath-cfd-case7-")
    assert run[run.index("--network") + 1] == "none" and run[run.index("--memory") + 1] == "4g"
    assert "--cpus=3.0" in run and run[run.index("--user") + 1] == "1000:1000"
    assert ["kill", name] in lines  # CLI emas — konteynerning o'zi to'xtatildi


def test_docker_command_defaults():
    from ges_sim.cfd import runner

    cmd = runner.docker_command(Path("/tmp/c"), "sath-cfd-x", image="img", cpus=2, memory="8g", user=None)
    assert "--user" not in cmd and cmd[cmd.index("--pids-limit") + 1] == "2048" and "no-new-privileges" in cmd


def test_spillway_is_turbulent_komega_sst(tmp_path):
    """SIM-07: suv tashlagich — laminar emas, RAS k-omega SST (prototip Re ~ 10^6), devor funksiyalari bilan."""
    case = build_case({"kind": "spillway", "crest_height_m": 3, "head_m": 1.2}, tmp_path)
    tp = (tmp_path / "constant/turbulenceProperties").read_text()
    assert "simulationType RAS;" in tp and "RASModel kOmegaSST;" in tp and "laminar" not in tp
    k, omega, nut = ((tmp_path / f"0/{n}").read_text() for n in ("k", "omega", "nut"))
    assert "kqRWallFunction" in k and "omegaWallFunction" in omega and "nutkWallFunction" in nut
    for text in (k, omega, nut):
        for patch in ("inlet", "outlet", "atmosphere", "bottom", "weir", "frontAndBack"):
            assert patch in text
    assert "dimensions [0 2 -2 0 0 0 0];" in k and "dimensions [0 0 -1 0 0 0 0];" in omega
    u_in = case.q / (3 + 1.2)
    k0 = 1.5 * (0.05 * u_in) ** 2
    assert f"uniform {k0:.6g};" in k
    fs = (tmp_path / "system/fvSchemes").read_text()
    assert "div(phi,k)" in fs and "div(phi,omega)" in fs and "wallDist { method meshWave; }" in fs
    sol = (tmp_path / "system/fvSolution").read_text()
    assert '"(U|k|omega)"' in sol and '"(U|k|omega)Final"' in sol
