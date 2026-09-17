"""Sath desktop paketlarini (desktop/dist) serverga yuklash — web «yuklab olish» va addon yangilanish xabari uchun.

python desktop/build/publish_desktop.py --server http://ges-server:8000 --user admin [--password ...] [files...]
Parol: --password, GES_ADMIN_PASSWORD env yoki so'raladi. Fayl berilmasa dist dagi eng yangi Sath-*.zip/-installer.exe.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DIST = Path(os.environ.get("GES_DIST_DIR") or ROOT / "desktop" / "dist")
NAME = re.compile(r"^Sath-(\d+\.\d+\.\d+)-Windows-x86_64(-installer\.exe|\.zip)$")


def latest_files() -> list[Path]:
    found = [(tuple(int(x) for x in m.group(1).split(".")), p) for p in DIST.glob("Sath-*") if (m := NAME.match(p.name))]
    if not found:
        return []
    top = max(k for k, _ in found)
    return [p for k, p in found if k == top]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("GES_SERVER", "http://localhost:8000"))
    ap.add_argument("--user", default=os.environ.get("GES_ADMIN_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("GES_ADMIN_PASSWORD"))
    ap.add_argument("files", nargs="*", type=Path)
    a = ap.parse_args()
    files = a.files or latest_files()
    if not files:
        print("Yuklash uchun fayl yo'q:", DIST)
        return 1
    pw = a.password or getpass.getpass(f"{a.user} paroli: ")
    with httpx.Client(base_url=a.server.rstrip("/"), timeout=httpx.Timeout(60, read=600, write=3600)) as c:
        r = c.post("/api/auth/login", data={"username": a.user, "password": pw})
        r.raise_for_status()
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        for f in files:
            print(f"yuklanmoqda: {f.name} ({f.stat().st_size // 2**20} MB) ...", flush=True)
            with open(f, "rb") as fh:
                r = c.post("/api/desktop/upload", files={"file": (f.name, fh, "application/octet-stream")})
            if r.status_code != 201:
                print("  xato:", r.status_code, r.text[:300])
                return 1
            print("  ok:", r.json())
        r = c.get("/api/desktop/latest")
        print("serverda eng yangi:", r.json().get("version"), [x["name"] for x in r.json().get("files", [])])
    return 0


if __name__ == "__main__":
    sys.exit(main())
