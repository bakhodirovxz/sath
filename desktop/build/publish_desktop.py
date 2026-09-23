"""Sath desktop paketlarini (desktop/dist) serverga yuklash — web «yuklab olish» va addon yangilanishi uchun.

python desktop/build/publish_desktop.py --server https://ges-server --user admin --product blender \
    --signing-key ~/.sath/release-ed25519.pem [files...]
python desktop/build/publish_desktop.py --gen-key ~/.sath/release-ed25519.pem   # bir martalik kalit juftligi

Parol: --password, GES_ADMIN_PASSWORD env yoki so'raladi. Fayl berilmasa dist dagi eng yangi paketlar.

Imzo (SEC-03): har paket uchun manifest {product, version, kind, name, size, sha256} kanonik JSON sifatida
Ed25519 bilan imzolanadi (server/ges_server/system/release.py bilan bir xil format). Private kalit faqat
shu yerda (CI secret yoki admin kompyuteri) — serverda emas. Ochiq kalit (--gen-key chiqaradi):
  * serverda GES_DESKTOP_SIGNING_PUBLIC_KEY (+ ixtiyoriy GES_DESKTOP_REQUIRE_SIGNATURE=true),
  * Blender addoni sozlamalarida «Yangilanish kaliti» (yoki SATH_UPDATE_PUBLIC_KEY muhit o'zgaruvchisi).
Kalit: --signing-key (PEM PKCS8 yoki 32 baytli xom seed base64) yoki SATH_SIGNING_KEY_FILE.

Mahsulot (--product blender | freecad): FreeCAD va Blender paketlari serverda alohida saqlanadi (bir xil nomda
to'qnashmaydi). Nomda `Sath-Blender-`/`Sath-FreeCAD-` qo'shimchasi bo'lsa undan olinadi.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = Path(os.environ.get("GES_DIST_DIR") or ROOT / "desktop" / "dist")
NAME = re.compile(
    r"^Sath-(?:(?P<prod>Blender|FreeCAD)-)?(?P<ver>\d+\.\d+\.\d+)-Windows-x86_64(?P<ext>-installer\.exe|\.zip)$"
)
PRODUCTS = ("blender", "freecad")
KIND = {"-installer.exe": "installer", ".zip": "zip"}
SIGNED_FIELDS = ("kind", "name", "product", "sha256", "size", "version")


def canonical_message(manifest: dict) -> bytes:
    payload = {k: manifest[k] for k in SIGNED_FIELDS}
    payload["size"] = int(payload["size"])
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def load_private_key(path: Path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    data = path.read_bytes()
    if b"PRIVATE KEY" in data:
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise SystemExit("Imzo kaliti Ed25519 emas")
        return key
    raw = base64.b64decode(data.strip(), validate=True)
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_raw(key) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def build_manifest(path: Path, product: str) -> dict:
    m = NAME.match(path.name)
    if not m:
        raise SystemExit(f"Nom formati noto'g'ri: {path.name}")
    return {
        "product": product,
        "version": m["ver"],
        "kind": KIND[m["ext"]],
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def sign_manifest(manifest: dict, key) -> dict:
    pub = public_raw(key)
    return {
        **manifest,
        "signature": base64.b64encode(key.sign(canonical_message(manifest))).decode("ascii"),
        "key_id": hashlib.sha256(pub).hexdigest()[:16],
    }


def product_for(path: Path, explicit: str | None) -> str:
    m = NAME.match(path.name)
    named = (m["prod"] or "").lower() if m else ""
    if explicit and named and named != explicit:
        raise SystemExit(f"{path.name}: nomdagi mahsulot ({named}) --product ({explicit}) bilan mos emas")
    prod = explicit or named
    if prod not in PRODUCTS:
        raise SystemExit(f"{path.name}: --product {' | '.join(PRODUCTS)} kerak (FreeCAD va Blender paketlari nomi bir xil)")
    return prod


def latest_files() -> list[Path]:
    found = [(tuple(int(x) for x in m["ver"].split(".")), p) for p in DIST.glob("Sath-*") if (m := NAME.match(p.name))]
    if not found:
        return []
    top = max(k for k, _ in found)
    return [p for k, p in found if k == top]


def gen_key(out: Path) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if out.exists():
        print("Fayl bor — ustiga yozilmaydi:", out)
        return 1
    key = Ed25519PrivateKey.generate()
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
    pub = base64.b64encode(public_raw(key)).decode("ascii")
    print("Private kalit:", out, "(0600 — CI secret / parol menejerida saqlang)")
    print("Ochiq kalit (GES_DESKTOP_SIGNING_PUBLIC_KEY va addon «Yangilanish kaliti»):", pub)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("GES_SERVER", "http://localhost:8000"))
    ap.add_argument("--user", default=os.environ.get("GES_ADMIN_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("GES_ADMIN_PASSWORD"))
    ap.add_argument("--product", choices=PRODUCTS, default=os.environ.get("SATH_PRODUCT") or None)
    ap.add_argument("--signing-key", type=Path, default=os.environ.get("SATH_SIGNING_KEY_FILE") or None)
    ap.add_argument("--unsigned", action="store_true", help="imzosiz (faqat sinov; server talab qilsa rad etadi)")
    ap.add_argument("--gen-key", type=Path, metavar="OUT.pem", help="Ed25519 kalit juftligi yaratish va chiqish")
    ap.add_argument("--insecure", action="store_true", help="TLS sertifikatini tekshirmaslik (faqat ichki sinov)")
    ap.add_argument("files", nargs="*", type=Path)
    a = ap.parse_args(argv)
    if a.gen_key:
        return gen_key(a.gen_key)
    files = a.files or latest_files()
    if not files:
        print("Yuklash uchun fayl yo'q:", DIST)
        return 1
    if not a.signing_key and not a.unsigned:
        print("--signing-key (yoki SATH_SIGNING_KEY_FILE) kerak; imzosiz faqat --unsigned bilan")
        return 2
    key = load_private_key(a.signing_key) if a.signing_key else None
    manifests = []
    for f in files:
        man = build_manifest(f, product_for(f, a.product))
        manifests.append((f, sign_manifest(man, key) if key else man))

    import httpx

    pw = a.password or getpass.getpass(f"{a.user} paroli: ")
    timeout = httpx.Timeout(60, read=600, write=3600)
    with httpx.Client(base_url=a.server.rstrip("/"), timeout=timeout, verify=not a.insecure) as c:
        r = c.post("/api/auth/login", data={"username": a.user, "password": pw})
        r.raise_for_status()
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        for f, man in manifests:
            print(f"yuklanmoqda: {f.name} [{man['product']}] ({f.stat().st_size // 2**20} MB) ...", flush=True)
            data = {"product": man["product"], "sha256": man["sha256"]}
            if man.get("signature"):
                data.update(signature=man["signature"], key_id=man["key_id"])
            with open(f, "rb") as fh:
                r = c.post("/api/desktop/upload", data=data, files={"file": (f.name, fh, "application/octet-stream")})
            if r.status_code != 201:
                print("  xato:", r.status_code, r.text[:300])
                return 1
            print("  ok:", r.json())
        for prod in sorted({m["product"] for _, m in manifests}):
            r = c.get("/api/desktop/latest", params={"product": prod})
            print(f"serverda eng yangi [{prod}]:", r.json().get("version"), [x["name"] for x in r.json().get("files", [])])
    return 0


if __name__ == "__main__":
    sys.exit(main())
