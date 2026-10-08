"""core.events: obuna, e'lon, obunani bekor qilish, bitta obunachi xatosi boshqalarni to'xtatmaydi."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import events  # noqa: E402


def test_publish_subscribe_unsubscribe():
    events.clear()
    got = []
    off = events.subscribe("ifc.loaded", lambda p: got.append(p))
    events.publish("ifc.loaded", path="a.ifc")
    off()
    events.publish("ifc.loaded", path="b.ifc")
    assert got == [{"path": "a.ifc"}]


def test_failing_subscriber_does_not_block_others(capsys):
    events.clear()
    got = []
    events.subscribe("session.login", lambda p: 1 / 0)
    events.subscribe("session.login", lambda p: got.append(p["user"]))
    events.publish("session.login", user="admin")
    assert got == ["admin"]
    assert "session.login" in capsys.readouterr().out
