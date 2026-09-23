"""SRV-04: parallel fragments konvertatsiyasi — har biri noyob temp fayl, atomik os.replace, qoldiq yo'q;
kalit qulflari chegaralangan (LRU)."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from ges_server.models import fragments
from ges_server.models.keylocks import KeyLocks


def test_parallel_convert_unique_temp_and_atomic(monkeypatch, tmp_path):
    sha = "ab" * 32
    ifc = tmp_path / "m.ifc"
    ifc.write_text("ISO-10303-21;")
    seen: list[str] = []
    barrier = threading.Barrier(2, timeout=10)

    def fake_run(cmd, cwd, timeout_s, ro_paths):
        out = Path(cmd[-1])
        seen.append(out.name)
        barrier.wait()  # ikkalasi bir vaqtda yozadi
        out.write_bytes(b"FRAG" * 100 + out.name.encode())
        time.sleep(0.05)
        return SimpleNamespace(returncode=0, stdout=b'{"ms": 1}\n', stderr=b"")

    monkeypatch.setattr(fragments.sandbox, "run", fake_run)
    monkeypatch.setattr(fragments, "tool_path", lambda: tmp_path / "tool.mjs")
    monkeypatch.setattr(fragments.shutil, "which", lambda _: "node")
    out = fragments.frag_path(sha)
    out.unlink(missing_ok=True)
    res = []
    # qulfni chetlab o'tamiz — ikki jarayon (replika) holati
    ts = [threading.Thread(target=lambda: res.append(fragments._convert_locked(ifc, sha, out, 60))) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(set(seen)) == 2 and all(n.startswith(sha) and n.endswith(".frag.part") for n in seen)
    assert res == [out, out] and out.exists() and out.read_bytes().startswith(b"FRAG")
    assert not list(out.parent.glob(f"{sha}*.part"))
    out.unlink()


def test_failed_convert_leaves_no_temp(monkeypatch, tmp_path):
    sha = "cd" * 32
    monkeypatch.setattr(fragments.sandbox, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"xato"))
    monkeypatch.setattr(fragments, "tool_path", lambda: tmp_path / "tool.mjs")
    monkeypatch.setattr(fragments.shutil, "which", lambda _: "node")
    out = fragments.frag_path(sha)
    assert fragments.convert(tmp_path / "x.ifc", sha) is None
    assert not out.exists() and not list(out.parent.glob(f"{sha}*.part"))


def test_keylocks_bounded_and_held_lock_kept():
    kl = KeyLocks(maxsize=4)
    held = kl.get("held")
    held.acquire()
    try:
        for i in range(50):
            kl.get(f"k{i}")
        assert len(kl) <= 5
        assert kl.get("held") is held  # ushlab turilgan qulf chiqarilmaydi
    finally:
        held.release()
