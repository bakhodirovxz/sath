"""FreeCAD workbench CAD importi (desktop/tests/fc_cad.py) — FreeCAD Python muhiti bo'lsa ishga tushadi."""

import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("GES_FC_HOME") or Path.home() / "Tools" / "fc-py313")
PY = HOME / ("python.exe" if os.name == "nt" else "bin/python")


@pytest.mark.skipif(not PY.is_file(), reason="FreeCAD Python muhiti yo'q (GES_FC_HOME)")
def test_freecad_cad_checks():
    r = subprocess.run(
        [str(PY), str(HERE / "fc_cad.py")], capture_output=True, text=True, timeout=600,
        env={**os.environ, "GES_FC_HOME": str(HOME)},
    )  # fmt: skip
    assert "[OK] fc_cad" in r.stdout, r.stdout[-3000:] + r.stderr[-3000:]
