"""Sath modul reyestri — bpy siz (pytest): manifest, topish, imzo, tartib va hayot sikli (spec §1).

Modul — papka: `sath_module.toml` + `__init__.py` (`register(api)`, ixtiyoriy `unregister(api)`).
Birinchi tomon: sath/modules/<id>/ (bundle ichida, imzo talab qilinmaydi). Uchinchi tomon:
<user config>/sath_modules/<id>/ — faqat prefs.allow_user_modules yoqilgan va papka ishonchli Ed25519 kalit bilan
imzolangan (`sath_module.sig`, tekshiruv update.py dagi) bo'lsa; imzosiz/o'zgartirilgan modul import qilinmaydi.
Uchinchi tomon modulida bayt-kod (*.pyc, __pycache__), symlink yoki junction bo'lsa — rad etiladi; u faqat
`load_user_module()` orqali import qilinadi: imzo import oldidan qayta tekshiriladi va kod aynan tekshirilgan manba
baytlaridan kompilyatsiya qilinadi (bayt-kod o'qilmaydi va yozilmaydi; submodullar ham shu yo'ldan).
Manifestdagi `permissions` — deklaratsiya (Sozlamalarda ko'rsatiladi), Python kodini cheklamaydi.
Blender ulagichi — core/host.py; bu fayl bpy ni import qilmaydi.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import operator
import os
import re
import stat
import sys
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from ..update import UpdateError, decode_public_key, ed25519_verify

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 (pytest .venv): tomli — pytest ning 3.11 dan pastdagi majburiy bog'liqligi
    import tomli as tomllib

API_VERSION = (1, 0)
MANIFEST = "sath_module.toml"
SIGNATURE = "sath_module.sig"
CAPABILITIES = frozenset({"network", "files", "subprocess", "ifc.write"})
_ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_CONSTRAINT = re.compile(r"^(>=|<=|==|>|<)\s*(\d+)(?:\.(\d+))?$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt, "<": operator.lt}


class ManifestError(ValueError):
    """Manifest yoki imzo yaroqsiz — modul yuklanmaydi (sabab Sozlamalarda ko'rsatiladi)."""


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    version: str
    api: str
    path: Path
    origin: str = "bundled"  # bundled | user
    requires: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    visible_if_any: tuple[str, ...] = ()
    workspaces: tuple[str, ...] = ()
    category: str = "Sath"
    default_enabled: bool = True
    order: int = 100


def parse_range(spec: str) -> list[tuple[str, tuple[int, int]]]:
    out = []
    for part in spec.split(","):
        m = _CONSTRAINT.match(part.strip())
        if m is None:
            raise ManifestError(f'api oralig\'i noto\'g\'ri: «{spec}» (namuna: ">=1.0,<2")')
        out.append((m.group(1), (int(m.group(2)), int(m.group(3) or 0))))
    return out


def api_ok(spec: str, version: tuple[int, int] = API_VERSION) -> bool:
    return all(_OPS[op](version, v) for op, v in parse_range(spec))


def parse_manifest(text: str, path: Path, origin: str = "bundled") -> Manifest:
    try:
        d = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"{MANIFEST}: TOML xatosi — {e}") from None

    def text_field(key: str, default: str | None = None) -> str:
        v = d.get(key, default)
        if not isinstance(v, str) or not v.strip():
            raise ManifestError(f"«{key}» bo'sh bo'lmagan satr bo'lishi kerak")
        return v.strip()

    def list_field(key: str) -> tuple[str, ...]:
        v = d.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
            raise ManifestError(f"«{key}» satrlar ro'yxati bo'lishi kerak")
        return tuple(v)

    mid = text_field("id")
    if not _ID.match(mid):
        raise ManifestError(f"id «{mid}» noto'g'ri: kichik lotin harf, raqam, «_» (2–32 belgi)")
    if path.name != mid:
        raise ManifestError(f"papka nomi «{path.name}» id «{mid}» ga teng emas")
    version = text_field("version")
    if not _SEMVER.match(version):
        raise ManifestError(f"version «{version}» X.Y.Z ko'rinishida bo'lishi kerak")
    api = text_field("api")
    parse_range(api)
    requires = list_field("requires")
    if mid in requires:
        raise ManifestError("modul o'ziga bog'liq bo'lolmaydi")
    permissions = list_field("permissions")
    unknown = sorted(set(permissions) - CAPABILITIES)
    if unknown:
        raise ManifestError(f"noma'lum ruxsat(lar): {', '.join(unknown)} (mumkin: {', '.join(sorted(CAPABILITIES))})")
    default_enabled = d.get("default_enabled", True)
    if not isinstance(default_enabled, bool):
        raise ManifestError("«default_enabled» true/false bo'lishi kerak")
    order = d.get("order", 100)
    if isinstance(order, bool) or not isinstance(order, int):
        raise ManifestError("«order» butun son bo'lishi kerak")
    return Manifest(
        id=mid, name=text_field("name"), version=version, api=api, path=path, origin=origin, requires=requires,
        permissions=permissions, visible_if_any=list_field("visible_if_any"), workspaces=list_field("workspaces"),
        category=text_field("category", "Sath"), default_enabled=default_enabled, order=order,
    )  # fmt: skip


# ---------- imzo (uchinchi tomon modullari) ----------


_BYTECODE = (".pyc", ".pyo")


def _is_link(st: os.stat_result) -> bool:
    """lstat natijasi bo'yicha: symlink yoki (Windows) har qanday reparse point — junction ham."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _snapshot(path: Path) -> dict[str, bytes]:
    """Modul papkasidagi barcha fayllar {nisbiy posix yo'l: baytlar} — bir marta o'qiladi (imzo va import shu nusxadan).
    Bayt-kod (*.pyc/*.pyo, __pycache__), symlink, junction yoki oddiy bo'lmagan fayl — ManifestError: jimgina
    o'tkazib yuborilmaydi (Python ularni manba o'rniga yuklashi mumkin)."""

    def reject(rel: str) -> None:
        raise ManifestError(f"modulda bayt-kod/symlink bor — rad etildi: {rel}")

    if _is_link(os.lstat(path)):
        reject(".")
    files: dict[str, bytes] = {}

    def walk(d: Path, prefix: str) -> None:
        with os.scandir(d) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            rel = prefix + e.name
            st = e.stat(follow_symlinks=False)
            if _is_link(st):
                reject(rel)
            if stat.S_ISDIR(st.st_mode):
                if e.name == "__pycache__":
                    reject(rel)
                walk(Path(e.path), rel + "/")
            elif stat.S_ISREG(st.st_mode):
                if e.name.lower().endswith(_BYTECODE):
                    reject(rel)
                files[rel] = Path(e.path).read_bytes()
            else:
                reject(rel)

    walk(path, "")
    return files


def _message(files: dict[str, bytes], manifest: Manifest) -> bytes:
    digests = {rel: hashlib.sha256(b).hexdigest() for rel, b in files.items() if rel != SIGNATURE}
    payload = {"files": digests, "id": manifest.id, "version": manifest.version}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def module_message(path: Path, manifest: Manifest) -> bytes:
    """Imzolanadigan kanonik xabar: papkadagi har fayl sha256 (imzo faylidan tashqari) + id + version.
    Bayt-kod/symlink bo'lsa ManifestError (imzolashdan oldin __pycache__ ni o'chiring)."""
    return _message(_snapshot(path), manifest)


def _verified_snapshot(path: Path, manifest: Manifest, trusted_keys: list[bytes]) -> dict[str, bytes]:
    if not trusted_keys:
        raise ManifestError("ishonchli kalit yo'q — Sozlamalar → Sath → «Modul kalitlari»")
    files = _snapshot(path)
    if SIGNATURE not in files:
        raise ManifestError(f"imzolanmagan ({SIGNATURE} yo'q)")
    try:
        sig = base64.b64decode(files[SIGNATURE].decode("ascii").strip(), validate=True)
    except (ValueError, binascii.Error):
        raise ManifestError("imzo fayli buzilgan") from None
    msg = _message(files, manifest)
    if not any(ed25519_verify(k, msg, sig) for k in trusted_keys):
        raise ManifestError("imzo noto'g'ri yoki kalit ishonchli emas — modul o'zgartirilgan bo'lishi mumkin")
    return files


def verify_signature(path: Path, manifest: Manifest, trusted_keys: list[bytes]) -> None:
    _verified_snapshot(path, manifest, trusted_keys)


# ---------- uchinchi tomon modulini xavfsiz import ----------


class _SnapshotLoader(importlib.abc.Loader):
    """Kodni imzo tekshirilgan baytlardan kompilyatsiya qiladi — diskdagi .py/.pyc ga qaytib qaramaydi."""

    def __init__(self, origin: str, source: bytes) -> None:
        self._origin = origin
        self._source = source

    def create_module(self, spec):
        return None

    def exec_module(self, module: ModuleType) -> None:
        exec(compile(self._source, self._origin, "exec", dont_inherit=True), module.__dict__)  # imzo tekshirilgan baytlar

    def get_source(self, fullname: str) -> str:
        return importlib.util.decode_source(self._source)


class _UserModuleFinder(importlib.abc.MetaPathFinder):
    """`_sath_user_<id>` va uning submodullari faqat tekshirilgan nusxadan; nusxada yo'q nom — ModuleNotFoundError
    (PathFinder diskdan keyin qo'shilgan fayl yoki bayt-kodni topmasin)."""

    def __init__(self) -> None:
        self.roots: dict[str, tuple[Path, dict[str, bytes]]] = {}

    def find_spec(self, fullname, path=None, target=None):
        top, _, rest = fullname.partition(".")
        entry = self.roots.get(top)
        if entry is None:
            return None
        root, files = entry
        base = rest.replace(".", "/")
        init = f"{base}/__init__.py" if base else "__init__.py"
        if init in files:
            rel, is_pkg = init, True
        elif base and f"{base}.py" in files:
            rel, is_pkg = f"{base}.py", False
        else:
            raise ModuleNotFoundError(f"{fullname}: imzolangan modulda bunday fayl yo'q", name=fullname)
        origin = str(root / rel)
        spec = importlib.util.spec_from_loader(fullname, _SnapshotLoader(origin, files[rel]), origin=origin,
                                               is_package=is_pkg)  # fmt: skip
        spec.has_location = True  # __file__ o'rnatilsin
        if is_pkg:
            spec.submodule_search_locations = [str(Path(origin).parent)]
        return spec


_FINDER = _UserModuleFinder()


def user_module_name(mod_id: str) -> str:
    return f"_sath_user_{mod_id}"


def unload_user_module(mod_id: str) -> None:
    """Foydalanuvchi modulini (va submodullarini) sys.modules va finder dan olib tashlaydi."""
    name = user_module_name(mod_id)
    _FINDER.roots.pop(name, None)
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]


def load_user_module(manifest: Manifest, trusted_keys: Iterable[bytes]) -> ModuleType:
    """Uchinchi tomon modulini xavfsiz import qiladi (core/host.py shu orqali): papka shu zahoti qayta o'qiladi va imzo
    qayta tekshiriladi (discover dan keyingi almashtirish — TOCTOU — yopiladi), manifest discover dagisi bilan bir xil
    bo'lishi shart; kod va barcha submodullar aynan shu tekshirilgan baytlardan bajariladi, bayt-kod o'qilmaydi va
    __pycache__ yozilmaydi. Nom: `_sath_user_<id>` (paket; ichida `from . import x` ishlaydi). Xato — ManifestError
    yoki modulning o'z istisnosi; bunda sys.modules tozalanadi (tuzatilgach qayta yuklash mumkin)."""
    files = _verified_snapshot(manifest.path, manifest, list(trusted_keys))
    try:
        text = files[MANIFEST].decode("utf-8-sig")
    except (KeyError, UnicodeDecodeError):
        raise ManifestError(f"{MANIFEST} o'qilmadi") from None
    if parse_manifest(text, manifest.path, "user") != manifest:
        raise ManifestError("manifest topilgandan keyin o'zgargan — qayta skanerlang")
    if "__init__.py" not in files:
        raise ManifestError("__init__.py yo'q")
    name = user_module_name(manifest.id)
    unload_user_module(manifest.id)
    _FINDER.roots[name] = (manifest.path, files)
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)
    try:
        return importlib.import_module(name)
    except BaseException:
        unload_user_module(manifest.id)
        raise


def decode_keys(texts: Iterable[str]) -> list[bytes]:
    """Vergul/bo'shliq bilan ajratilgan base64 yoki hex ochiq kalitlar; yaroqsizi tashlanadi, takror yo'q."""
    out: list[bytes] = []
    for t in texts:
        for part in re.split(r"[\s,;]+", t or ""):
            if not part:
                continue
            try:
                k = decode_public_key(part)
            except UpdateError:
                continue
            if k not in out:
                out.append(k)
    return out


# ---------- topish va tartib ----------


def discover(bundled: Path, user: Path | None = None, trusted_keys: Iterable[bytes] = ()) -> tuple[list[Manifest], list[tuple[str, str]]]:
    """Manifestlarni topadi. Qaytaradi: (yaroqli manifestlar, [(belgi, sabab)] — yuklanmaganlar)."""
    keys = list(trusted_keys)
    found: list[Manifest] = []
    errors: list[tuple[str, str]] = []
    for origin, root in (("bundled", bundled), ("user", user)):
        if root is None or not root.is_dir():
            continue
        try:
            dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
        except OSError as e:  # masalan foydalanuvchi papkasiga ruxsat yo'q — topilgan birinchi tomon modullari qolsin
            errors.append((root.name if origin == "bundled" else f"{root.name} (foydalanuvchi)", f"papka o'qilmadi: {e}"))
            continue
        for d in dirs:
            if not (d / MANIFEST).is_file():
                continue
            label = d.name if origin == "bundled" else f"{d.name} (foydalanuvchi)"
            try:
                m = parse_manifest((d / MANIFEST).read_text(encoding="utf-8-sig"), d, origin)
                if not (d / "__init__.py").is_file():
                    raise ManifestError("__init__.py yo'q")
                if origin == "user":
                    verify_signature(d, m, keys)
                if any(x.id == m.id for x in found):
                    raise ManifestError(f"id «{m.id}» band (birinchi tomon moduli)")
                found.append(m)
            except (ManifestError, OSError, UnicodeDecodeError) as e:
                errors.append((label, str(e)))
    return found, errors


def resolve(manifests: Iterable[Manifest]) -> tuple[list[Manifest], dict[str, str]]:
    """Topologik tartib (bog'liqlik avval; teng holatda order, id). Qaytaradi: (tartib, {id: sabab})."""
    ms = list(manifests)
    by_id = {m.id: m for m in ms}
    bad: dict[str, str] = {}
    for m in ms:
        if not api_ok(m.api):
            bad[m.id] = f"API {m.api} talab qilinadi, ilovada {API_VERSION[0]}.{API_VERSION[1]}"
            continue
        for r in m.requires:
            if r not in by_id:
                bad[m.id] = f"bog'liqlik topilmadi: {r}"
                break
            if m.origin == "bundled" and by_id[r].origin != "bundled":
                bad[m.id] = f"birinchi tomon moduli foydalanuvchi moduliga bog'liq bo'lolmaydi: {r}"
                break
    changed = True
    while changed:
        changed = False
        for m in ms:
            if m.id not in bad:
                dep = next((r for r in m.requires if r in bad), None)
                if dep is not None:
                    bad[m.id] = f"bog'liqlik ishlamaydi: {dep}"
                    changed = True
    ok = [m for m in ms if m.id not in bad]
    indeg = {m.id: len(set(m.requires)) for m in ok}
    users: dict[str, list[Manifest]] = {m.id: [] for m in ok}
    for m in ok:
        for r in set(m.requires):
            users[r].append(m)
    ready = [m for m in ok if indeg[m.id] == 0]
    out: list[Manifest] = []
    while ready:
        ready.sort(key=lambda m: (m.order, m.id))
        m = ready.pop(0)
        out.append(m)
        for u in users[m.id]:
            indeg[u.id] -= 1
            if indeg[u.id] == 0:
                ready.append(u)
    rest = {m.id: m for m in ok if m not in out}  # halqa a'zolari va halqaga bog'liqlar

    def in_cycle(mid: str) -> bool:
        seen: set[str] = set()
        stack = [r for r in rest[mid].requires if r in rest]
        while stack:
            r = stack.pop()
            if r == mid:
                return True
            if r not in seen:
                seen.add(r)
                stack.extend(x for x in rest[r].requires if x in rest)
        return False

    cyclic = {mid for mid in rest if in_cycle(mid)}
    for mid, m in rest.items():
        if mid in cyclic:
            bad[mid] = "bog'liqliklar halqasi (requires aylanib qolgan)"
        else:
            bad[mid] = f"bog'liqlik ishlamaydi: {next(r for r in m.requires if r in rest)}"
    return out, bad


# ---------- hayot sikli ----------


@dataclass(eq=False)
class Record:
    manifest: Manifest
    state: str = "disabled"  # disabled | enabled | failed
    error: str = ""
    module: Any = None
    classes: list = field(default_factory=list)
    ms: float = 0.0
    undo: list[Callable[[], None]] = field(default_factory=list, repr=False)  # LIFO: klasslar va tozalashlar


class Registry:
    """Modullar hayot sikli. Blender amallari tashqaridan (pytest — soxtalari): import_module(manifest) → modul,
    register_class / unregister_class (bpy.utils ...), log(matn)."""

    def __init__(self, *, import_module: Callable[[Manifest], Any], register_class: Callable[[type], None],
                 unregister_class: Callable[[type], None], log: Callable[[str], None] = print) -> None:  # fmt: skip
        self._import = import_module
        self._register_class = register_class
        self._unregister_class = unregister_class
        self._log = log
        self.records: dict[str, Record] = {}  # topologik tartibda
        self.broken: list[tuple[str, str]] = []  # yuklanmagan modullar: (belgi, sabab)
        self.api: Any = None
        self._current: str | None = None

    def load(self, manifests: Iterable[Manifest], errors: Iterable[tuple[str, str]] = ()) -> None:
        """Topilgan modullarni o'rnatadi (qayta skanerda ham): manifesti o'zgarmagan yozuv holati bilan qoladi;
        yo'qolgan yoki o'zgargan yoqilgan modul (va unga bog'liqlar) avval o'chiriladi."""
        ordered, bad = resolve(manifests)
        new = {m.id: m for m in ordered}
        for rid in reversed(list(self.records)):
            if new.get(rid) != self.records[rid].manifest:
                self.disable(rid)
        old = self.records
        self.records = {m.id: old[m.id] if m.id in old and old[m.id].manifest == m else Record(m) for m in ordered}
        self.broken = [*errors, *bad.items()]

    def start(self, wanted: Callable[[Manifest], bool]) -> None:
        """Yoqilishi kerak bo'lgan o'chiq modullarni tartib bilan yoqadi; bog'liqligi yoqilmagani o'tkazib yuboriladi.
        Yiqilgan (failed) modul bu yerda qayta urinilmaydi — faqat foydalanuvchi qayta yoqsa."""
        for rid, rec in self.records.items():
            if rec.state == "disabled" and wanted(rec.manifest) and all(self.is_enabled(r) for r in rec.manifest.requires):
                self._enable_one(rid)

    def stop(self) -> None:
        for rid in reversed(list(self.records)):
            self._disable_one(rid)

    def is_enabled(self, rid: str) -> bool:
        rec = self.records.get(rid)
        return rec is not None and rec.state == "enabled"

    def dependents(self, rid: str) -> list[str]:
        """rid ga (bevosita yoki bilvosita) bog'liq modullar — topologik tartibda."""
        hit, out = {rid}, []
        for r in self.records.values():
            if r.manifest.id != rid and any(x in hit for x in r.manifest.requires):
                hit.add(r.manifest.id)
                out.append(r.manifest.id)
        return out

    def enable(self, rid: str) -> list[str]:
        """Yoqadi; avval o'chiq bog'liqliklarini. Qaytaradi: yoqilganlar (tartib bilan)."""
        rec = self.records[rid]
        done: list[str] = []
        for dep in rec.manifest.requires:
            if not self.is_enabled(dep):
                done += self.enable(dep)
                if not self.is_enabled(dep):
                    rec.error = f"bog'liqlik yoqilmadi: {dep}"
                    return done
        if rec.state != "enabled" and self._enable_one(rid):
            done.append(rid)
        return done

    def disable(self, rid: str) -> list[str]:
        """O'chiradi; avval unga bog'liq yoqilganlarini (teskari tartibda). Qaytaradi: o'chirilganlar."""
        done: list[str] = []
        for d in reversed(self.dependents(rid)):
            if self.is_enabled(d):
                self._disable_one(d)
                done.append(d)
        rec = self.records[rid]
        if rec.state == "enabled":
            self._disable_one(rid)
            done.append(rid)
        elif rec.state == "failed":
            rec.state = "disabled"
        return done

    def owner(self, rid: str) -> Record:
        """Hozir register() i ishlayotgan yoki yoqilgan modul yozuvi; aks holda ValueError."""
        rec = self.records.get(rid)
        if rec is None or (rid != self._current and rec.state != "enabled"):
            raise ValueError(f"«{rid}» moduli faol emas — register_classes/tozalash faqat modulning register() ichida")
        return rec

    def add_classes(self, rid: str, classes: Iterable[type]) -> None:
        rec = self.owner(rid)
        for c in classes:
            self._register_class(c)
            rec.classes.append(c)
            rec.undo.append(lambda c=c: self._unregister_class(c))

    def add_cleanup(self, rid: str, fn: Callable[[], None]) -> None:
        self.owner(rid).undo.append(fn)

    def _enable_one(self, rid: str) -> bool:
        rec = self.records[rid]
        t0 = time.perf_counter()
        rec.error = ""
        self._current = rid
        try:
            if rec.module is None:
                rec.module = self._import(rec.manifest)
            rec.module.register(self.api)
            rec.state = "enabled"
            return True
        except (Exception, SystemExit):  # sys.exit() ham izolyatsiyadan chiqmasin
            rec.error = traceback.format_exc()
            self._teardown(rec)
            rec.module = None  # tuzatilgandan keyin qayta yoqishda qayta import qilinsin
            rec.state = "failed"
            self._log(f"[sath] «{rid}» moduli yuklanmadi:\n{rec.error}")
            return False
        finally:
            self._current = None
            rec.ms = (time.perf_counter() - t0) * 1000.0

    def _disable_one(self, rid: str) -> None:
        rec = self.records[rid]
        if rec.state != "enabled":
            return
        fn = getattr(rec.module, "unregister", None)
        if fn is not None:
            self._current = rid
            try:
                fn(self.api)
            except (Exception, SystemExit):
                self._log(f"[sath] «{rid}» moduli unregister xatosi:\n{traceback.format_exc()}")
            finally:
                self._current = None
        self._teardown(rec)
        rec.state = "disabled"

    def _teardown(self, rec: Record) -> None:
        while rec.undo:
            fn = rec.undo.pop()
            try:
                fn()
            except (Exception, SystemExit):
                self._log(f"[sath] «{rec.manifest.id}» tozalashda xato:\n{traceback.format_exc()}")
        rec.classes.clear()
