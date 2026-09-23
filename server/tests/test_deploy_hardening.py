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


def _compose(name: str = "docker-compose.yml") -> dict:
    import yaml

    class _Loader(yaml.SafeLoader):
        pass

    # compose teglari (!reset, !override) — qiymatning o'zi
    _Loader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else loader.construct_scalar(node))
    return yaml.load((DEPLOY / name).read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506


def test_cfd_worker_shares_server_db_and_sees_only_cases():
    """CFD worker server bilan bir DB (Postgres) ga ulanadi; /data to'liq (secret.key, ges.db) mount qilinmaydi,
    .env (sirlar) berilmaydi — faqat cfd_data hajmi (SEC-01, yangi xato: worker boshqa SQLite ga ulanardi)."""
    c = _compose()
    cfd, ges = c["services"]["cfd"], c["services"]["ges"]
    assert cfd["environment"]["GES_DATABASE_URL"] == ges["environment"]["GES_DATABASE_URL"]
    assert "env_file" not in cfd
    assert str(cfd["environment"]["GES_SECRET_KEY_REQUIRED"]).lower() == "false"
    assert cfd["volumes"] == ["cfd_data:/data/cfd"]
    assert not any(str(v).split(":")[1] == "/data" for v in cfd["volumes"])
    assert "cfd_data:/data/cfd" in ges["volumes"] and "cfd_data" in c["volumes"]
    ha = _compose("docker-compose.ha.yml")
    assert "cfd_data:/data/cfd" in ha["services"]["ges-worker"]["volumes"]
    dockerfile = (DEPLOY / "Dockerfile.cfd").read_text(encoding="utf-8")
    assert "GES_DATABASE_URL=sqlite" not in dockerfile and "GES_SECRET_KEY_REQUIRED=false" in dockerfile


def test_cfd_worker_refuses_invisible_sqlite(tmp_path):
    from ges_server.sim.worker import check_database_url

    assert check_database_url("sqlite:////data/ges.db") is not None  # konteynerda server bazasi ko'rinmaydi
    db = tmp_path / "ges.db"
    db.write_bytes(b"")
    assert check_database_url(f"sqlite:///{db.as_posix()}") is None  # lokal dev: umumiy fayl
    assert check_database_url("postgresql+psycopg://ges:x@postgres:5432/ges") is None


def test_secret_key_not_required_for_worker(monkeypatch, tmp_path):
    from ges_server import config

    monkeypatch.delenv("GES_SECRET_KEY", raising=False)
    monkeypatch.setenv("GES_SECRET_KEY_REQUIRED", "false")
    monkeypatch.setenv("GES_DATA_DIR", str(tmp_path))
    s = config.load_settings()
    assert s.secret_key == "" and not (tmp_path / "secret.key").exists()


def test_solver_env_drops_secrets():
    from ges_sim.cfd.runner import solver_env

    env = solver_env(
        {
            "PATH": "/usr/bin",
            "WM_PROJECT_DIR": "/openfoam",
            "FOAM_RUN": "/work",
            "LD_LIBRARY_PATH": "/lib",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
            "GES_DATABASE_URL": "postgresql://ges:parol@db/ges",
            "GES_SECRET_KEY": "k",
            "POSTGRES_PASSWORD": "p",
            "PGPASSWORD": "p",
            "AWS_SECRET_ACCESS_KEY": "s",
            "GITHUB_TOKEN": "t",
            "API_KEY": "a",
            "DATABASE_URL": "x",
        }
    )
    assert set(env) == {"PATH", "WM_PROJECT_DIR", "FOAM_RUN", "LD_LIBRARY_PATH", "DOCKER_HOST"}


def test_compose_project_name_matches_backup_volumes():
    """SEC-02: compose loyiha nomi qat'iy `sath` — hajm sath_ges_data (backup.sh/restore.sh kutgan nom)."""
    assert _compose()["name"] == "sath"
    assert _compose("docker-compose.ha.yml")["name"] == "sath"
    for script in ("backup.sh", "restore.sh"):
        text = (DEPLOY / script).read_text(encoding="utf-8")
        assert 'PROJECT="${COMPOSE_PROJECT:-sath}"' in text and 'VOL="${PROJECT}_ges_data"' in text
        assert 'docker volume inspect "$VOL"' in text
    backup = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
    assert "pragma integrity_check" in backup and "getsize(src) == 0" in backup
    assert '[ -s "$work/db.pgdump" ]' in backup


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yo'q")
def test_backup_fails_loudly_when_volume_missing(tmp_path):
    """SEC-02: hajm topilmasa backup.sh bo'sh arxiv yozmaydi — exit 3 va tushunarli xabar."""
    fake = tmp_path / "bin"
    fake.mkdir()
    calls = tmp_path / "calls.txt"
    (fake / "docker").write_text(
        f'#!/bin/sh\necho "$*" >> "{calls.as_posix()}"\n[ "$1" = volume ] && exit 1\nexit 0\n', encoding="utf-8"
    )
    (fake / "docker").chmod(0o755)
    import os

    env = {**os.environ, "PATH": f"{fake.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}", "BACKUP_DIR": str(tmp_path / "out")}
    r = subprocess.run(["sh", str(DEPLOY / "backup.sh"), "--no-encrypt"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "sath_ges_data" in r.stderr and "topilmadi" in r.stderr
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
    assert "run" not in calls.read_text(encoding="utf-8")  # hech qanday konteyner ishga tushmadi


def test_bind_default_loopback_and_caddy_csp_same_host():
    """OPS-01: 8000 port default faqat 127.0.0.1 (tashqariga — Caddy HTTPS); Caddy CSP ws/wss faqat shu host."""
    ports = _compose()["services"]["ges"]["ports"]
    assert ports == ["${GES_BIND:-127.0.0.1}:${GES_PORT:-8000}:8000"]
    env = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    assert "\nGES_BIND=127.0.0.1" in env
    for name in ("Caddyfile", "Caddyfile.ha"):
        caddy = (DEPLOY / name).read_text(encoding="utf-8")
        assert "connect-src 'self' wss://{host} blob: data:;" in caddy and " ws: " not in caddy


def test_all_services_drop_caps_and_no_new_privileges():
    """OPS-02: har servis cap_drop ALL + no-new-privileges; kerakli qobiliyatlar faqat aniq cap_add bilan;
    ildiz FS faqat o'qish — ges, cfd, caddy, simulyator (postgres entrypoint i yozadi — istisno)."""
    for fname in ("docker-compose.yml", "docker-compose.ha.yml"):
        for name, svc in _compose(fname)["services"].items():
            if fname.endswith("ha.yml") and name in ("ges", "caddy"):
                continue  # asosiy compose ustiga qo'shimcha (merge) — kalitlar asosiy faylda
            assert svc.get("cap_drop") == ["ALL"], (fname, name)
            assert "no-new-privileges:true" in svc.get("security_opt", []), (fname, name)
            assert set(svc.get("cap_add", [])) <= {"CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID", "NET_BIND_SERVICE"}
    c = _compose()["services"]
    for name in ("ges", "cfd", "caddy", "simulator", "sim-gateway"):
        assert c[name].get("read_only") is True, name
    assert c["caddy"]["cap_add"] == ["NET_BIND_SERVICE"]
    sim = (DEPLOY / "simulator" / "Dockerfile").read_text(encoding="utf-8")
    assert [ln.strip() for ln in sim.splitlines() if ln.startswith("USER ")][-1] == "USER sath"


def test_config_env_file_location_and_cfd_default(monkeypatch, tmp_path):
    """CODE-06: .env — GES_ENV_FILE yoki barqaror server/.env (CWD ga bog'liq emas); cfd_mode default = worker
    (deploy/.env.example bilan bir xil)."""
    from ges_server import config

    assert config.Settings.model_fields["cfd_mode"].default == "worker"
    assert "GES_CFD_MODE=worker" in (DEPLOY / ".env.example").read_text(encoding="utf-8")
    env = tmp_path / "sath.env"
    env.write_text("GES_APP_NAME=Sath-sinov\nGES_CFD_MODE=off\n", encoding="utf-8")
    monkeypatch.setenv("GES_ENV_FILE", str(env))
    monkeypatch.delenv("GES_CFD_MODE", raising=False)
    s = config.load_settings()
    assert s.app_name == "Sath-sinov" and s.cfd_mode == "off"
    assert config.env_files() == (env,)
    monkeypatch.delenv("GES_ENV_FILE")
    other = tmp_path / "boshqa"
    other.mkdir()
    monkeypatch.chdir(other)
    assert config.env_files()[0] == config.SERVER_ENV_FILE  # barqaror joy birinchi
    assert config.legacy_cwd_env() is None
    (other / ".env").write_text("GES_APP_NAME=cwd\n", encoding="utf-8")
    assert config.legacy_cwd_env() == other / ".env"  # eski joy — ishlaydi, lekin ogohlantiriladi


def _run_block(dockerfile: str, marker: str) -> str:
    """Dockerfile dagi `marker` li birinchi RUN buyrug'i (satr davomlari birlashtirilgan, `RUN ` siz)."""
    blocks, cur = [], None
    for ln in dockerfile.splitlines():
        if cur is None and ln.startswith("RUN "):
            cur = []
        if cur is not None:
            cur.append(ln.rstrip().removesuffix("\\"))
            if not ln.rstrip().endswith("\\"):
                blocks.append(" ".join(cur)[4:])
                cur = None
    return next(b for b in blocks if marker in b)


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yo'q")
def test_dwg_build_arg_fails_loudly():
    """CAD-10: WITH_DWG=1 (default) da LibreDWG o'rnatilmasa build to'xtaydi (`|| true` yo'q); sintaksis to'g'ri."""
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    import re

    assert text.count("ARG WITH_DWG=1") == 2  # dwg bosqichi va runtime
    assert re.search(r"^ARG LIBREDWG_SHA256=[0-9a-f]{64}$", text, re.M)
    build = _run_block(text, "LIBREDWG_VERSION")  # Debian da paket yo'q — GNU manbadan, sha256 bilan
    assert "sha256sum -c -" in build and "ftp.gnu.org/gnu/libredwg" in build and "|| true" not in build
    runtime = _run_block(text, "ln -s /opt/libredwg/bin/dwg2dxf")
    assert "exit 1" in runtime and "|| true" not in runtime
    for cmd in (build, runtime):
        r = subprocess.run(["sh", "-n", "-c", cmd], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
    assert "GPLv3" in (DEPLOY / "README.md").read_text(encoding="utf-8")


def test_health_reports_dwg(client, monkeypatch):
    from ges_server import main
    from ges_server.models import mesh_import

    monkeypatch.setattr(main, "_DWG", {})
    monkeypatch.setattr(mesh_import, "tools", lambda: {"dwg2dxf": None, "oda": None, "assimp": None, "blender": None})
    assert client.get("/api/health").json()["dwg"] is False
    main._DWG.clear()
    monkeypatch.setattr(mesh_import, "tools", lambda: {"dwg2dxf": "/usr/bin/dwg2dxf", "oda": None})
    assert client.get("/api/health").json()["dwg"] is True


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yo'q")
def test_blender_is_official_pinned_tarball():
    """CAD-08: WITH_BLENDER=1 — apt dagi eski blender emas, rasmiy 5.2.x tarball, sha256 tekshiruvi bilan."""
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert "install -y --no-install-recommends blender" not in text
    import re

    ver = re.search(r"^ARG BLENDER_VERSION=(\d+)\.(\d+)\.(\d+)$", text, re.M)
    sha = re.search(r"^ARG BLENDER_SHA256=([0-9a-f]{64})$", text, re.M)
    assert ver and (int(ver[1]), int(ver[2])) >= (5, 2) and sha
    cmd = _run_block(text, "BLENDER_SHA256")
    assert "sha256sum -c -" in cmd and "download.blender.org" in cmd
    r = subprocess.run(["sh", "-n", "-c", cmd], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
