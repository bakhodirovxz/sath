"""Ishonchsiz fayl parserlari uchun sandbox (L5): tashqi konverterlar (dwg2dxf, ODA, blender, assimp,
Node/web-ifc) va boshqa subprocess lar chegaralangan muhitda ishlaydi.

Rejimlar (`GES_SANDBOX`):
- `auto` — Linux da `bwrap` (bubblewrap) ishlasa shu (tarmoqsiz, PID/IPC ajratilgan, faqat ish papkasi
  yoziladi, nobody foydalanuvchisi), aks holda `rlimit`; Windows da `off` (faqat vaqt chegarasi).
- `bwrap`, `rlimit` (POSIX: RLIMIT_AS/CPU/NPROC/FSIZE), `off`.
Har doim: vaqt chegarasi, chiqish hajmi chegarasi (capture), `shell=False` (ro'yxat argumentlar).
Docker da bwrap odatda foydalanuvchi nom maydonini talab qiladi (default seccomp bloklaydi) — probe
muvaffaqiyatsiz bo'lsa `rlimit` ga tushadi; konteynerning o'zi `cap_drop: ALL`, `no-new-privileges`,
`read_only` bilan ishlaydi (docker-compose.yml).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("ges_server.sandbox")

DEFAULT_MEM_MB = 4096
DEFAULT_CPU_S = 900
MAX_OUTPUT = 1 << 20  # stdout/stderr dan saqlanadigan qism


class SandboxError(RuntimeError):
    pass


@lru_cache
def mode() -> str:
    """Amaldagi rejim (sozlama + muhit imkoniyati)."""
    from .config import get_settings

    want = get_settings().sandbox
    if want == "off":
        return "off"
    if sys.platform == "win32":
        if want not in ("auto", "off"):
            log.warning("sandbox=%s Windows da yo'q — off", want)
        return "off"
    if want in ("auto", "bwrap") and _bwrap_ok():
        return "bwrap"
    if want == "bwrap":
        log.warning("bwrap ishlamadi (foydalanuvchi nom maydoni yopiq?) — rlimit rejimi")
    return "rlimit"


def _bwrap_ok() -> bool:
    b = shutil.which("bwrap")
    if not b:
        return False
    try:
        r = subprocess.run(_bwrap_prefix(b, Path("/tmp")) + ["/bin/true"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _bwrap_prefix(b: str, work: Path, ro_paths: tuple[Path, ...] = ()) -> list[str]:
    cmd = [b, "--die-with-parent", "--new-session", "--unshare-all", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for d in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/opt", "/venv", "/app"):
        if Path(d).exists():
            cmd += ["--ro-bind", d, d]
    for p in ro_paths:
        cmd += ["--ro-bind", str(p), str(p)]
    cmd += ["--bind", str(work), str(work), "--chdir", str(work), "--setenv", "HOME", "/tmp", "--"]
    return cmd


def _rlimit_preexec(mem_mb: int, cpu_s: int):
    import resource

    def _apply():
        mem = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 30, 8 << 30))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        except (ValueError, OSError):
            pass
        os.setsid()

    return _apply


def run(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    mem_mb: int = DEFAULT_MEM_MB,
    cpu_s: int | None = None,
    check: bool = False,
    ro_paths: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess:
    """Konverterni chegaralangan muhitda ishga tushiradi. `cwd` — yagona yoziladigan papka (natija shu yerda),
    `ro_paths` — faqat o'qiladigan kirish fayllari (cwd dan tashqarida bo'lsa). Vaqt tugasa `SandboxError`;
    `check` bo'lsa nol bo'lmagan kod ham."""
    if not isinstance(cmd, list) or not cmd:
        raise ValueError("cmd — argumentlar ro'yxati")
    m = mode()
    full = list(cmd)
    kw: dict = {}
    if m == "bwrap":
        full = _bwrap_prefix(shutil.which("bwrap") or "bwrap", cwd, tuple(ro_paths)) + full
    elif m == "rlimit":
        kw["preexec_fn"] = _rlimit_preexec(mem_mb, cpu_s or min(DEFAULT_CPU_S, timeout_s * 2))
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8"}
    # Blender (--factory-startup) haqiqiy foydalanuvchi profiliga (APPDATA / ~/.config) tegmasin — profil ish papkasida
    env["BLENDER_USER_RESOURCES"] = str(cwd / ".blender-user")
    for k in ("SYSTEMROOT", "TEMP", "TMP", "WINDIR", "LD_LIBRARY_PATH", "FOAM_INST_DIR", "WM_PROJECT_DIR"):
        if k in os.environ:
            env[k] = os.environ[k]
    try:
        r = subprocess.run(full, cwd=str(cwd), capture_output=True, timeout=timeout_s, env=env, **kw)
    except subprocess.TimeoutExpired as e:
        raise SandboxError(f"konverter {timeout_s} s da tugamadi: {Path(cmd[0]).name}") from e
    except OSError as e:
        raise SandboxError(f"konverter ishga tushmadi: {e}") from e
    r.stdout, r.stderr = (r.stdout or b"")[-MAX_OUTPUT:], (r.stderr or b"")[-MAX_OUTPUT:]
    if check and r.returncode != 0:
        raise SandboxError(f"{Path(cmd[0]).name} xato ({r.returncode}): {r.stderr[-400:].decode(errors='replace')}")
    return r
