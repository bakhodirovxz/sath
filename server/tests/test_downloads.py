"""SRV-03: Content-Disposition — kirill nom, qo'shtirnoq, CR/LF (RFC 6266 / 5987)."""

from urllib.parse import unquote

import pytest
from conftest import upload
from ges_server.downloads import content_disposition


def _utf8_name(header: str) -> str:
    assert "filename*=UTF-8''" in header
    return unquote(header.split("filename*=UTF-8''", 1)[1])


@pytest.mark.parametrize(
    "name,expect",
    [
        ("Тўғон_v1.ifc", "Тўғон_v1.ifc"),
        ('a"b.csv', "ab.csv"),
        ("x\r\nSet-Cookie: y=1.csv", "xSet-Cookie: y=1.csv"),
        ("../../etc/passwd", "_.._etc_passwd"),
        ("", "download"),
    ],
)
def test_helper(name, expect):
    h = content_disposition(name)
    h.encode("latin-1")  # sarlavha latin-1 da kodlanishi shart
    assert "\r" not in h and "\n" not in h
    assert h.startswith("attachment; filename=\"")
    fallback = h.split('filename="', 1)[1].split('"', 1)[0]
    assert fallback.isascii() and '"' not in fallback
    assert _utf8_name(h) == expect


def test_cyrillic_model_downloads(client, users, ifc_file):
    name = 'Тўғон "A"\r\nX-Evil: 1'
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": name}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file).json()
    for url in (
        f"/api/versions/{v['id']}/file",
        f"/api/models/{mid}/issues/bcf",
        f"/api/versions/{v['id']}/assets/register?format=csv",
    ):
        r = client.get(url, headers=users["viewer"])
        assert r.status_code == 200, (url, r.text)
        cd = r.headers["content-disposition"]
        assert "x-evil" not in {k.lower() for k in r.headers}
        assert "Тўғон AX-Evil: 1" in _utf8_name(cd)
