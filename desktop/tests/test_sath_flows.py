"""sath.flows — real server bilan (uvicorn alohida oqim), bpy siz."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
sys.path.insert(0, str(ROOT / "server" / "tests"))

_TMP = Path(tempfile.mkdtemp(prefix="sath_flows_"))
os.environ["GES_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GES_DATA_DIR"] = str(_TMP)
os.environ["GES_SECRET_KEY"] = "desktop-test-secret-key-at-least-32-bytes"
os.environ["GES_ADMIN_PASSWORD"] = "admin123"

import uvicorn  # noqa: E402
from conftest import make_ifc  # noqa: E402
from ges_server.main import app  # noqa: E402
from sath import flows  # noqa: E402
from sath.shared.server_client import GesClient, ServerError  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    c = GesClient(f"http://127.0.0.1:{port}")
    for _ in range(100):
        try:
            c.health()
            break
        except ServerError:
            time.sleep(0.1)
    c.login("admin", "admin123")
    yield c
    server.should_exit = True
    t.join(timeout=5)


def test_rows_and_commit_roundtrip(client, tmp_path):
    client._json("POST", "/api/projects", {"name": "Flows GES"})
    projects = flows.project_rows(client)
    assert projects and projects[0]["name"]
    pid = next(p["item_id"] for p in projects if p["name"] == "Flows GES")
    m = client.create_model(pid, "flows-test")
    ifc_path = tmp_path / "a.ifc"
    make_ifc(ifc_path)
    r = flows.commit(client, m["id"], ifc_path, "birinchi", None, submit=True)
    assert r["version"]["number"] == 1 and r["cr"] is not None
    rows = flows.version_rows(client, m["id"])
    assert rows[0]["number"] == 1 and rows[0]["item_id"] == r["version"]["id"]
    assert rows[0]["col2"] == "birinchi"
    dest = flows.download_version(client, {"id": m["id"]}, r["version"])
    assert dest.exists() and dest.name == f"m{m['id']}_v1.ifc"
    assert flows.model_rows(client, pid)[0]["name"] == "flows-test"
    assert flows.model_role(client, m["id"]) in ("viewer", "engineer", "approver", None)


def test_check_update_web_url_notifications(client):
    assert flows.check_update(client, "999.0.0") is None
    assert flows.web_url(client, client.base_url, "/models/1").startswith("http://127.0.0.1")
    assert isinstance(flows.notification_rows(client), list)
    assert flows.unread_summary(client) is None or isinstance(flows.unread_summary(client), str)
