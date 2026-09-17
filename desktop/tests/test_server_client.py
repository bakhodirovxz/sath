"""server_client ni haqiqiy server (uvicorn, alohida oqim) bilan sinaydi — FreeCAD kerak emas."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "GesWorkbench"))
sys.path.insert(0, str(ROOT / "server" / "tests"))

_TMP = Path(tempfile.mkdtemp(prefix="ges_desktop_"))
os.environ["GES_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GES_DATA_DIR"] = str(_TMP)
os.environ["GES_SECRET_KEY"] = "desktop-test-secret-key-at-least-32-bytes"
os.environ["GES_ADMIN_PASSWORD"] = "admin123"

import uvicorn  # noqa: E402
from conftest import make_ifc  # noqa: E402  (server/tests/conftest.py)
from ges_server.main import app  # noqa: E402
from ges_workbench.server_client import GesClient, ServerError  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            GesClient(url).health()
            break
        except ServerError:
            time.sleep(0.1)
    yield url
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="module")
def admin(base_url):
    c = GesClient(base_url)
    c.login("admin", "admin123")
    return c


def test_login_and_me(base_url):
    c = GesClient(base_url)
    with pytest.raises(ServerError) as e:
        c.login("admin", "wrong")
    assert e.value.status == 401
    c.login("admin", "admin123")
    assert c.me()["username"] == "admin"


def test_unreachable_server():
    with pytest.raises(ServerError) as e:
        GesClient("http://127.0.0.1:1", timeout=2).health()
    assert e.value.status == 0


def test_full_desktop_flow(admin, tmp_path):
    # Loyiha (admin API orqali — klientda loyiha yaratish yo'q, bu web/admin ishi)
    project = admin._json("POST", "/api/projects", {"name": "Desktop GES"})
    models = admin.models(project["id"])
    assert models == []
    model = admin.create_model(project["id"], "To'g'on")

    # Commit
    ifc = make_ifc(tmp_path / "dam.ifc", wall_names=("A",))
    v1 = admin.upload_version(model["id"], ifc, message="birinchi")
    assert v1["number"] == 1 and v1["message"] == "birinchi"
    v2 = admin.upload_version(
        model["id"], make_ifc(tmp_path / "dam2.ifc", ("A", "B")), "ikkinchi", parent_id=v1["id"]
    )
    assert v2["parent_id"] == v1["id"]
    assert [v["number"] for v in admin.versions(model["id"])] == [2, 1]

    # Yuklab olish — bayt-ba-bayt bir xil
    dest = admin.download_version(v1["id"], tmp_path / "dl" / "v1.ifc")
    assert dest.read_bytes() == ifc.read_bytes()

    # Tasdiqqa yuborish, issue
    cr = admin.create_change_request(model["id"], v2["id"], "Tasdiqlang")
    assert cr["status"] == "open"
    assert admin.change_requests(model["id"])[0]["id"] == cr["id"]
    issue = admin.create_issue(
        model["id"],
        "Devor",
        version_id=v2["id"],
        viewpoint={"camera": {"position": [1, 2, 3], "target": [0, 0, 0]}},
    )
    admin.comment_issue(issue["id"], "ko'rdim")
    assert admin.issue(issue["id"])["comment_count"] == 1
    assert len(admin.issues(model["id"])) == 1


def test_error_detail_passthrough(admin):
    with pytest.raises(ServerError) as e:
        admin.version(99999)
    assert e.value.status == 404
    assert "topilmadi" in e.value.message
