"""Content-addressed fayl xotira: data/files/ab/cd/<sha256>.ifc

Bir xil fayl ikki marta yuklansa bitta nusxa saqlanadi (dedup).
"""

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from ..config import get_settings

CHUNK = 1024 * 1024


def _path_for(sha: str, ext: str) -> Path:
    return get_settings().files_dir / sha[:2] / sha[2:4] / f"{sha}{ext}"


def store(stream: BinaryIO, ext: str = ".ifc", max_bytes: int | None = None) -> tuple[str, int]:
    """Oqimni vaqtinchalik faylga yozib sha256 hisoblaydi, keyin joyiga ko'chiradi.

    Qaytaradi: (sha256, hajm). max_bytes oshsa ValueError.
    """
    files_dir = get_settings().files_dir
    files_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=files_dir, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := stream.read(CHUNK):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise ValueError("Fayl juda katta")
            h.update(chunk)
            tmp.write(chunk)
    sha = h.hexdigest()
    final = _path_for(sha, ext)
    if final.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path), str(final))
    return sha, size


def resolve(sha: str, ext: str = ".ifc") -> Path:
    p = _path_for(sha, ext)
    if not p.exists():
        raise FileNotFoundError(sha)
    return p
