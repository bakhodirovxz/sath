import pytest
from conftest import make_ifc, upload


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "Mashina zali"},
        headers=users["engineer"],
    )
    return r.json()["id"]


@pytest.fixture
def v1(client, users, model_id, ifc_file):
    return upload(client, users["engineer"], model_id, ifc_file, "v1").json()


def open_cr(client, users, model_id, version_id, headers=None):
    r = client.post(
        f"/api/models/{model_id}/change-requests",
        json={"version_id": version_id, "title": "Tasdiqqa"},
        headers=headers or users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def review(client, headers, cr_id, decision, comment=""):
    return client.post(
        f"/api/change-requests/{cr_id}/reviews",
        json={"decision": decision, "comment": comment},
        headers=headers,
    )


def version_state(client, headers, version_id):
    return client.get(f"/api/versions/{version_id}", headers=headers).json()["state"]


# ---------- Change request oqimi ----------


def test_full_approval_flow(client, users, model_id, v1):
    cr = open_cr(client, users, model_id, v1["id"])
    assert cr["status"] == "open"
    assert version_state(client, users["viewer"], v1["id"]) == "shared"

    # viewer izoh qoldira oladi, lekin tasdiqlay olmaydi
    assert review(client, users["viewer"], cr["id"], "comment", "ko'rdim").status_code == 201
    assert review(client, users["viewer"], cr["id"], "approve").status_code == 403
    assert review(client, users["engineer"], cr["id"], "approve").status_code == 403

    r = review(client, users["approver"], cr["id"], "approve", "yaxshi")
    assert r.status_code == 201
    assert r.json()["status"] == "approved"
    assert [rv["decision"] for rv in r.json()["reviews"]] == ["comment", "approve"]

    # merge faqat approver
    assert (
        client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["engineer"]).status_code
        == 403
    )
    r = client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"])
    assert r.status_code == 200
    assert r.json()["status"] == "merged"
    assert r.json()["closed_at"] is not None
    assert version_state(client, users["viewer"], v1["id"]) == "published"

    r = client.get(f"/api/models/{model_id}/published", headers=users["viewer"])
    assert r.json()["id"] == v1["id"]
    r = client.get(f"/api/models/{model_id}", headers=users["viewer"])
    assert r.json()["published_version_id"] == v1["id"]


def test_merge_archives_previous_published(client, users, model_id, v1, ifc_file, tmp_path):
    cr1 = open_cr(client, users, model_id, v1["id"])
    review(client, users["approver"], cr1["id"], "approve")
    client.post(f"/api/change-requests/{cr1['id']}/merge", headers=users["approver"])

    v2 = upload(
        client, users["engineer"], model_id, make_ifc(tmp_path / "b.ifc", ("A", "B")), "v2"
    ).json()
    cr2 = open_cr(client, users, model_id, v2["id"])
    review(client, users["approver"], cr2["id"], "approve")
    client.post(f"/api/change-requests/{cr2['id']}/merge", headers=users["approver"])

    assert version_state(client, users["viewer"], v1["id"]) == "archived"
    assert version_state(client, users["viewer"], v2["id"]) == "published"
    r = client.get(f"/api/models/{model_id}/published", headers=users["viewer"])
    assert r.json()["id"] == v2["id"]


def test_changes_requested_then_new_version(client, users, model_id, v1, tmp_path):
    cr = open_cr(client, users, model_id, v1["id"])
    r = review(client, users["approver"], cr["id"], "request_changes", "devor noto'g'ri")
    assert r.json()["status"] == "changes_requested"
    # merge bo'lmaydi
    assert (
        client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"]).status_code
        == 409
    )

    v2 = upload(
        client, users["engineer"], model_id, make_ifc(tmp_path / "b.ifc", ("A",)), "fix"
    ).json()
    # faqat muallif yangi versiya bog'laydi
    r = client.post(
        f"/api/change-requests/{cr['id']}/version",
        json={"version_id": v2["id"]},
        headers=users["approver"],
    )
    assert r.status_code == 403
    r = client.post(
        f"/api/change-requests/{cr['id']}/version",
        json={"version_id": v2["id"]},
        headers=users["engineer"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "open"
    assert r.json()["version_id"] == v2["id"]
    assert version_state(client, users["viewer"], v1["id"]) == "wip"
    assert version_state(client, users["viewer"], v2["id"]) == "shared"


def test_cannot_open_cr_for_non_wip(client, users, model_id, v1):
    open_cr(client, users, model_id, v1["id"])
    r = client.post(
        f"/api/models/{model_id}/change-requests",
        json={"version_id": v1["id"], "title": "yana"},
        headers=users["engineer"],
    )
    assert r.status_code == 409


def test_author_cannot_approve_own_cr(client, users, model_id, ifc_file):
    # approver o'zi versiya yuklab CR ochadi → o'zini tasdiqlay olmaydi
    v = upload(client, users["approver"], model_id, ifc_file, "x").json()
    cr = open_cr(client, users, model_id, v["id"], headers=users["approver"])
    assert review(client, users["approver"], cr["id"], "approve").status_code == 403
    # admin (boshqa odam) tasdiqlaydi
    assert review(client, users["admin"], cr["id"], "approve").status_code == 201


def test_reject(client, users, model_id, v1):
    cr = open_cr(client, users, model_id, v1["id"])
    assert (
        client.post(f"/api/change-requests/{cr['id']}/reject", headers=users["viewer"]).status_code
        == 403
    )
    r = client.post(f"/api/change-requests/{cr['id']}/reject", headers=users["engineer"])  # muallif
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert version_state(client, users["viewer"], v1["id"]) == "wip"
    assert review(client, users["approver"], cr["id"], "approve").status_code == 409


def test_list_and_filter_crs(client, users, model_id, v1, tmp_path):
    cr1 = open_cr(client, users, model_id, v1["id"])
    client.post(f"/api/change-requests/{cr1['id']}/reject", headers=users["engineer"])
    v2 = upload(
        client, users["engineer"], model_id, make_ifc(tmp_path / "b.ifc", ("A",)), "2"
    ).json()
    open_cr(client, users, model_id, v2["id"])
    r = client.get(f"/api/models/{model_id}/change-requests", headers=users["viewer"])
    assert len(r.json()) == 2
    r = client.get(
        f"/api/models/{model_id}/change-requests?status_filter=open", headers=users["viewer"]
    )
    assert len(r.json()) == 1
    assert (
        client.get(f"/api/change-requests/{cr1['id']}", headers=users["outsider"]).status_code
        == 403
    )


# ---------- Diff ----------


def test_diff(client, users, model_id, v1, tmp_path):
    # v2: Wall 1 o'chirildi, A va B qo'shildi (site/storey bir xil GUID emas — ular ham o'zgaradi)
    v2 = upload(
        client, users["engineer"], model_id, make_ifc(tmp_path / "b.ifc", ("A", "B")), "v2"
    ).json()
    r = client.get(f"/api/versions/{v2['id']}/diff", headers=users["viewer"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["from_version_id"] == v1["id"] and d["to_version_id"] == v2["id"]
    added_names = {e["name"] for e in d["added"] if e["type"] == "IfcWall"}
    deleted_names = {e["name"] for e in d["deleted"] if e["type"] == "IfcWall"}
    assert added_names == {"A", "B"}
    assert deleted_names == {"Wall 1"}
    assert d["summary"]["added"] == len(d["added"])
    # kesh: ikkinchi so'rov ham bir xil
    assert client.get(f"/api/versions/{v2['id']}/diff", headers=users["viewer"]).json() == d
    # aniq from
    r = client.get(
        f"/api/versions/{v1['id']}/diff?from_version_id={v2['id']}", headers=users["viewer"]
    )
    assert {e["name"] for e in r.json()["added"] if e["type"] == "IfcWall"} == {"Wall 1"}


def test_diff_same_file_no_changes(client, users, model_id, v1, ifc_file):
    v2 = upload(client, users["engineer"], model_id, ifc_file, "same").json()
    d = client.get(f"/api/versions/{v2['id']}/diff", headers=users["viewer"]).json()
    assert d["summary"] == {"added": 0, "deleted": 0, "changed": 0}


def test_diff_without_parent(client, users, v1):
    assert client.get(f"/api/versions/{v1['id']}/diff", headers=users["viewer"]).status_code == 400


# ---------- Issues ----------


def test_issue_lifecycle(client, users, model_id, v1):
    vp = {"camera": {"pos": [1, 2, 3], "target": [0, 0, 0]}, "selected_guids": ["abc"]}
    r = client.post(
        f"/api/models/{model_id}/issues",
        json={
            "title": "Devor noto'g'ri",
            "version_id": v1["id"],
            "viewpoint": vp,
            "assignee_id": users["ids"]["engineer"],
            "priority": "high",
        },
        headers=users["viewer"],
    )
    assert r.status_code == 201, r.text
    issue = r.json()
    assert issue["status"] == "open" and issue["viewpoint"] == vp
    assert issue["assignee_username"] == "engineer"

    # outsider ko'ra olmaydi
    assert client.get(f"/api/issues/{issue['id']}", headers=users["outsider"]).status_code == 403

    # izoh
    r = client.post(
        f"/api/issues/{issue['id']}/comments", json={"body": "Tuzatdim"}, headers=users["engineer"]
    )
    assert r.status_code == 201
    assert r.json()["comments"][0]["author_username"] == "engineer"

    # ijrochi holatni o'zgartiradi; begona a'zo (approver emas) o'zgartira olmaydi
    r = client.patch(
        f"/api/issues/{issue['id']}", json={"status": "resolved"}, headers=users["engineer"]
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    # viewer muallif — yopa oladi
    r = client.patch(
        f"/api/issues/{issue['id']}", json={"status": "closed"}, headers=users["viewer"]
    )
    assert r.status_code == 200

    r = client.get(f"/api/models/{model_id}/issues?status_filter=closed", headers=users["viewer"])
    assert [i["id"] for i in r.json()] == [issue["id"]]
    assert r.json()[0]["comment_count"] == 1


def test_issue_update_permission(client, users, model_id, admin):
    from conftest import login, make_user

    uid = make_user(client, admin, "other")
    client.put(
        f"/api/projects/{users['project_id']}/members",
        json={"user_id": uid, "role": "engineer"},
        headers=admin,
    )
    other = login(client, "other", "pass1234")
    issue = client.post(
        f"/api/models/{model_id}/issues", json={"title": "X"}, headers=users["viewer"]
    ).json()
    assert (
        client.patch(
            f"/api/issues/{issue['id']}", json={"status": "closed"}, headers=other
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/issues/{issue['id']}", json={"status": "closed"}, headers=users["approver"]
        ).status_code
        == 200
    )


def test_issue_bad_refs(client, users, model_id):
    r = client.post(
        f"/api/models/{model_id}/issues",
        json={"title": "X", "version_id": 999},
        headers=users["viewer"],
    )
    assert r.status_code == 400
    r = client.post(
        f"/api/models/{model_id}/issues",
        json={"title": "X", "assignee_id": 999},
        headers=users["viewer"],
    )
    assert r.status_code == 400


# ---------- BCF ----------


def test_bcf_export_import_roundtrip(client, users, model_id, v1, tmp_path):
    import io
    import zipfile

    vp = {
        "camera": {
            "space": "ifc",
            "position": [10, -20, 5],
            "target": [0, 0, 2],
            "projection": "Perspective",
        },
        "selected_guids": ["abc", "def"],
        "section": [{"origin": [0, 0, 1], "normal": [0, 0, 1]}],
    }
    i1 = client.post(
        f"/api/models/{model_id}/issues",
        json={
            "title": "To'g'on yorig'i",
            "description": "Tavsif",
            "priority": "high",
            "version_id": v1["id"],
            "viewpoint": vp,
            "assignee_id": users["ids"]["engineer"],
        },
        headers=users["viewer"],
    ).json()
    client.post(
        f"/api/issues/{i1['id']}/comments",
        json={"body": "Ko'rib chiqing", "viewpoint": vp},
        headers=users["approver"],
    )
    client.patch(
        f"/api/issues/{i1['id']}", json={"status": "in_progress"}, headers=users["approver"]
    )
    client.post(
        f"/api/models/{model_id}/issues", json={"title": "Ikkinchi"}, headers=users["viewer"]
    )

    r = client.get(f"/api/models/{model_id}/issues/bcf", headers=users["viewer"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "bcf.version" in names and sum(n.endswith("/markup.bcf") for n in names) == 2
    markup = next(
        z.read(n).decode()
        for n in names
        if n.endswith("/markup.bcf") and "Ikkinchi" not in z.read(n).decode()
    )
    assert (
        'TopicStatus="InProgress"' in markup
        and "<Priority>High</Priority>" in markup
        and "<AssignedTo>engineer</AssignedTo>" in markup
    )
    assert "<Comment>Ko'rib chiqing</Comment>" in markup
    vpx = next(
        z.read(n).decode()
        for n in names
        if n.endswith("/viewpoint.bcfv") and "abc" in z.read(n).decode()
    )
    assert '<Component IfcGuid="abc" />' in vpx or 'IfcGuid="abc"' in vpx
    assert "<CameraViewPoint>" in vpx and "<ClippingPlane>" in vpx

    # Qayta import → mavjudlar yangilanadi, yangi yaratilmaydi
    r = client.post(
        f"/api/models/{model_id}/issues/bcf",
        files={"file": ("issues.bcfzip", r.content, "application/zip")},
        headers=users["engineer"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 0, "updated": 2}
    assert len(client.get(f"/api/models/{model_id}/issues", headers=users["viewer"]).json()) == 2
    # izohlar takrorlanmagan
    assert (
        client.get(f"/api/issues/{i1['id']}", headers=users["viewer"]).json()["comment_count"] == 1
    )


def test_bcf_import_external(client, users, model_id):
    import io
    import zipfile

    guid = "11111111-2222-3333-4444-555555555555"
    markup = f"""<?xml version="1.0" encoding="UTF-8"?>
<Markup><Topic Guid="{guid}" TopicType="Clash" TopicStatus="Active"><Title>Solibri clash</Title><Priority>Major</Priority>
<CreationDate>2026-03-01T10:00:00Z</CreationDate><CreationAuthor>solibri@x.uz</CreationAuthor><Description>Quvur devor bilan kesishadi</Description></Topic>
<Comment Guid="aaaa"><Date>2026-03-02T10:00:00Z</Date><Author>rev@x.uz</Author><Comment>Tekshirildi</Comment></Comment>
<Viewpoints Guid="bbbb"><Viewpoint>viewpoint.bcfv</Viewpoint></Viewpoints></Markup>"""
    vpx = """<?xml version="1.0"?><VisualizationInfo Guid="bbbb"><Components><Selection><Component IfcGuid="1co$qRc3HNQhvxx7DQ$zKf"/></Selection></Components>
<PerspectiveCamera><CameraViewPoint><X>5</X><Y>-10</Y><Z>3</Z></CameraViewPoint><CameraDirection><X>0</X><Y>1</Y><Z>0</Z></CameraDirection><CameraUpVector><X>0</X><Y>0</Y><Z>1</Z></CameraUpVector><FieldOfView>60</FieldOfView></PerspectiveCamera></VisualizationInfo>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bcf.version", '<?xml version="1.0"?><Version VersionId="2.1"/>')
        z.writestr(f"{guid}/markup.bcf", markup)
        z.writestr(f"{guid}/viewpoint.bcfv", vpx)
    r = client.post(
        f"/api/models/{model_id}/issues/bcf",
        files={"file": ("ext.bcfzip", buf.getvalue(), "application/zip")},
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json() == {"created": 1, "updated": 0}
    issues = client.get(f"/api/models/{model_id}/issues", headers=users["viewer"]).json()
    assert (
        issues[0]["title"] == "Solibri clash"
        and issues[0]["status"] == "in_progress"
        and issues[0]["priority"] == "high"
    )
    full = client.get(f"/api/issues/{issues[0]['id']}", headers=users["viewer"]).json()
    assert full["viewpoint"]["selected_guids"] == ["1co$qRc3HNQhvxx7DQ$zKf"]
    assert full["viewpoint"]["camera"]["target"] == [5, 0, 3]
    assert full["comments"][0]["body"].startswith("Tekshirildi")
    # viewer import qila olmaydi; yaroqsiz fayl 400
    assert (
        client.post(
            f"/api/models/{model_id}/issues/bcf",
            files={"file": ("x.bcfzip", b"junk", "application/zip")},
            headers=users["viewer"],
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/models/{model_id}/issues/bcf",
            files={"file": ("x.bcfzip", b"junk", "application/zip")},
            headers=users["engineer"],
        ).status_code
        == 400
    )


# ---------- Saqlangan ko'rinishlar ----------


def test_saved_views(client, users, model_id):
    vp = {
        "camera": {"space": "ifc", "position": [1, 2, 3], "target": [0, 0, 0]},
        "selected_guids": [],
    }
    r = client.put(
        f"/api/models/{model_id}/views",
        json={"name": "Turbina zali", "viewpoint": vp},
        headers=users["viewer"],
    )
    assert r.status_code == 200 and r.json()["author_username"] == "viewer"
    vid = r.json()["id"]
    # bir xil nom: boshqa oddiy a'zo ustidan yoza olmaydi; muallif/tasdiqlovchi — yangilaydi
    vp2 = {**vp, "selected_guids": ["x"]}
    r = client.put(
        f"/api/models/{model_id}/views",
        json={"name": "Turbina zali", "viewpoint": vp2},
        headers=users["engineer"],
    )
    assert r.status_code == 403
    r = client.put(
        f"/api/models/{model_id}/views",
        json={"name": "Turbina zali", "viewpoint": vp2},
        headers=users["approver"],
    )
    assert r.json()["id"] == vid and r.json()["viewpoint"]["selected_guids"] == ["x"]
    assert len(client.get(f"/api/models/{model_id}/views", headers=users["viewer"]).json()) == 1
    assert client.get(f"/api/models/{model_id}/views", headers=users["outsider"]).status_code == 403
    # o'chirish: muallif (viewer) yoki tasdiqlovchi; muhandis (muallif emas) — yo'q
    assert client.delete(f"/api/views/{vid}", headers=users["engineer"]).status_code == 403
    assert client.delete(f"/api/views/{vid}", headers=users["viewer"]).status_code == 204
    assert client.get(f"/api/models/{model_id}/views", headers=users["viewer"]).json() == []
