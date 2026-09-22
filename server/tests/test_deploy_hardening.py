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


def test_dem_channel_can_be_disabled_or_mirrored(monkeypatch, tmp_path):
    """L7 (C5 kanali): DEM tashqi manbasi o'chirilishi yoki ichki ko'zguga yo'naltirilishi mumkin."""
    from ges_server.config import get_settings
    from ges_server.models import dem

    s = get_settings()
    monkeypatch.setattr(s, "data_dir", tmp_path)
    monkeypatch.setattr(s, "dem_enabled", False)
    with pytest.raises(ValueError, match="o'chirilgan"):
        dem._tile(12, 1, 1)
    monkeypatch.setattr(s, "dem_enabled", True)
    monkeypatch.setattr(s, "dem_tile_url", "http://127.0.0.1:9/kozgu/{z}/{x}/{y}.png")
    seen = {}

    def fake_urlopen(req, timeout=60):
        seen["url"] = req.full_url
        raise OSError("ko'zgu yo'q (sinov)")

    monkeypatch.setattr(dem.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OSError):
        dem._tile(12, 3, 4)
    assert seen["url"] == "http://127.0.0.1:9/kozgu/12/3/4.png"


def test_ha_compose_override_and_caddy():
    ha = (DEPLOY / "docker-compose.ha.yml").read_text(encoding="utf-8")
    assert "GES_ROLE: api" in ha and "GES_ROLE: worker" in ha and "replicas: 2" in ha and "/api/ready" in ha
    caddy = (DEPLOY / "Caddyfile.ha").read_text(encoding="utf-8")
    assert "dynamic a" in caddy and "health_uri /api/ready" in caddy
    assert "/api/ready" in (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
