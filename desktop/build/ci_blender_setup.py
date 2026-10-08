"""CI (K7): Blender zip ni sha256 bilan tekshirib ochadi, portable rejim (runner profilidan ajratilgan prefs va
extension lar), Bonsai ni pinlangan versiya va sha256 bilan o'rnatadi. GES_BLENDER ni GITHUB_ENV ga yozadi.

  python desktop/build/ci_blender_setup.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_blender_bundle as bb  # noqa: E402

BLENDER_VERSION = "5.2.2"
BLENDER_SHA256 = "3849d17a682cba006075aaa3f3597ecb5c9c30ec31035b2e092c53e40679b535"
BLENDER_URL = f"https://download.blender.org/release/Blender5.2/blender-{BLENDER_VERSION}-windows-x64.zip"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def ensure_blender() -> Path:
    bb.TOOLS.mkdir(parents=True, exist_ok=True)
    zp = bb.TOOLS / f"blender-{BLENDER_VERSION}-windows-x64.zip"
    if not zp.exists():
        part = zp.with_name(zp.name + ".part")
        print("Blender yuklab olinmoqda:", BLENDER_URL, flush=True)
        urllib.request.urlretrieve(BLENDER_URL, part)  # noqa: S310
        os.replace(part, zp)
    if _sha256(zp) != BLENDER_SHA256:
        zp.unlink()
        raise SystemExit("Blender zip sha256 qotirilgan qiymatga mos emas")
    root = bb.TOOLS / f"blender-{BLENDER_VERSION}-windows-x64"
    if not (root / "blender.exe").exists():
        with zipfile.ZipFile(zp) as z:
            z.extractall(bb.TOOLS)
    (root / "portable").mkdir(exist_ok=True)  # Blender 4.2+: prefs/extensions shu papkada
    return root


def main() -> int:
    root = ensure_blender()
    exe = root / "blender.exe"
    bonsai = bb.ensure_bonsai(None, BLENDER_VERSION)
    subprocess.run(
        [str(exe), "-b", "--command", "extension", "install-file", "--repo", "user_default", "--enable", str(bonsai)],
        check=True,
    )
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"GES_BLENDER={exe}\n")
    print("GES_BLENDER =", exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
