"""core.registry (P3): manifest, API oralig'i, topologik tartib, imzo, hayot sikli (soxta bpy bilan)."""

import base64
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
sys.path.insert(0, str(ROOT / "desktop" / "build"))

import sign_module  # noqa: E402
from sath.core import registry  # noqa: E402
from sath.core.registry import Manifest, ManifestError, Registry  # noqa: E402

SEED = bytes(range(32))
TOML = """id = "{id}"
name = "{id} moduli"
version = "1.0.0"
api = "{api}"
requires = {requires}
permissions = ["network"]
visible_if_any = ["sim.run"]
workspaces = ["Simulation"]
category = "Sath"
order = {order}
"""


def _write(root: Path, mid: str, *, api=">=1.0,<2", requires=(), order=100) -> Path:
    d = root / mid
    d.mkdir(parents=True)
    reqs = "[" + ", ".join(f'"{r}"' for r in requires) + "]"
    (d / registry.MANIFEST).write_text(TOML.format(id=mid, api=api, requires=reqs, order=order), encoding="utf-8")
    (d / "__init__.py").write_text("def register(api):\n    pass\n", encoding="utf-8")
    return d


def _m(mid, requires=(), order=100, origin="bundled", api=">=1.0,<2"):
    return Manifest(id=mid, name=mid, version="1.0.0", api=api, path=Path(mid), origin=origin, requires=tuple(requires), order=order)


# ---------- manifest ----------


def test_parse_manifest_fields(tmp_path):
    d = _write(tmp_path, "sim", requires=["bim"], order=30)
    m = registry.parse_manifest((d / registry.MANIFEST).read_text(encoding="utf-8"), d)
    assert (m.id, m.version, m.requires, m.permissions, m.visible_if_any, m.workspaces, m.order) == (
        "sim", "1.0.0", ("bim",), ("network",), ("sim.run",), ("Simulation",), 30)
    assert m.default_enabled is True and m.category == "Sath" and m.origin == "bundled"


HEAD = 'id = "sim"\nname = "x"\nversion = "1.0.0"\napi = ">=1.0"\n'


@pytest.mark.parametrize("text, msg", [
    ('id = "Sim"\nname = "x"\nversion = "1.0.0"\napi = ">=1.0"', "id"),
    ('id = "sim"\nname = "x"\nversion = "1.0"\napi = ">=1.0"', "version"),
    ('id = "sim"\nname = "x"\nversion = "1.0.0"\napi = "1.0+"', "api"),
    (HEAD + 'permissions = ["root"]', "ruxsat"),
    (HEAD + 'requires = ["sim"]', "o'ziga"),
    (HEAD + 'order = "1"', "order"),
    (HEAD + "default_enabled = 1", "default_enabled"),
    ('id = "sim"\nversion = "1.0.0"\napi = ">=1.0"', "name"),
    ("id = ", "TOML"),
])  # fmt: skip
def test_parse_manifest_rejects(text, msg):
    with pytest.raises(ManifestError, match=msg):
        registry.parse_manifest(text, Path("sim"))


def test_folder_must_match_id():
    with pytest.raises(ManifestError, match="papka"):
        registry.parse_manifest(HEAD, Path("boshqa"))


def test_api_range():
    assert registry.api_ok(">=1.0,<2") and registry.api_ok(">=1") and registry.api_ok("==1.0")
    assert not registry.api_ok(">=1.1") and not registry.api_ok("<1") and not registry.api_ok(">=2.0,<3")
    assert registry.api_ok(">=1.0,<2", (1, 7)) and not registry.api_ok(">=1.0,<2", (2, 0))


# ---------- tartib ----------


def test_resolve_dependencies_first_then_order_and_id():
    out, bad = registry.resolve([_m("twin", ["sim", "scada"], 50), _m("sim", ["bim"], 30), _m("scada", order=40),
                                 _m("bim", order=70), _m("review", order=20)])  # fmt: skip
    assert [m.id for m in out] == ["review", "scada", "bim", "sim", "twin"] and bad == {}


def test_resolve_missing_dependency_cascades():
    out, bad = registry.resolve([_m("twin", ["sim"]), _m("sim", ["yoq"]), _m("io")])
    assert [m.id for m in out] == ["io"]
    assert "topilmadi: yoq" in bad["sim"] and "ishlamaydi: sim" in bad["twin"]


def test_resolve_cycle_and_api_mismatch():
    out, bad = registry.resolve([_m("a", ["b"]), _m("b", ["a"]), _m("c", api=">=2.0"), _m("d")])
    assert [m.id for m in out] == ["d"]
    assert "halqa" in bad["a"] and "halqa" in bad["b"] and "API" in bad["c"]


def test_bundled_cannot_require_user_module():
    out, bad = registry.resolve([_m("bim"), _m("ext", origin="user"), _m("sim", ["ext"])])
    assert [m.id for m in out] == ["bim", "ext"] and "foydalanuvchi" in bad["sim"]


# ---------- topish va imzo ----------


def test_discover_bundled_and_signed_user_modules(tmp_path):
    bundled, user = tmp_path / "b", tmp_path / "u"
    _write(bundled, "review")
    (bundled / "__pycache__").mkdir()
    (bundled / "bosh").mkdir()  # manifest yo'q — e'tiborsiz
    _write(bundled, "broken").joinpath(registry.MANIFEST).write_text('id = "broken"', encoding="utf-8")
    sign_module.sign_module(_write(user, "ext"), SEED)
    _write(user, "unsigned")
    bad = _write(user, "tampered")
    sign_module.sign_module(bad, SEED)
    (bad / "__init__.py").write_text("def register(api):\n    raise SystemExit\n", encoding="utf-8")
    sign_module.sign_module(_write(user, "review"), SEED)

    found, errors = registry.discover(bundled, user, [sign_module.public_key(SEED)])
    assert sorted(m.id for m in found) == ["ext", "review"]
    assert next(m for m in found if m.id == "ext").origin == "user"
    assert next(m for m in found if m.id == "review").origin == "bundled"
    msgs = dict(errors)
    assert "version" in msgs["broken"]
    assert "imzolanmagan" in msgs["unsigned (foydalanuvchi)"]
    assert "imzo noto'g'ri" in msgs["tampered (foydalanuvchi)"]
    assert "band" in msgs["review (foydalanuvchi)"]


def test_user_modules_need_trusted_key(tmp_path):
    d = _write(tmp_path / "u", "ext")
    sign_module.sign_module(d, SEED)
    found, errors = registry.discover(tmp_path / "yoq", tmp_path / "u", [])
    assert found == [] and "kalit" in dict(errors)["ext (foydalanuvchi)"]
    found, errors = registry.discover(tmp_path / "yoq", tmp_path / "u", [sign_module.public_key(bytes(32))])
    assert found == [] and "imzo noto'g'ri" in dict(errors)["ext (foydalanuvchi)"]


def test_pycache_does_not_break_signature(tmp_path):
    d = _write(tmp_path / "u", "ext")
    sign_module.sign_module(d, SEED)
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
    found, _ = registry.discover(tmp_path / "yoq", tmp_path / "u", [sign_module.public_key(SEED)])
    assert [m.id for m in found] == ["ext"]


def test_decode_keys_accepts_base64_hex_lists_and_skips_garbage():
    pub = sign_module.public_key(SEED)
    assert registry.decode_keys([base64.b64encode(pub).decode() + ", yaroqsiz", pub.hex(), ""]) == [pub]


def test_sign_matches_cryptography():
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    sk = ed.Ed25519PrivateKey.from_private_bytes(SEED)
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert sign_module.public_key(SEED) == pub
    for msg in (b"", b"sath", bytes(range(256))):
        assert sign_module.sign(SEED, msg) == sk.sign(msg)


# ---------- hayot sikli ----------


class Fake:
    """Soxta bpy: ro'yxatdagi klasslar + modul jurnali."""

    def __init__(self):
        self.registered: list = []
        self.log: list[str] = []
        self.errors: list[str] = []
        self.modules: dict[str, SimpleNamespace] = {}

    def register_class(self, c):
        assert c not in self.registered, f"ikki marta: {c}"
        self.registered.append(c)

    def unregister_class(self, c):
        self.registered.remove(c)

    def make(self, mid, *, fail=False, classes=1, unreg_fail=False):
        cls = [type(f"{mid}_{i}", (), {}) for i in range(classes)]

        def register(api):
            self.log.append(f"+{mid}")
            api.register_classes(mid, cls)
            api.on_unregister(mid, lambda: self.log.append(f"cleanup {mid}"))
            if fail:
                raise RuntimeError(f"{mid} ataylab yiqildi")

        def unregister(api):
            self.log.append(f"-{mid}")
            if unreg_fail:
                raise RuntimeError("unregister xatosi")

        self.modules[mid] = SimpleNamespace(register=register, unregister=unregister, CLASSES=cls)


def _reg(fake, manifests):
    reg = Registry(import_module=lambda m: fake.modules[m.id], register_class=fake.register_class,
                   unregister_class=fake.unregister_class, log=fake.errors.append)  # fmt: skip
    reg.api = SimpleNamespace(register_classes=reg.add_classes, on_unregister=reg.add_cleanup)
    reg.load(manifests)
    return reg


def test_start_respects_wanted_and_dependencies():
    f = Fake()
    for mid in ("bim", "sim", "twin", "io"):
        f.make(mid)
    reg = _reg(f, [_m("bim"), _m("sim", ["bim"]), _m("twin", ["sim"]), _m("io")])
    reg.start(lambda m: m.id != "sim")
    assert {i for i, r in reg.records.items() if r.state == "enabled"} == {"bim", "io"}
    assert reg.records["twin"].state == "disabled"  # sim o'chiq — twin yoqilmaydi
    assert len(f.registered) == 2 and reg.records["bim"].ms >= 0.0


def test_failed_register_is_isolated():
    f = Fake()
    f.make("ok")
    f.make("bad", fail=True, classes=2)
    reg = _reg(f, [_m("bad", order=1), _m("ok", order=2)])
    reg.start(lambda m: True)
    bad, ok = reg.records["bad"], reg.records["ok"]
    assert bad.state == "failed" and "ataylab yiqildi" in bad.error and "Traceback" in bad.error
    assert ok.state == "enabled"
    assert f.registered == f.modules["ok"].CLASSES  # «bad» ning 2 klassi qaytarildi
    assert "cleanup bad" in f.log and any("bad" in e for e in f.errors)


def test_disable_cascades_in_reverse_and_enable_pulls_dependencies():
    f = Fake()
    for mid in ("bim", "sim", "twin"):
        f.make(mid)
    reg = _reg(f, [_m("bim"), _m("sim", ["bim"]), _m("twin", ["sim", "bim"])])
    reg.start(lambda m: True)
    f.log.clear()
    assert reg.dependents("bim") == ["sim", "twin"]
    assert reg.disable("bim") == ["twin", "sim", "bim"]
    assert f.log == ["-twin", "cleanup twin", "-sim", "cleanup sim", "-bim", "cleanup bim"]
    assert f.registered == []
    assert reg.enable("twin") == ["bim", "sim", "twin"]
    assert all(r.state == "enabled" for r in reg.records.values())


def test_unregister_error_still_tears_down():
    f = Fake()
    f.make("x", unreg_fail=True)
    reg = _reg(f, [_m("x")])
    reg.start(lambda m: True)
    assert reg.disable("x") == ["x"]
    assert f.registered == [] and reg.records["x"].state == "disabled"
    assert any("unregister xatosi" in e for e in f.errors)


def test_failed_module_can_be_disabled_and_retried_after_fix():
    f = Fake()
    f.make("x", fail=True)
    reg = _reg(f, [_m("x")])
    reg.start(lambda m: True)
    assert reg.records["x"].state == "failed"
    assert reg.disable("x") == [] and reg.records["x"].state == "disabled"
    f.make("x")  # tuzatilgan modul: yiqilgandan keyin qayta import qilinadi
    assert reg.enable("x") == ["x"] and reg.records["x"].state == "enabled" and reg.records["x"].error == ""


def test_add_classes_outside_register_is_rejected():
    f = Fake()
    reg = _reg(f, [_m("y")])
    with pytest.raises(ValueError):
        reg.add_classes("y", [type("Z", (), {})])
    with pytest.raises(ValueError):
        reg.add_classes("yoq", [])


def test_load_rescan_keeps_unchanged_and_drops_removed():
    f = Fake()
    for mid in ("a", "b"):
        f.make(mid)
    reg = _reg(f, [_m("a"), _m("b", origin="user")])
    reg.start(lambda m: True)
    rec_a = reg.records["a"]
    reg.load([_m("a")], [("b (foydalanuvchi)", "imzo noto'g'ri")])
    assert reg.records["a"] is rec_a and rec_a.state == "enabled"
    assert "b" not in reg.records and f.registered == f.modules["a"].CLASSES
    assert reg.broken == [("b (foydalanuvchi)", "imzo noto'g'ri")]
