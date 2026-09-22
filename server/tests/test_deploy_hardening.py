"""L5/L6: deploy fayllari — konteyner qattiqlashtirish kalitlari, root siz obraz, zaxira/tiklash skriptlari sintaksisi."""

import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def test_dockerfiles_run_as_non_root():
    for name in ("Dockerfile", "Dockerfile.cfd"):
        text = (DEPLOY / name).read_text(encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("USER ")]
        assert lines and lines[-1] == "USER sath", f"{name}: oxirgi USER sath bo'lishi kerak"
    assert "bubblewrap" in (DEPLOY / "Dockerfile").read_text(encoding="utf-8")


def test_compose_hardening_keys():
    text = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    ges = text.split("  ges:")[1].split("\n  postgres:")[0]
    for key in ("cap_drop: [ALL]", "no-new-privileges:true", "read_only: true", "pids_limit:", "mem_limit:"):
        assert key in ges, key
    cfd = text.split("  cfd:")[1].split("\n  #")[0]
    assert "cap_drop: [ALL]" in cfd and "no-new-privileges:true" in cfd


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yo'q")
def test_backup_restore_scripts_syntax():
    for name in ("backup.sh", "restore.sh"):
        p = DEPLOY / name
        assert p.read_text(encoding="utf-8").startswith("#!/usr/bin/env sh")
        r = subprocess.run(["sh", "-n", str(p)], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
    assert "restore.sh --test" in (DEPLOY / "backup.cron.example").read_text(encoding="utf-8")
