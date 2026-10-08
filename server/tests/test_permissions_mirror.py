"""Desktop rol zaxirasi (common/sath_common/permissions.py) — server ROLE_PERMISSIONS ning aniq ko'zgusi (P3).
Server ruxsatlari o'zgarsa test yiqiladi: ko'zguni yangilang va `python desktop/build/sync_blender.py`."""

import importlib.util
from pathlib import Path

import pytest
from ges_server.auth.deps import ROLE_PERMISSIONS, role_permissions
from ges_server.orm import Role

MIRROR = Path(__file__).resolve().parents[2] / "common" / "sath_common" / "permissions.py"


@pytest.fixture(scope="module")
def mirror():
    if not MIRROR.is_file():
        pytest.skip("common/sath_common yo'q (faqat server obrazi)")
    spec = importlib.util.spec_from_file_location("sath_common_permissions", MIRROR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mirror_equals_server_role_permissions(mirror):
    assert {r.value: set(p) for r, p in ROLE_PERMISSIONS.items()} == {k: set(v) for k, v in mirror.ROLE_PERMISSIONS.items()}


def test_every_role_mirrored_and_lookup_matches(mirror):
    assert {r.value for r in Role} == set(mirror.ROLE_PERMISSIONS)
    for r in Role:
        assert mirror.role_permissions(r.value) == role_permissions(r)
    assert mirror.role_permissions(None) == frozenset() == role_permissions(None)
    assert mirror.role_permissions("yoq") == frozenset()
    assert mirror.ALL == frozenset().union(*ROLE_PERMISSIONS.values())
