"""core.perms (P3, rolga sezgir UI): server ruxsatlari, eski server uchun rol zaxirasi, faol loyiha, so'rab olish."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import session  # noqa: E402
from sath.core import perms  # noqa: E402
from sath.core.tasks import TASKS  # noqa: E402


def _ctx(rows=(), project_id=0, index=-1):
    projects = [NS(item_id=i, state=role, perms=p) for i, role, p in rows]
    return NS(scene=NS(ges=NS(projects=projects, projects_index=index, project_id=project_id)))


class FakeClient:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def project(self, pid):
        self.calls.append(pid)
        if self.exc:
            raise self.exc
        return self.reply


@pytest.fixture
def logged_in(monkeypatch):
    def login(client=None):
        client = client or FakeClient({})
        monkeypatch.setattr(session, "_client", client)
        return client

    perms.clear()
    monkeypatch.setattr(TASKS, "inline", True)
    yield login
    perms.clear()


def test_resolve_prefers_server_list_and_falls_back_to_role():
    assert perms.resolve("viewer", ["model.write"]) == {"model.write"}
    assert perms.resolve("viewer", None) == {"project.read", "scada.read"}
    assert "cr.merge" in perms.resolve("approver", None)
    assert perms.resolve(None, None) == frozenset() == perms.resolve("yoq", None)


def test_logged_out_has_nothing():
    perms.clear()
    ctx = _ctx([(1, "approver", "")], project_id=1)
    assert not perms.can("model.write", ctx) and perms.role(ctx) == ""


def test_server_permissions_and_old_server_fallback(logged_in):
    logged_in()
    new = _ctx([(1, "viewer", "project.read scada.read")], project_id=1)
    assert perms.can("scada.read", new) and not perms.can("sim.run", new)
    old = _ctx([(1, "engineer", "")], project_id=1)  # eski server: permissions maydoni yo'q
    assert perms.can("sim.run", old) and perms.can("model.write", old) and not perms.can("cr.approve", old)
    assert perms.role(old) == "engineer"
    assert perms.any_of(["cr.merge", "sim.run"], old) and not perms.any_of(["cr.merge"], old)


def test_active_project_open_model_else_selected_row(logged_in):
    logged_in()
    ctx = _ctx([(1, "viewer", ""), (2, "approver", "")], project_id=0, index=1)
    assert perms.active_project_id(ctx.scene.ges) == 2 and perms.can("cr.merge", ctx)
    ctx.scene.ges.project_id = 1  # ochiq model loyihasi ustun
    assert not perms.can("cr.merge", ctx)
    assert perms.can("cr.merge", ctx, project_id=2)  # aniq loyiha (yangi model yaratish)


def test_missing_row_is_fetched_once(logged_in):
    c = logged_in(FakeClient({"my_role": "engineer", "permissions": ["model.write", "project.read"]}))
    ctx = _ctx([], project_id=42)
    assert perms.can("model.write", ctx) and not perms.can("sim.run", ctx)
    assert perms.role(ctx) == "engineer" and c.calls == [42]


def test_fetch_error_means_no_permissions(logged_in):
    c = logged_in(FakeClient(exc=RuntimeError("403")))
    ctx = _ctx([], project_id=7)
    assert not perms.can("project.read", ctx) and not perms.can("project.read", ctx)
    assert c.calls == [7]


def test_require_and_poll_reason(logged_in):
    logged_in()
    msgs = []
    cls = NS(poll_message_set=msgs.append)
    viewer = _ctx([(1, "viewer", "")], project_id=1)
    assert not perms.poll(cls, "sim.run", viewer)
    assert not perms.poll(cls, "sim.run", _ctx())
    assert msgs == ["Ruxsat yo'q: sim.run", "Avval loyihani tanlang"]
    assert perms.poll(cls, "sim.run", _ctx([(1, "engineer", "")], project_id=1)) and len(msgs) == 2
    with pytest.raises(PermissionError, match="sim.run"):
        perms.require("sim.run", viewer)
