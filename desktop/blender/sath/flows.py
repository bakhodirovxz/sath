"""Server oqimlari — bpy siz (pytest bilan real server ustida sinaladi). Operatorlar shularni chaqiradi."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .shared.server_client import GesClient, ServerError


def _manifest_version() -> str:
    try:
        text = (Path(__file__).resolve().parent / "blender_manifest.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


ADDON_VERSION = _manifest_version()


def cache_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "sath"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dt(s: str | None) -> str:
    return str(s or "")[:16].replace("T", " ")


def project_rows(client: GesClient) -> list[dict]:
    return [
        {"item_id": p["id"], "name": p["name"], "state": p.get("my_role") or ""}
        for p in client.projects()
    ]


def model_rows(client: GesClient, project_id: int) -> list[dict]:
    return [
        {"item_id": m["id"], "name": m["name"], "col2": f"{m.get('version_count', 0)} versiya"}
        for m in client.models(project_id)
    ]


def version_rows(client: GesClient, model_id: int) -> list[dict]:
    rows = []
    for v in sorted(client.versions(model_id), key=lambda x: -x["number"]):
        rows.append(
            {
                "item_id": v["id"],
                "number": v["number"],
                "name": f"v{v['number']}",
                "state": v.get("state", ""),
                "col2": v.get("message", ""),
                "col3": v.get("author_username", ""),
                "col4": _dt(v.get("created_at")),
            }
        )
    return rows


def download_version(client: GesClient, model: dict, version: dict) -> Path:
    dest = cache_dir() / f"m{model['id']}_v{version['number']}.ifc"
    client.download_version(version["id"], dest)
    return dest


def commit(
    client: GesClient,
    model_id: int,
    ifc_path: Path,
    message: str,
    parent_id: int | None,
    submit: bool,
) -> dict:
    v = client.upload_version(model_id, ifc_path, message, parent_id)
    cr = None
    if submit:
        cr = client.create_change_request(model_id, v["id"], message[:200] or f"v{v['number']}")
    return {"version": v, "cr": cr}


def newer_package(client: GesClient, current: str) -> dict | None:
    """Serverdagi desktop paketi joriy versiyadan yangi bo'lsa — {version, kind, url, size, files}."""
    try:
        latest = client.desktop_latest()
    except ServerError:
        return None
    if not latest:
        return None
    try:
        new = tuple(int(x) for x in latest["version"].split("."))
        cur = tuple(int(x) for x in current.split("."))
    except ValueError:
        return None
    return latest if new > cur else None


def check_update(client: GesClient, current: str) -> str | None:
    """Serverda yangiroq desktop paketi bo'lsa — xabar matni."""
    latest = newer_package(client, current)
    if not latest:
        return None
    return f"Yangi Sath versiyasi: {latest['version']} (sizda {current}) — Server panelida «Yuklab olish»"


def download_url(client: GesClient, saved_server: str, pkg: dict) -> str:
    """Brauzer uchun havola: qisqa muddatli download-token bilan (web bilan bir xil)."""
    tok = client._json("POST", "/api/desktop/download-token")["token"]
    return f"{saved_server.rstrip('/')}{pkg['url']}?token={tok}"


def unread_summary(client: GesClient) -> str | None:
    try:
        n = client.notifications(unread=True, limit=5)
    except ServerError:
        return None
    return f"{len(n)} ta o'qilmagan bildirishnoma — {n[0]['title']}" if n else None


def web_url(client: GesClient, saved_server: str, path: str) -> str:
    """Prod da web shu serverdan; dev da (health.web = False, :8000) Vite :5173."""
    base = saved_server.rstrip("/")
    try:
        if not client.health().get("web", True) and base.endswith(":8000"):
            base = base[: -len(":8000")] + ":5173"
    except ServerError:
        pass
    return f"{base}{path}"


def model_role(client: GesClient, model_id: int) -> str | None:
    try:
        return client.project(client.model(model_id)["project_id"]).get("my_role")
    except ServerError:
        return None


def notification_rows(client: GesClient) -> list[dict]:
    return [
        {
            "item_id": n["id"],
            "name": n["title"],
            "col2": n["kind"],
            "col3": _dt(n.get("created_at")),
            "col4": n.get("body") or "",
            "state": "read" if n.get("read_at") else "unread",
        }
        for n in client.notifications(unread=False, limit=50)
    ]


# ------------------------------------------------------------------ taqriz, issue, farq
DIFF_COLORS = {"added": (0.25, 0.7, 0.35, 1.0), "changed": (0.9, 0.7, 0.2, 1.0)}
STATUS_UZ = {
    "open": "Ochiq",
    "changes_requested": "O'zgartirish so'ralgan",
    "approved": "Ma'qullangan",
    "rejected": "Rad etilgan",
    "merged": "Tasdiqlangan",
}


def diff_colors(d: dict) -> tuple[dict[str, tuple], str]:
    colors = {e["guid"]: DIFF_COLORS[k] for k in ("added", "changed") for e in d.get(k, [])}
    s = d.get("summary", {})
    deleted = ", ".join((e.get("name") or e["guid"]) for e in d.get("deleted", [])[:20])
    text = (
        f"+{s.get('added', 0)} qo'shilgan (yashil), ~{s.get('changed', 0)} o'zgargan (sariq), "
        f"−{s.get('deleted', 0)} o'chirilgan{': ' + deleted if deleted else ''}"
    )
    return colors, text


def issue_rows(client: GesClient, model_id: int) -> list[dict]:
    return [
        {
            "item_id": i["id"],
            "name": f"#{i['id']} {i['title']}",
            "state": i["status"],
            "col2": i.get("assignee_username") or "—",
        }
        for i in client.issues(model_id)
    ]


def issue_text(full: dict) -> str:
    lines = [
        f"#{full['id']} {full['title']} — {full.get('author_username', '')} · "
        f"{full.get('priority', '')} · {full['status']}"
    ]
    if full.get("description"):
        lines.append(full["description"])
    for c in full.get("comments", []):
        lines.append(f"  {c.get('author_username', '')}: {c['body']}")
    return "\n".join(lines)


def cr_rows(client: GesClient, model_id: int) -> list[dict]:
    return [
        {
            "item_id": cr["id"],
            "name": f"#{cr['id']} {cr['title']}",
            "state": STATUS_UZ.get(cr["status"], cr["status"]),
            "col2": f"v{cr['version_number']}" if cr.get("version_number") else str(cr["version_id"]),
            "col3": cr.get("author_username", ""),
            "col4": cr["status"],
        }
        for cr in client.change_requests(model_id)
    ]


def cr_text(full: dict) -> str:
    lines = [
        f"#{full['id']} {full['title']} — {full.get('author_username', '')} · "
        f"{STATUS_UZ.get(full['status'], full['status'])}"
    ]
    if full.get("description"):
        lines.append(full["description"])
    for r in full.get("reviews", []):
        lines.append(f"  {r.get('reviewer_username', '')} — {r['decision']}: {r.get('comment', '')}")
    return "\n".join(lines)


# ------------------------------------------------------------------ simulyatsiya
SAFETY_UZ = {"ok": "bajarildi", "warn": "ogohlantirish", "fail": "bajarilmadi", "skip": "hisoblanmadi"}


def sim_values(fields: list[dict], raw: dict) -> dict:
    """Forma matnlari → server parametrlari (turga qarab float / ro'yxat / bool)."""
    out = {}
    for f in fields:
        v = raw.get(f["key"])
        t = f["type"]
        if t == "bool":
            out[f["key"]] = bool(v)
        elif t == "select":
            out[f["key"]] = v
        else:
            txt = str(v or "").strip()
            if t == "series":
                out[f["key"]] = [float(x) for x in txt.replace(";", ",").split(",") if x.strip()]
            elif t in ("number", "int"):
                if txt:
                    out[f["key"]] = float(txt.replace(",", "."))
            else:
                out[f["key"]] = txt
    return out


def sim_result_rows(kind: dict, r: dict) -> tuple[list[dict], float | None]:
    """Natija → ko'rsatkichlar qatorlari + suv sathi (viz.water_level bo'lsa)."""
    s = r.get("summary", {})
    rows = [
        {
            "name": "Xulosa",
            "col2": str(s.get("verdict", "")),
            "state": "fail" if s.get("ok") is False else "ok",
        }
    ]
    for o in kind.get("outputs", []):
        v = s.get(o["key"])
        if v is None:
            continue
        txt = f"{v:,.2f}" if isinstance(v, float) else str(v)
        rows.append({"name": o["label"], "col2": f"{txt} {o.get('unit', '')}".strip(), "state": ""})
    level = None
    key = (kind.get("viz") or {}).get("water_level")
    if key:
        ser = r.get("series", {}).get(key)
        if isinstance(ser, list) and ser:
            level = float(max(ser))
        elif isinstance(s.get(key), int | float):
            level = float(s[key])
    return rows, level


def safety_rows(res: dict) -> tuple[str, list[dict]]:
    c = res["counts"]
    head = (
        f"{res['score']} / 100 — {res['verdict']} · {c['ok']} ok · {c['warn']} ogohlantirish · "
        f"{c['fail']} bajarilmadi · {c['skip']} hisoblanmadi"
    )
    rows = [
        {
            "name": r["title"],
            "state": SAFETY_UZ.get(r["status"], r["status"]),
            "col2": r.get("message", ""),
            "col3": " · ".join(
                f"{k} = {v:.2f}" if isinstance(v, float) else f"{k} = {v}"
                for k, v in (r.get("metrics") or {}).items()
            ),
        }
        for r in res["rows"]
    ]
    return head, rows


# ------------------------------------------------------------------ monitoring (SCADA)
ALARM_COLORS = {
    "ok": (0.23, 0.66, 0.39, 1.0),
    "low": (0.88, 0.4, 0.42, 1.0),
    "high": (0.88, 0.4, 0.42, 1.0),
    "stale": (0.42, 0.43, 0.46, 1.0),
}
ALARM_UZ = {"ok": "normal", "low": "past", "high": "yuqori", "stale": "uzilgan"}


def sensor_rows(sensors: list[dict]) -> list[dict]:
    rows = []
    for s in sensors:
        v = s.get("last_value")
        rows.append(
            {
                "item_id": s["id"],
                "name": s["name"],
                "col2": f"{v:.2f} {s.get('unit', '')}".strip() if isinstance(v, int | float) else "—",
                "state": ALARM_UZ.get(s.get("alarm"), str(s.get("alarm"))),
                "col3": _dt(s.get("last_ts")),
                "col4": "bog'langan" if s.get("element_guid") else "",
                "guid": s.get("element_guid") or "",
            }
        )
    return rows


def alarm_colors(sensors: list[dict]) -> dict[str, tuple]:
    return {
        s["element_guid"]: ALARM_COLORS.get(s.get("alarm"), (1.0, 1.0, 1.0, 1.0))
        for s in sensors
        if s.get("element_guid") and s.get("enabled")
    }


def water_sensor_level(sensors: list[dict]) -> float | None:
    for s in sensors:
        if (
            s.get("kind") == "level"
            and s.get("enabled")
            and isinstance(s.get("last_value"), int | float)
            and s.get("alarm") != "stale"
        ):
            return float(s["last_value"])
    return None


# ------------------------------------------------------------------ raqamli egizak, sog'liq, vaqt mashinasi
HEALTH_COLORS = {
    "yaxshi": (0.23, 0.66, 0.39, 1.0),
    "qoniqarli": (0.85, 0.75, 0.25, 1.0),
    "yomon": (0.9, 0.5, 0.2, 1.0),
    "kritik": (0.85, 0.25, 0.25, 1.0),
}


def _mw(v) -> str:
    return "—" if v is None else f"{v:.1f}"


def twin_head(state: dict) -> str:
    if state.get("status") != "ok":
        return f"Egizak: {state.get('status', '—')}"
    return (
        f"Napor {state.get('head_gross_m', 0):.2f} m · {_mw(state.get('measured_total_mw'))} / "
        f"{_mw(state.get('expected_total_mw'))} MW (o'lchangan / kutilgan)"
    )


def twin_rows(state: dict) -> list[dict]:
    rows = []
    for i, u in enumerate(state.get("units", [])):
        dev = u.get("deviation_pct")
        eff = u.get("efficiency")
        rows.append(
            {
                "item_id": i,
                "name": u["name"],
                "col2": f"{_mw(u.get('measured_mw'))} / {_mw(u.get('expected_mw'))} MW",
                "col3": "" if dev is None else f"{dev:+.1f} %".replace("-", "−"),
                "col4": "" if eff is None else f"FIK {eff * 100:.0f}%",
                "state": ("ok" if abs(dev or 0) < 10 else "warn") if u.get("running") else "stop",
            }
        )
    return rows


def twin_safety_rows(items: list[dict]) -> list[dict]:
    return [
        {
            "name": it["name"],
            "col2": f"{it.get('value', '')} {it.get('unit', '')}".strip(),
            "state": "ok" if it.get("ok") else "fail",
        }
        for it in items
    ]


def health_head(h: dict) -> str:
    ps = h.get("plant_score")
    return "Stansiya sog'lig'i: —" if ps is None else f"Stansiya sog'lig'i: {ps} / 100"


def health_rows(h: dict) -> list[dict]:
    return [
        {
            "item_id": a["asset_id"],
            "name": a["name"],
            "col2": str(a.get("score", "")),
            "col3": "; ".join(a.get("problems") or [])[:80],
            "state": a.get("level", ""),
            "guid": a.get("element_guid") or "",
        }
        for a in h.get("assets", [])
    ]


def health_colors(assets: list[dict]) -> dict[str, tuple]:
    return {
        a["element_guid"]: HEALTH_COLORS[a["level"]]
        for a in assets
        if a.get("element_guid") and a.get("level") in HEALTH_COLORS
    }


def reading_at(points: list[dict], ts: str) -> float | None:
    """Vaqt mashinasi: `ts` (ISO) dan oldingi oxirgi o'qish qiymati (nuqtalar vaqt bo'yicha tartiblangan)."""
    val = None
    for p in points:
        if p["ts"] <= ts:
            val = p.get("value")
        else:
            break
    return val
