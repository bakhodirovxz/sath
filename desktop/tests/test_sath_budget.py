"""core/budget.py — spec §5 byudjetlari (P4) va dangasa og'ir importlar."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import budget  # noqa: E402


def test_register_line_lists_core_parts_and_modules():
    line = budget.register_line(10.0, {"ui_tasks": 0.5, "host": 20.0}, {"review": 3.0, "bim": 7.3})
    assert line == (
        "[sath] register 30.5 ms (byudjet < 150): import 10.0, ui_tasks 0.5, host 20.0"
        " [modullar: review 3.0, bim 7.3]"
    )
    assert line.isascii()  # Windows konsoli/pipe kodirovkasidan qat'i nazar
    assert "BYUDJET OSHDI" in budget.register_line(100.0, {"host": 60.0}, {})


def test_heavy_loaded_uses_top_level_names():
    names = ["numpy.core", "numpy", "ezdxf.math", "json", "sath.shared.geom", "assimp_py"]
    assert budget.heavy_loaded(names) == ["assimp_py", "ezdxf", "numpy"]


def test_check_reports_each_violation():
    assert budget.check(register_ms=40.0, cold_ratio=1.05, rss_delta_mb=12.0, heavy=[]) == []
    bad = budget.check(register_ms=150.0, cold_ratio=1.3, rss_delta_mb=60.0, heavy=["numpy"])
    assert len(bad) == 4
    assert len(budget.check(register_ms=None, cold_ratio=None, rss_delta_mb=None, heavy=[])) == 3
    assert budget.check_bundle(budget.BUNDLE_MAX_MB, False) == []
    assert len(budget.check_bundle(budget.BUNDLE_MAX_MB + 1, True)) == 2
    assert len(budget.check_bundle(None, False)) == 1


def test_ges_kinds_imports_without_numpy():
    """Blender register da ges_objects → ges_kinds import qilinadi: geom (numpy) birinchi qurishgacha yuklanmaydi."""
    code = (
        "import sys; sys.modules['numpy'] = None; sys.path.insert(0, 'common');"
        "from sath_common import ges_kinds;"
        "assert ges_kinds.KINDS and ges_kinds.geometric_params('GES_Dam');"
        "assert 'sath_common.geom' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)
