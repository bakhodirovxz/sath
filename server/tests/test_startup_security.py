"""CODE-08: muhitdagi zaif admin paroli va default Postgres paroli — ishlab chiqarish rejimida (GES_DEV_MODE=false)."""

import pytest
from conftest import login


def test_weak_env_admin_password_forces_change(client, monkeypatch):
    from ges_server import config, main

    s = config.get_settings()
    assert s.admin_password == "admin123" and s.dev_mode  # conftest: sinov rejimi
    assert main.admin_password_problems()  # admin123 — bloklash ro'yxatida
    r = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.json()["must_change_password"] is False  # dev rejimida faqat ogohlantirish
    monkeypatch.setattr(s, "dev_mode", False)
    assert any("SHART" in w for w in main.startup_warnings())
    main.init_db()  # qayta start: mavjud admin muhitdagi zaif parol bilan — almashtirish majburiy
    h = login(client, "admin", "admin123")
    r = client.get("/api/projects", headers=h)
    assert r.status_code == 403 and r.headers.get("X-Password-Change-Required") == "1"


def test_strong_env_admin_password_not_forced(monkeypatch):
    from ges_server import config, main

    s = config.get_settings()
    monkeypatch.setattr(s, "admin_password", "Kuchli-Parol-2026!")
    monkeypatch.setattr(s, "dev_mode", False)
    assert main.admin_password_problems() == []


@pytest.mark.parametrize(
    ("url", "bad"),
    [
        ("postgresql+psycopg://ges:ges@postgres:5432/ges", True),
        ("postgresql+psycopg://ges:@postgres:5432/ges", True),
        ("postgresql+psycopg://ges:postgres@db/ges", True),
        ("postgresql+psycopg://ges:x9Qv2LmRt7@postgres:5432/ges", False),
        ("sqlite:////data/ges.db", False),
    ],
)
def test_default_db_password_detected(monkeypatch, url, bad):
    from ges_server import config, main

    monkeypatch.setattr(config.get_settings(), "database_url", url)
    assert bool(main.production_problems()) is bad


def test_server_refuses_default_db_password_in_production(monkeypatch):
    from fastapi.testclient import TestClient
    from ges_server import config
    from ges_server.main import create_app

    s = config.get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql+psycopg://ges:ges@postgres:5432/ges")
    monkeypatch.setattr(s, "dev_mode", False)
    with pytest.raises(RuntimeError, match="Postgres paroli"), TestClient(create_app()):
        pass


def test_compose_requires_postgres_password():
    from pathlib import Path

    deploy = Path(__file__).resolve().parents[2] / "deploy"
    for name in ("docker-compose.yml", "docker-compose.ha.yml"):
        text = (deploy / name).read_text(encoding="utf-8")
        assert "POSTGRES_PASSWORD:-" not in text and "POSTGRES_PASSWORD:?" in text, name
        assert "PG_REPL_PASSWORD:-" not in text


def test_sqlite_warning_in_server_mode(monkeypatch):
    """SRV-08: SQLite ishlab chiqarish (dev_mode=false) rejimida startda ogohlantirish; Postgres da yo'q."""
    from ges_server import config, main

    s = config.get_settings()
    monkeypatch.setattr(s, "dev_mode", False)
    monkeypatch.setattr(s, "database_url", "sqlite:////data/ges.db")
    assert any("SQLite" in w for w in main.startup_warnings())
    monkeypatch.setattr(s, "role", "api")
    assert any("GES_ROLE=api" in w for w in main.startup_warnings())
    monkeypatch.setattr(s, "database_url", "postgresql+psycopg://ges:Kuchli-2026@db/ges")
    assert not any("SQLite" in w for w in main.startup_warnings())
    monkeypatch.setattr(s, "database_url", "sqlite:////tmp/x.db")
    monkeypatch.setattr(s, "dev_mode", True)
    assert not any("SQLite" in w for w in main.startup_warnings())
