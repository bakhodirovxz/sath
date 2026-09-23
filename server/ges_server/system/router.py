"""Tizim: desktop klient yangilanishi (zip/installer tarqatish, imzolangan manifest), sozlamalar holati."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from .. import audit, uploads
from ..auth.deps import DB, AdminUser, CurrentUser, user_from_token
from ..auth.security import create_access_token
from ..config import get_settings
from . import release

log = logging.getLogger("ges_server.system")
router = APIRouter(prefix="/api", tags=["system"])

# Paket nomlari: fork build (installer/zip), mahsulot qo'shimchasi bilan yoki eski portable zip
#   Sath-0.1.0-Windows-x86_64-installer.exe, Sath-Blender-0.3.0-Windows-x86_64.zip, Sath-Desktop-0.1.0.zip
_NAME = re.compile(
    r"^Sath-(?:(?P<prod>Desktop|Blender|FreeCAD)-)?(?P<ver>\d+\.\d+\.\d+)(?:-Windows-x86_64)?"
    r"(?P<ext>-installer\.exe|\.zip)$"
)
_KIND = {"-installer.exe": "installer", ".zip": "zip"}
_MEDIA = {"installer": "application/vnd.microsoft.portable-executable", "zip": "application/zip"}
NAME_HINT = (
    "Nom formati: Sath-[Blender-|FreeCAD-]x.y.z-Windows-x86_64-installer.exe yoki "
    "Sath-[Blender-|FreeCAD-]x.y.z-Windows-x86_64.zip"
)
PRODUCT_HINT = f"product: {' | '.join(release.PRODUCTS)}"


def _root() -> Path:
    d = get_settings().data_dir / "desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _desktop_dir(product: str) -> Path:
    """Mahsulot papkasi (desktop/<product>/) — FreeCAD va Blender paketlari bir xil nomda to'qnashmaydi.
    Eski joylashuv (desktop/ ildizi) dagi paketlar birinchi murojaatda default mahsulotga ko'chiriladi."""
    root = _root()
    d = root / product
    d.mkdir(parents=True, exist_ok=True)
    legacy = root / release.DEFAULT_PRODUCT
    for p in root.glob("Sath-*"):
        if p.is_file() and _NAME.match(p.name):
            legacy.mkdir(parents=True, exist_ok=True)
            os.replace(p, legacy / p.name)
    return d


def _product_from_name(name: str) -> str | None:
    m = _NAME.match(name)
    prod = (m["prod"] or "").lower() if m else ""
    return prod if prod in release.PRODUCTS else None


def _check_product(product: str) -> str:
    if product not in release.PRODUCTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PRODUCT_HINT)
    return product


def _manifest_path(p: Path) -> Path:
    return p.with_name(p.name + ".manifest.json")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _manifest(product: str, p: Path) -> dict:
    """Paket manifesti (version, product, kind, name, size, sha256, signature, key_id). Eski paketda manifest
    yo'q bo'lsa sha256 bir marta hisoblanib yoziladi (imzosiz)."""
    mp = _manifest_path(p)
    if mp.exists():
        try:
            man = json.loads(mp.read_text(encoding="utf-8"))
            if man.get("size") == p.stat().st_size:
                return man
        except (OSError, ValueError):
            pass
    m = _NAME.match(p.name)
    man = {
        "product": product,
        "version": m["ver"],
        "kind": _KIND[m["ext"]],
        "name": p.name,
        "size": p.stat().st_size,
        "sha256": _sha256_file(p),
        "signature": None,
        "key_id": None,
    }
    _write_manifest(p, man)
    return man


def _write_manifest(p: Path, man: dict) -> None:
    mp = _manifest_path(p)
    tmp = mp.with_name(f".{mp.name}.part")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, mp)


def _packages(product: str) -> list[tuple[tuple[int, ...], str, str, Path]]:
    """[(versiya kaliti, versiya, kind, fayl)] — mahsulotning to'liq yuklangan paketlari (`.part` emas)."""
    out = []
    for p in _desktop_dir(product).glob("Sath-*"):
        m = _NAME.match(p.name)
        if m and p.is_file():
            out.append((tuple(int(x) for x in m["ver"].split(".")), m["ver"], _KIND[m["ext"]], p))
    return out


def _latest(product: str) -> list[tuple[str, str, Path]] | None:
    """Eng yangi versiyaning fayllari: [(versiya, kind, fayl)], installer birinchi."""
    pk = _packages(product)
    if not pk:
        return None
    top = max(k for k, *_ in pk)
    files = [(v, kind, p) for k, v, kind, p in pk if k == top]
    files.sort(key=lambda t: t[1] != "installer")
    return files


@router.get("/desktop/latest")
def desktop_latest(_: CurrentUser, product: str = Query(release.DEFAULT_PRODUCT)):
    """Desktop ishga tushganda / web tugmasi uchun: mahsulotning eng yangi versiyasi.
    {version, product, kind, url, size, sha256, signature, key_id, files:[...]} — installer bo'lsa u asosiy,
    zip qo'shimcha. Klient yuklab olgach hajm + sha256 (+ Ed25519 imzo) ni tekshiradi (SEC-03). Yo'q — 404."""
    _check_product(product)
    found = _latest(product)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Desktop paketi yuklanmagan")
    files = []
    for _v, _kind, p in found:
        man = _manifest(product, p)
        files.append(
            {
                "kind": man["kind"],
                "name": p.name,
                "product": product,
                "version": man["version"],
                "url": f"/api/desktop/download/{product}/{p.name}",
                "size": man["size"],
                "sha256": man["sha256"],
                "signature": man.get("signature"),
                "key_id": man.get("key_id"),
            }
        )
    head = files[0]
    return {
        "version": found[0][0],
        "product": product,
        **{k: head[k] for k in ("kind", "url", "size", "sha256", "signature", "key_id")},
        "files": files,
    }


@router.post("/desktop/download-token")
def desktop_download_token(user: CurrentUser):
    """Brauzer havolasi uchun qisqa muddatli (5 daqiqa), faqat yuklab olishga yaraydigan token —
    sessiya tokeni URL ga (log/tarixga) tushmasin."""
    return {"token": create_access_token(user.id, minutes=5, scope="desktop-download", ver=user.token_version)}


def _download(db, product: str, name: str, token: str, authorization: str | None):
    user = None
    if token:
        user = user_from_token(db, token, scope="desktop-download")
    elif authorization and authorization.lower().startswith("bearer "):
        user = user_from_token(db, authorization[7:])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token kerak")
    _check_product(product)
    m = _NAME.match(name)
    if not m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_HINT)
    p = _desktop_dir(product) / name
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fayl topilmadi")
    return FileResponse(p, media_type=_MEDIA[_KIND[m["ext"]]], filename=name)


@router.get("/desktop/download/{product}/{name}")
def desktop_download_product(
    product: str,
    name: str,
    db: DB,
    token: str = Query(""),
    authorization: Annotated[str | None, Header()] = None,
):
    """Yuklab olish: Bearer sessiya tokeni yoki ?token=<download-token> (brauzer havolasi)."""
    return _download(db, product, name, token, authorization)


@router.get("/desktop/download/{name}")
def desktop_download(
    name: str,
    db: DB,
    token: str = Query(""),
    authorization: Annotated[str | None, Header()] = None,
):
    """Eski havola (mahsulotsiz) — default mahsulot (nomdagi qo'shimcha bo'lsa — o'sha)."""
    return _download(db, _product_from_name(name) or release.DEFAULT_PRODUCT, name, token, authorization)


@router.post("/desktop/upload", status_code=201)
async def desktop_upload(
    file: UploadFile,
    admin: AdminUser,
    db: DB,
    product: Annotated[str | None, Form()] = None,
    sha256: Annotated[str | None, Form()] = None,
    signature: Annotated[str | None, Form()] = None,
    key_id: Annotated[str | None, Form()] = None,
):
    """Administrator/CI yangi desktop paketini yuklaydi (publish_desktop.py): installer va/yoki zip.
    `product` (blender | freecad; berilmasa nomdan yoki default), ixtiyoriy `sha256` (nashr qiluvchi
    hisoblagan — mos kelmasa 400) va Ed25519 `signature` (kanonik manifest ustidan, release.py).
    Fayl `.part` ga yoziladi va faqat tekshiruvlardan keyin atomik `os.replace` — qisman yuklangan fayl
    hech qachon «latest» bo'lib ko'rinmaydi."""
    settings = get_settings()
    name = Path(file.filename or "").name
    m = _NAME.match(name)
    if not m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_HINT)
    prod = _check_product((product or _product_from_name(name) or release.DEFAULT_PRODUCT).lower())
    named = _product_from_name(name)
    if named and named != prod:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Nomdagi mahsulot ({named}) va product ({prod}) mos emas")
    dest = _desktop_dir(prod) / name
    # Oqimli hajm chegarasi (L5): max_upload_mb dan oshsa part o'chiriladi, 413
    size, digest, part = await uploads.spool_atomic(file, dest, settings.max_upload_mb * 1024 * 1024)
    try:
        if sha256 and sha256.strip().lower() != digest:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "sha256 mos emas — fayl uzatishda buzilgan")
        man = {
            "product": prod,
            "version": m["ver"],
            "kind": _KIND[m["ext"]],
            "name": name,
            "size": size,
            "sha256": digest,
            "signature": signature or None,
            "key_id": key_id or None,
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        verified = None
        if settings.desktop_signing_public_key:
            pub = release.decode_public_key(settings.desktop_signing_public_key)
            verified = bool(signature) and release.verify(pub, man, signature)
            if signature and not verified:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Imzo noto'g'ri (Ed25519) — paket rad etildi")
            man["key_id"] = release.key_id(pub) if verified else man["key_id"]
        if settings.desktop_require_signature and not verified:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Imzo talab qilinadi (GES_DESKTOP_REQUIRE_SIGNATURE): publish_desktop.py --signing-key",
            )
        # avval manifest (eski manifest bilan yangi fayl juftligi bo'lmasin), keyin paketning o'zi
        _write_manifest(dest, man)
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    audit.log(
        db,
        user_id=admin.id,
        action="desktop.upload",
        target_type="system",
        detail={"name": name, "product": prod, "size": size, "sha256": digest, "signed": bool(signature)},
    )
    db.commit()
    return {"name": name, "product": prod, "size": size, "sha256": digest, "signed": bool(signature), "verified": verified}
