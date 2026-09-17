"""Test muhiti: har sessiya uchun alohida SQLite + data papka (import dan OLDIN sozlanadi)."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="ges_test_"))
os.environ["GES_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GES_DATA_DIR"] = str(_TMP)
os.environ["GES_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
os.environ["GES_ADMIN_PASSWORD"] = "admin123"

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from ges_server.auth import security
from ges_server.db import Base, engine
from ges_server.main import app, init_db

# Testlarda parol xeshlash tez bo'lsin (xavfsizlik testda muhim emas)
security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin", "admin123")


def make_user(client, admin, username, password="pass1234", **kw) -> int:
    r = client.post(
        "/api/users", json={"username": username, "password": password, **kw}, headers=admin
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def users(client, admin):
    """Uchta rol uchun foydalanuvchi + loyiha; qaytaradi headers va idlar."""
    ids = {name: make_user(client, admin, name) for name in ("viewer", "engineer", "approver")}
    r = client.post("/api/projects", json={"name": "Test GES"}, headers=admin)
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    for name, uid in ids.items():
        r = client.put(
            f"/api/projects/{project_id}/members",
            json={"user_id": uid, "role": name},
            headers=admin,
        )
        assert r.status_code == 200, r.text
    outsider_id = make_user(client, admin, "outsider")
    return {
        "project_id": project_id,
        "ids": {**ids, "outsider": outsider_id},
        "admin": admin,
        "viewer": login(client, "viewer", "pass1234"),
        "engineer": login(client, "engineer", "pass1234"),
        "approver": login(client, "approver", "pass1234"),
        "outsider": login(client, "outsider", "pass1234"),
    }


def make_ifc(path: Path, wall_names=("Wall 1",), project_name="Test GES") -> Path:
    """Minimal IFC4 fayl: loyiha → site → storey → devorlar."""
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.project
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    f = ifcopenshell.api.project.create_file(version="IFC4")
    proj = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name=project_name)
    ifcopenshell.api.unit.assign_unit(f)
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Site")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="L0")
    ifcopenshell.api.aggregate.assign_object(f, relating_object=proj, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[storey])
    walls = [
        ifcopenshell.api.root.create_entity(f, ifc_class="IfcWall", name=n) for n in wall_names
    ]
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=walls)
    f.write(str(path))
    return path


@pytest.fixture
def ifc_file(tmp_path) -> Path:
    return make_ifc(tmp_path / "model.ifc")


def upload(client, headers, model_id, path: Path, message="", parent_id=None):
    data = {"message": message}
    if parent_id is not None:
        data["parent_id"] = str(parent_id)
    with open(path, "rb") as fh:
        return client.post(
            f"/api/models/{model_id}/versions",
            files={"file": (path.name, fh, "application/octet-stream")},
            data=data,
            headers=headers,
        )
