"""Tizim: desktop klient yangilanishi (zip tarqatish), sozlamalar holati."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from .. import audit
from ..auth.deps import DB, AdminUser, CurrentUser
from ..auth.security import create_access_token, decode_access_token
from ..config import get_settings
from ..orm import User

router = APIRouter(prefix="/api", tags=["system"])

# Paket nomlari: fork build (installer/zip) va eski portable zip
#   Sath-0.1.0-Windows-x86_64-installer.exe, Sath-0.1.0-Windows-x86_64.zip, Sath-Desktop-0.1.0.zip
_NAME = re.compile(
    r"^Sath-(?:Desktop-)?(\d+\.\d+\.\d+)(?:-Windows-x86_64)?(?P<ext>-installer\.exe|\.zip)$"
)
_KIND = {"-installer.exe": "installer", ".zip": "zip"}
_MEDIA = {"installer": "application/vnd.microsoft.portable-executable", "zip": "application/zip"}
NAME_HINT = (
    "Nom formati: Sath-x.y.z-Windows-x86_64-installer.exe yoki Sath-x.y.z-Windows-x86_64.zip"
)


def _desktop_dir() -> Path:
    d = get_settings().data_dir / "desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _packages() -> list[tuple[tuple[int, ...], str, str, Path]]:
    """[(versiya kaliti, versiya, kind, fayl)] — mavjud paketlar."""
    out = []
    for p in _desktop_dir().glob("Sath-*"):
        m = _NAME.match(p.name)
        if m:
            out.append(
                (tuple(int(x) for x in m.group(1).split(".")), m.group(1), _KIND[m["ext"]], p)
            )
    return out


def _latest() -> list[tuple[str, str, Path]] | None:
    """Eng yangi versiyaning fayllari: [(versiya, kind, fayl)], installer birinchi."""
    pk = _packages()
    if not pk:
        return None
    top = max(k for k, *_ in pk)
    files = [(v, kind, p) for k, v, kind, p in pk if k == top]
    files.sort(key=lambda t: t[1] != "installer")
    return files


@router.get("/desktop/latest")
def desktop_latest(_: CurrentUser):
    """Desktop ishga tushganda / web tugmasi uchun: eng yangi versiya. {version, kind, url, size,
    files:[{kind, name, url, size}]} — installer bo'lsa u asosiy, zip qo'shimcha. Yo'q bo'lsa 404."""
    found = _latest()
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Desktop paketi yuklanmagan")
    files = [
        {
            "kind": kind,
            "name": p.name,
            "url": f"/api/desktop/download/{p.name}",
            "size": p.stat().st_size,
        }
        for _v, kind, p in found
    ]
    return {
        "version": found[0][0],
        **{k: files[0][k] for k in ("kind", "url", "size")},
        "files": files,
    }


@router.post("/desktop/download-token")
def desktop_download_token(user: CurrentUser):
    """Brauzer havolasi uchun qisqa muddatli (5 daqiqa), faqat yuklab olishga yaraydigan token —
    sessiya tokeni URL ga (log/tarixga) tushmasin."""
    return {"token": create_access_token(user.id, minutes=5, scope="desktop-download")}


@router.get("/desktop/download/{name}")
def desktop_download(
    name: str,
    db: DB,
    token: str = Query(""),
    authorization: Annotated[str | None, Header()] = None,
):
    """Yuklab olish: Bearer sessiya tokeni yoki ?token=<download-token> (brauzer havolasi)."""
    uid = None
    if token:
        uid = decode_access_token(token, scope="desktop-download")
    elif authorization and authorization.lower().startswith("bearer "):
        uid = decode_access_token(authorization[7:])
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token kerak")
    m = _NAME.match(name)
    if not m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_HINT)
    p = _desktop_dir() / name
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fayl topilmadi")
    return FileResponse(p, media_type=_MEDIA[_KIND[m["ext"]]], filename=name)


@router.post("/desktop/upload", status_code=201)
async def desktop_upload(file: UploadFile, admin: AdminUser, db: DB):
    """Administrator yangi desktop paketini yuklaydi (build_portable.py yoki CI natijasi:
    installer va/yoki zip)."""
    name = Path(file.filename or "").name
    if not _NAME.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_HINT)
    dest = _desktop_dir() / name
    size = 0
    with open(dest, "wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
            size += len(chunk)
    audit.log(
        db,
        user_id=admin.id,
        action="desktop.upload",
        target_type="system",
        detail={"name": name, "size": size},
    )
    db.commit()
    return {"name": name, "size": size}
