"""IFC → ThatOpen fragments (.frag) konvertatsiya — server tomonida (Node, web/tools/ifc2frag.mjs).

Brauzer .frag ni to'g'ridan-to'g'ri yuklaydi: katta IFC (100+ MB) uchun web-ifc parse qilinmaydi,
fayl 3–10 barobar kichik. Natija data/derived/<sha>.frag da; Node yoki tool bo'lmasa — jim
(brauzer IFC ni o'zi ochadi).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("ges_server.fragments")


def tool_path() -> Path | None:
    s = get_settings()
    if s.fragments_tool:
        return s.fragments_tool if s.fragments_tool.exists() else None
    for cand in (
        Path(__file__).resolve().parents[3] / "web" / "tools" / "ifc2frag.mjs",  # repo
        Path("/app/web/tools/ifc2frag.mjs"),  # Docker
    ):
        if cand.exists():
            return cand
    return None


def available() -> bool:
    return tool_path() is not None and shutil.which(get_settings().node_bin) is not None


def frag_path(sha: str) -> Path:
    d = get_settings().data_dir / "derived"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha}.frag"


def convert(ifc: Path, sha: str, timeout_s: int = 1800) -> Path | None:
    """Konvertatsiya (kesh bilan). Muvaffaqiyatsiz bo'lsa None — brauzer IFC bilan ishlaydi."""
    out = frag_path(sha)
    if out.exists():
        return out
    tool = tool_path()
    node = shutil.which(get_settings().node_bin)
    if tool is None or node is None:
        return None
    tmp = out.with_suffix(".frag.part")
    try:
        r = subprocess.run(
            [node, str(tool), str(ifc), str(tmp)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=tool.parent,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("fragments konvertatsiya ishlamadi: %s", e)
        return None
    if r.returncode != 0 or not tmp.exists():
        log.warning(
            "fragments konvertatsiya xato (%s): %s", r.returncode, (r.stderr or r.stdout)[-800:]
        )
        tmp.unlink(missing_ok=True)
        return None
    tmp.replace(out)
    try:
        info = json.loads(r.stdout.strip().splitlines()[-1])
        log.info(
            "fragments: %s → %s bayt, %s ms",
            info.get("ifc_bytes"),
            info.get("frag_bytes"),
            info.get("ms"),
        )
    except (ValueError, IndexError):
        pass
    return out
