"""BCF 2.1 (BIM Collaboration Format) eksport/import — issue larni Revit/ArchiCAD/BIMcollab bilan almashish.

Zip tuzilmasi: bcf.version, <TopicGuid>/markup.bcf, <TopicGuid>/viewpoint.bcfv
Kamera: bizda IFC koordinatalari (metr) — BCF ham metr, Z yuqoriga. Yo'nalish = target − position.
"""

from __future__ import annotations

import io
import math
import uuid
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET  # XXE/billion-laughs himoyasi (o'qishda)

from ..orm import Issue, IssueComment, IssueStatus

STATUS_TO_BCF = {
    IssueStatus.open: "Open",
    IssueStatus.in_progress: "InProgress",
    IssueStatus.resolved: "Resolved",
    IssueStatus.closed: "Closed",
}
BCF_TO_STATUS = {v.lower(): k for k, v in STATUS_TO_BCF.items()} | {
    "active": IssueStatus.in_progress
}
PRIORITY_TO_BCF = {"low": "Low", "normal": "Normal", "high": "High", "critical": "Critical"}
BCF_TO_PRIORITY = {v.lower(): k for k, v in PRIORITY_TO_BCF.items()} | {
    "major": "high",
    "minor": "low",
    "medium": "normal",
}

NS = "sath"


def topic_guid(issue: Issue) -> str:
    return issue.bcf_guid or str(uuid.uuid5(uuid.NAMESPACE_URL, f"{NS}/issue/{issue.id}"))


def _guid(kind: str, id_: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{NS}/{kind}/{id_}"))


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = str(text)
    return el


def _xyz(parent, tag, v) -> None:
    el = _sub(parent, tag)
    for k, val in zip(("X", "Y", "Z"), v, strict=True):
        _sub(el, k, f"{val:.6f}")


def _viewpoint_xml(vp: dict, guid: str) -> bytes:
    root = ET.Element("VisualizationInfo", {"Guid": guid})
    guids = vp.get("selected_guids") or []
    if guids:
        sel = _sub(_sub(root, "Components"), "Selection")
        for g in guids:
            _sub(sel, "Component", IfcGuid=g)
    cam = vp.get("camera") or {}
    if cam.get("position") and cam.get("target") and cam.get("space") in ("ifc", None):
        p, t = cam["position"], cam["target"]
        d = [t[i] - p[i] for i in range(3)]
        n = math.sqrt(sum(x * x for x in d)) or 1.0
        d = [x / n for x in d]
        tag = "OrthogonalCamera" if cam.get("projection") == "Orthographic" else "PerspectiveCamera"
        c = _sub(root, tag)
        _xyz(c, "CameraViewPoint", p)
        _xyz(c, "CameraDirection", d)
        _xyz(c, "CameraUpVector", (0, 0, 1))
        _sub(
            c,
            "ViewToWorldScale" if tag == "OrthogonalCamera" else "FieldOfView",
            "1" if tag == "OrthogonalCamera" else "60",
        )
    sections = vp.get("section") or []
    if sections:
        cps = _sub(root, "ClippingPlanes")
        for s in sections:
            cp = _sub(cps, "ClippingPlane")
            _xyz(cp, "Location", s.get("origin", (0, 0, 0)))
            _xyz(cp, "Direction", s.get("normal", (0, 0, 1)))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_zip(issues: list[Issue], project_name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ver = ET.Element("Version", {"VersionId": "2.1"})
        _sub(ver, "DetailedVersion", "2.1")
        z.writestr("bcf.version", ET.tostring(ver, encoding="utf-8", xml_declaration=True))
        for issue in issues:
            tg = topic_guid(issue)
            markup = ET.Element("Markup")
            topic = _sub(
                markup, "Topic", Guid=tg, TopicType="Issue", TopicStatus=STATUS_TO_BCF[issue.status]
            )
            _sub(topic, "Title", issue.title)
            _sub(topic, "Priority", PRIORITY_TO_BCF.get(issue.priority, "Normal"))
            _sub(topic, "CreationDate", _iso(issue.created_at))
            _sub(topic, "CreationAuthor", issue.author.username)
            _sub(topic, "ModifiedDate", _iso(issue.updated_at))
            if issue.assignee:
                _sub(topic, "AssignedTo", issue.assignee.username)
            _sub(topic, "Description", issue.description or "")
            vp_guid = _guid("viewpoint", issue.id)
            for c in issue.comments:
                ce = _sub(markup, "Comment", Guid=_guid("comment", c.id))
                _sub(ce, "Date", _iso(c.created_at))
                _sub(ce, "Author", c.author.username)
                _sub(ce, "Comment", c.body)
                if c.viewpoint:
                    _sub(ce, "Viewpoint", Guid=_guid("cviewpoint", c.id))
            vps = _sub(markup, "Viewpoints", Guid=vp_guid)
            _sub(vps, "Viewpoint", "viewpoint.bcfv")
            for c in issue.comments:
                if c.viewpoint:
                    cv = _sub(markup, "Viewpoints", Guid=_guid("cviewpoint", c.id))
                    _sub(cv, "Viewpoint", f"comment_{c.id}.bcfv")
            z.writestr(
                f"{tg}/markup.bcf", ET.tostring(markup, encoding="utf-8", xml_declaration=True)
            )
            z.writestr(f"{tg}/viewpoint.bcfv", _viewpoint_xml(issue.viewpoint or {}, vp_guid))
            for c in issue.comments:
                if c.viewpoint:
                    z.writestr(
                        f"{tg}/comment_{c.id}.bcfv",
                        _viewpoint_xml(c.viewpoint, _guid("cviewpoint", c.id)),
                    )
        z.writestr("project.txt", project_name)
    return buf.getvalue()


def _parse_xyz(el) -> list[float] | None:
    if el is None:
        return None
    try:
        return [float(el.findtext(k, "0")) for k in ("X", "Y", "Z")]
    except ValueError:
        return None


def parse_viewpoint(data: bytes) -> dict:
    root = SafeET.fromstring(data)
    vp: dict = {"selected_guids": [], "section": []}
    sel = root.find("Components/Selection")
    if sel is not None:
        vp["selected_guids"] = [
            c.get("IfcGuid") for c in sel.findall("Component") if c.get("IfcGuid")
        ]
    for tag, proj in (("PerspectiveCamera", "Perspective"), ("OrthogonalCamera", "Orthographic")):
        cam = root.find(tag)
        if cam is not None:
            p = _parse_xyz(cam.find("CameraViewPoint"))
            d = _parse_xyz(cam.find("CameraDirection"))
            if p and d:
                dist = 10.0
                vp["camera"] = {
                    "space": "ifc",
                    "position": p,
                    "target": [p[i] + d[i] * dist for i in range(3)],
                    "projection": proj,
                }
    for cp in root.findall("ClippingPlanes/ClippingPlane"):
        loc, dirn = _parse_xyz(cp.find("Location")), _parse_xyz(cp.find("Direction"))
        if loc and dirn:
            vp["section"].append({"origin": loc, "normal": dirn})
    return vp


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_vp(z: zipfile.ZipFile, names: set[str], folder: str, fname: str | None) -> dict:
    if fname and folder + fname in names:
        try:
            return parse_viewpoint(z.read(folder + fname))
        except (ET.ParseError, ValueError):
            return {}
    return {}


MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_ENTRY_BYTES = 5 * 1024 * 1024
MAX_TOPICS = 5000


def import_zip(data: bytes) -> list[dict]:
    """Zip → topic lar ro'yxati: {guid, title, description, status, priority, author, assignee, created_at, viewpoint, comments:[{author, body, created_at, viewpoint}]}"""
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("BCF fayl 50 MB dan katta")
    topics = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > MAX_TOPICS * 4:
            raise ValueError("BCF ichida juda ko'p fayl")
        big = [i.filename for i in infos if i.file_size > MAX_ENTRY_BYTES]
        if big:
            raise ValueError(f"BCF ichida juda katta fayl: {big[0]}")
        names = {i.filename for i in infos}
        for name in sorted(names):
            if not name.endswith("/markup.bcf"):
                continue
            if len(topics) >= MAX_TOPICS:
                break
            folder = name[: -len("markup.bcf")]
            root = SafeET.fromstring(z.read(name))
            topic = root.find("Topic")
            if topic is None:
                continue
            vp_files = {v.get("Guid"): v.findtext("Viewpoint") for v in root.findall("Viewpoints")}
            first_vp = next(iter(vp_files.values()), "viewpoint.bcfv")
            comments = []
            for c in root.findall("Comment"):
                vref = c.find("Viewpoint")
                comments.append(
                    {
                        "author": c.findtext("Author") or "bcf",
                        "body": c.findtext("Comment") or "",
                        "created_at": _parse_dt(c.findtext("Date")),
                        "viewpoint": _load_vp(z, names, folder, vp_files.get(vref.get("Guid")))
                        if vref is not None
                        else None,
                    }
                )
            topics.append(
                {
                    "guid": topic.get("Guid") or str(uuid.uuid4()),
                    "title": topic.findtext("Title") or "(nomsiz)",
                    "description": topic.findtext("Description") or "",
                    "status": BCF_TO_STATUS.get(
                        (topic.get("TopicStatus") or "open").lower(), IssueStatus.open
                    ),
                    "priority": BCF_TO_PRIORITY.get(
                        (topic.findtext("Priority") or "normal").lower(), "normal"
                    ),
                    "author": topic.findtext("CreationAuthor") or "bcf",
                    "assignee": topic.findtext("AssignedTo"),
                    "created_at": _parse_dt(topic.findtext("CreationDate")),
                    "viewpoint": _load_vp(z, names, folder, first_vp),
                    "comments": comments,
                }
            )
    return topics


def apply_import(db, model, topics: list[dict], importer) -> dict:
    """Topic larni Issue ga aylantiradi. bcf_guid bo'yicha mavjudini yangilaydi (holat, ijrochi, izohlar)."""
    created = updated = 0
    for t in topics:
        issue = db.query(Issue).filter_by(model_id=model.id, bcf_guid=t["guid"]).one_or_none()
        if issue is None:
            issue = Issue(
                model_id=model.id,
                author_id=importer.id,
                title=t["title"],
                description=f"{t['description']}\n\n[BCF: {t['author']}]".strip(),
                status=t["status"],
                priority=t["priority"],
                viewpoint=t["viewpoint"],
                bcf_guid=t["guid"],
            )
            if t["created_at"]:
                issue.created_at = t["created_at"]
            db.add(issue)
            db.flush()
            created += 1
            existing_bodies: set[str] = set()
        else:
            issue.status = t["status"]
            issue.priority = t["priority"]
            if t["viewpoint"]:
                issue.viewpoint = t["viewpoint"]
            updated += 1
            # qayta importda takrorlanmasin: "— muallif (BCF)" qo'shimchasisiz solishtiramiz
            existing_bodies = {c.body.split("\n— ")[0] for c in issue.comments}
        for c in t["comments"]:
            if c["body"] in existing_bodies:
                continue
            body = (
                f"{c['body']}\n— {c['author']} (BCF)"
                if c["author"] != importer.username
                else c["body"]
            )
            ic = IssueComment(
                issue_id=issue.id, author_id=importer.id, body=body, viewpoint=c["viewpoint"]
            )
            if c["created_at"]:
                ic.created_at = c["created_at"]
            db.add(ic)
    db.commit()
    return {"created": created, "updated": updated}
