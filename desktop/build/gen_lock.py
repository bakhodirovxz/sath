"""Python bog'liqliklari lok fayllari (CI-03): server/requirements.lock va sim/requirements.lock.

python desktop/build/gen_lock.py          # joriy muhitdan (pip install -e ./sim -e "./server[postgres]") yozadi
python desktop/build/gen_lock.py --check  # CI: lok fayl pyproject bog'liqliklarini qamraydimi

uv/pip-tools offline bo'lmagani uchun lok — o'rnatilgan muhitdagi (importlib.metadata) paketlarning pyproject
dan boshlangan tranzitiv yopilmasi, aniq versiyalar bilan. Docker va CI uni *constraints* sifatida ishlatadi
(`pip install -c server/requirements.lock ...`): faqat o'rnatiladigan paketlar versiyasi qotiriladi, platformaga
xos (masalan Windows colorama) yoki muhitda yo'q ekstra paketlar xalaqit bermaydi. Yangilash: muhitni
yangilab (`pip install -U ...`), testlar o'tgach shu skriptni qayta ishga tushiring.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "server/requirements.lock": ("ges-server", ("postgres",)),
    "sim/requirements.lock": ("ges-sim", ()),
}
LOCAL = {"ges-server", "ges-sim"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# Markerlar: joriy muhit YOKI Docker/CI muhiti (Linux, CPython 3.12) uchun kerak bo'lsa — kiritiladi
_LINUX = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "python_version": "3.12",
    "python_full_version": "3.12.0",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}


def _wanted(req, extras: tuple[str, ...]) -> bool:
    if req.marker is None:
        return True
    for extra in (*extras, ""):
        for env in ({}, _LINUX):
            if req.marker.evaluate({**env, "extra": extra}):
                return True
    return False


def _pyproject_requires(project_dir: Path, extras: tuple[str, ...]) -> list[str]:
    """Worktree dagi pyproject.toml dan (o'rnatilgan metadata emas — u eskirgan bo'lishi mumkin)."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    proj = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    reqs = list(proj.get("dependencies", []))
    for e in extras:
        reqs += proj.get("optional-dependencies", {}).get(e, [])
    return reqs


def _closure(root: str, extras: tuple[str, ...]) -> dict[str, str]:
    """{normallashgan nom: versiya} — root paket (va ekstralari) bog'liqliklarining yopilmasi."""
    from packaging.requirements import Requirement

    out: dict[str, str] = {}
    project_dirs = {"ges-server": ROOT / "server", "ges-sim": ROOT / "sim"}
    todo: list[tuple[str, tuple[str, ...]]] = []
    for spec in _pyproject_requires(project_dirs[root], extras):
        req = Requirement(spec)
        if _wanted(req, ()):
            todo.append((req.name, tuple(sorted(req.extras))))
    seen: set[tuple[str, tuple[str, ...]]] = set()
    while todo:
        name, ex = todo.pop()
        if (_norm(name), ex) in seen:
            continue
        seen.add((_norm(name), ex))
        if _norm(name) in LOCAL:
            for spec in _pyproject_requires(project_dirs[_norm(name)], ex):
                req = Requirement(spec)
                if _wanted(req, ()):
                    todo.append((req.name, tuple(sorted(req.extras))))
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # bu muhitda yo'q (masalan faqat Linux) — lokda qotirilmaydi
        out[_norm(dist.metadata["Name"])] = dist.version
        for spec in dist.requires or []:
            req = Requirement(spec)
            if _wanted(req, ex):
                todo.append((req.name, tuple(sorted(req.extras))))
    return out


def render(target: str) -> str:
    root, extras = TARGETS[target]
    pins = _closure(root, extras)
    head = (
        f"# {target} — CI-03 lok (constraints): desktop/build/gen_lock.py bilan yaratilgan, qo'lda tahrirlamang.\n"
        f"# Manba: {root}{'[' + ','.join(extras) + ']' if extras else ''} tranzitiv bog'liqliklari, aniq versiyalar.\n"
    )
    return head + "".join(f"{k}=={v}\n" for k, v in sorted(pins.items()))


def main(argv: list[str]) -> int:
    if "--check" in argv:
        bad = []
        for target in TARGETS:
            p = ROOT / target
            if not p.exists():
                bad.append(f"{target}: yo'q")
                continue
            locked = {_norm(ln.split("==")[0]) for ln in p.read_text(encoding="utf-8").splitlines() if "==" in ln}
            proj = ROOT / target.split("/")[0] / "pyproject.toml"
            deps = re.search(r"^dependencies = \[(.*?)^\]", proj.read_text(encoding="utf-8"), re.M | re.S)
            for d in re.findall(r'^\s*"([A-Za-z0-9_.\-]+)', deps.group(1) if deps else "", re.M):
                if _norm(d) not in LOCAL and _norm(d) not in locked:
                    bad.append(f"{target}: {d} lokda yo'q")
        print("\n".join(bad) or "lok fayllar pyproject bilan mos")
        return 1 if bad else 0
    for target in TARGETS:
        (ROOT / target).write_text(render(target), encoding="utf-8", newline="\n")
        print("yozildi:", target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
