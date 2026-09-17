"""Qoralama obyektlar: CRUD, ruxsatlar, IFC ga commit (yangi versiya, Pset, joylashuv)."""

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import pytest
from conftest import upload
from ges_server.models import storage

BOX = {
    "vertices": [
        [0, 0, 0],
        [4, 0, 0],
        [4, 2, 0],
        [0, 2, 0],
        [0, 0, 3],
        [4, 0, 3],
        [4, 2, 3],
        [0, 2, 3],
    ],
    "faces": [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ],
}


@pytest.fixture
def model_id(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models", json={"name": "M"}, headers=users["engineer"]
    )
    return r.json()["id"]


def test_draft_crud_and_permissions(client, users, model_id):
    body = {
        "kind": "dam",
        "name": "To'g'on A",
        "params": {"length": 4},
        "transform": {"x": 1, "y": 2, "z": 0, "rz": 0},
        "psets": {"Pset_GES_Dam": {"Balandlik_m": 3.0}},
        "mesh": BOX,
    }
    assert (
        client.post(
            f"/api/models/{model_id}/drafts", json=body, headers=users["viewer"]
        ).status_code
        == 403
    )
    r = client.post(f"/api/models/{model_id}/drafts", json=body, headers=users["engineer"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["kind"] == "dam" and d["has_mesh"] and d["author_username"] == "engineer"
    lst = client.get(f"/api/models/{model_id}/drafts", headers=users["viewer"]).json()
    assert [x["id"] for x in lst] == [d["id"]]
    r = client.patch(
        f"/api/drafts/{d['id']}",
        json={"name": "To'g'on B", "transform": {"x": 5, "y": 2, "z": 0, "rz": 45}},
        headers=users["engineer"],
    )
    assert (
        r.status_code == 200
        and r.json()["name"] == "To'g'on B"
        and r.json()["transform"]["rz"] == 45
    )
    assert (
        client.patch(
            f"/api/drafts/{d['id']}", json={"name": "x"}, headers=users["viewer"]
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/models/{model_id}/drafts", headers=users["outsider"]).status_code == 403
    )
    assert client.delete(f"/api/drafts/{d['id']}", headers=users["viewer"]).status_code == 403
    assert client.delete(f"/api/drafts/{d['id']}", headers=users["engineer"]).status_code == 204
    assert client.get(f"/api/models/{model_id}/drafts", headers=users["viewer"]).json() == []


def test_commit_drafts_creates_version_with_elements(client, users, model_id, ifc_file):
    v1 = upload(client, users["engineer"], model_id, ifc_file, "asos").json()
    # commit uchun qoralama yo'q
    assert (
        client.post(
            f"/api/models/{model_id}/drafts/commit", json={}, headers=users["engineer"]
        ).status_code
        == 400
    )
    for name, kind in (("To'g'on", "dam"), ("Quvur", "penstock")):
        r = client.post(
            f"/api/models/{model_id}/drafts",
            json={
                "kind": kind,
                "name": name,
                "transform": {"x": 10, "y": 0, "z": 0, "rz": 90},
                "psets": {"Pset_GES_Dam": {"Balandlik_m": 3.0, "Turi": "beton"}}
                if kind == "dam"
                else {},
                "mesh": BOX,
            },
            headers=users["engineer"],
        )
        assert r.status_code == 201
    assert (
        client.post(
            f"/api/models/{model_id}/drafts/commit", json={}, headers=users["viewer"]
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/models/{model_id}/drafts/commit",
        json={"message": "web dan"},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["number"] == 2 and v2["parent_id"] == v1["id"] and len(v2["guids"]) == 2
    assert v2["meta"]["element_count"] == v1["meta"]["element_count"] + 2
    # qoralamalar o'chirildi
    assert client.get(f"/api/models/{model_id}/drafts", headers=users["viewer"]).json() == []
    # IFC da: IfcWall + Pset, IfcPipeSegment, joylashuv burilgan
    f = ifcopenshell.open(str(storage.resolve(v2["file_sha256"])))
    wall = next(e for e in f.by_type("IfcWall") if e.Name == "To'g'on")
    ps = ifcopenshell.util.element.get_psets(wall)
    assert (
        ps["Pset_GES_Dam"]["Balandlik_m"] == 3.0 and ps["Pset_GES_Object"]["Manba"] == "Sath web"
    )
    assert f.by_type("IfcPipeSegment")[0].Name == "Quvur"
    assert ifcopenshell.util.element.get_container(wall) is not None
    # tarix saqlangan: 2 versiya
    assert len(client.get(f"/api/models/{model_id}/versions", headers=users["viewer"]).json()) == 2


def test_edit_and_delete_existing_elements(client, users, model_id, ifc_file):
    """Mavjud elementni tahrirlash (kind mesh + source_guid): GUID, klass, konteyner, Pset lar saqlanadi,
    geometriya/joylashuv/nom yangilanadi; kind deleted — element olib tashlanadi; diff «o'zgargan/o'chgan»."""
    upload(client, users["engineer"], model_id, ifc_file, "asos")
    # asos: ikkita web element (geometriya + Pset bilan) — v2
    for name in ("Devor A", "Devor B"):
        client.post(
            f"/api/models/{model_id}/drafts",
            json={
                "kind": "dam",
                "name": name,
                "transform": {"x": 0, "y": 0, "z": 0},
                "psets": {"Pset_GES_Dam": {"Balandlik_m": 3.0, "Turi": "beton"}},
                "mesh": BOX,
            },
            headers=users["engineer"],
        )
    v1 = client.post(
        f"/api/models/{model_id}/drafts/commit", json={}, headers=users["engineer"]
    ).json()
    f1 = ifcopenshell.open(str(storage.resolve(v1["file_sha256"])))
    walls = [e for e in f1.by_type("IfcWall") if e.Representation]
    assert len(walls) == 2
    edit, gone = walls[0], walls[1]
    n_before = len(f1.by_type("IfcProduct"))
    r = client.post(
        f"/api/models/{model_id}/drafts",
        json={
            "kind": "mesh",
            "name": "Devor (surilgan)",
            "ifc_class": "IfcWall",
            "source_guid": edit.GlobalId,
            "transform": {"x": 5, "y": 0, "z": 0, "rz": 0},
            "psets": {"Pset_GES_Edit": {"Izoh": "web"}},
            "mesh": BOX,
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["source_guid"] == edit.GlobalId and r.json()["mesh"] == BOX
    r = client.post(
        f"/api/models/{model_id}/drafts",
        json={"kind": "deleted", "name": gone.Name or "", "source_guid": gone.GlobalId},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    r = client.post(f"/api/models/{model_id}/drafts/commit", json={}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert "o'zgardi" in v2["message"] and "o'chirildi" in v2["message"]
    f2 = ifcopenshell.open(str(storage.resolve(v2["file_sha256"])))
    assert len(f2.by_type("IfcProduct")) == n_before - 1
    el = f2.by_guid(edit.GlobalId)
    assert el.is_a("IfcWall") and el.Name == "Devor (surilgan)"
    ps = ifcopenshell.util.element.get_psets(el)
    assert ps["Pset_GES_Edit"]["Izoh"] == "web" and "(tahrir)" in ps["Pset_GES_Object"]["Manba"]
    # asl Pset lar ko'chgan
    orig_ps = ifcopenshell.util.element.get_psets(edit, psets_only=True, should_inherit=False)
    for name in orig_ps:
        assert name in ps, name
    assert ifcopenshell.util.element.get_container(el) is not None
    # joylashuv x=5 ga
    m = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)
    scale = ifcopenshell.util.unit.calculate_unit_scale(f2)  # fayl birligi (mm bo'lsa 0.001)
    assert abs(m[0][3] * scale - 5) < 1e-6
    with pytest.raises(RuntimeError):
        f2.by_guid(gone.GlobalId)
    # rang saqlangan (asl elementda IfcSurfaceStyle bo'lsa)
    from ges_server.models.drafts import _surface_color

    if _surface_color(edit) is not None:
        assert _surface_color(el) == _surface_color(edit)
    d = client.get(f"/api/versions/{v2['id']}/diff", headers=users["viewer"]).json()
    assert edit.GlobalId in {x["guid"] for x in d["changed"]}
    assert gone.GlobalId in {x["guid"] for x in d["deleted"]}


def test_commit_without_base_version_creates_new_ifc(client, users, model_id):
    client.post(
        f"/api/models/{model_id}/drafts",
        json={"kind": "cube", "name": "Kub", "mesh": BOX},
        headers=users["engineer"],
    )
    r = client.post(
        f"/api/models/{model_id}/drafts/commit",
        json={"keep_drafts": True},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    assert (
        r.json()["number"] == 1
        and r.json()["parent_id"] is None
        and r.json()["meta"]["schema"] == "IFC4"
    )
    assert len(client.get(f"/api/models/{model_id}/drafts", headers=users["viewer"]).json()) == 1


def test_import_mesh_obj_glb_to_version(client, users, model_id, tmp_path):
    """Blender/3ds Max eksporti (OBJ, GLB) → IFC versiya: obyekt nomlari saqlanadi, birlik, ustiga qo'shish."""
    import trimesh

    s = trimesh.Scene()
    s.add_geometry(trimesh.creation.box((4, 2, 3)), node_name="Devor", geom_name="Devor")
    s.add_geometry(
        trimesh.creation.cylinder(radius=1, height=5),
        node_name="Quvur",
        geom_name="Quvur",
        transform=trimesh.transformations.translation_matrix([10, 0, 0]),
    )
    obj = tmp_path / "blender.obj"
    s.export(str(obj))
    with open(obj, "rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            files={"file": ("blender.obj", fh, "application/octet-stream")},
            data={"message": "Blender dan", "unit": "cm"},
            headers=users["engineer"],
        )
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["number"] == 1 and v1["imported"] == 2 and set(v1["names"]) == {"Devor", "Quvur"}
    assert v1["meta"]["element_count"] >= 3 and v1["file_name"] == "blender.ifc"
    f = ifcopenshell.open(str(storage.resolve(v1["file_sha256"])))
    names = {e.Name for e in f.by_type("IfcProduct")}
    assert {"Devor", "Quvur"} <= names
    assert f.by_type("IfcPipeSegment")[0].Name == "Quvur"  # nom bo'yicha tur
    # GLB (Y yuqoriga) joriy model ustiga → v2, elementlar ko'payadi
    glb = tmp_path / "max.glb"
    s.export(str(glb))
    with open(glb, "rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            files={"file": ("max.glb", fh, "application/octet-stream")},
            data={"y_up": "true", "onto_current": "true"},
            headers=users["engineer"],
        )
    assert r.status_code == 201, r.text
    assert r.json()["number"] == 2 and r.json()["parent_id"] == v1["id"]
    assert r.json()["meta"]["element_count"] == v1["meta"]["element_count"] + 2
    # ruxsat, format
    with open(obj, "rb") as fh:
        assert (
            client.post(
                f"/api/models/{model_id}/versions/import-mesh",
                files={"file": ("x.obj", fh, "application/octet-stream")},
                headers=users["viewer"],
            ).status_code
            == 403
        )
    r = client.post(
        f"/api/models/{model_id}/versions/import-mesh",
        files={"file": ("scene.fbx", b"xx", "application/octet-stream")},
        headers=users["engineer"],
    )
    assert r.status_code == 400  # buzuq FBX — assimp xatosi foydalanuvchiga tushunarli
    assert "FBX" in r.json()["detail"] or "glTF" in r.json()["detail"]


def test_import_colors_units_names_and_export(client, users, model_id, tmp_path):
    """OBJ+MTL rang → IfcSurfaceStyle, nom bo'yicha GES turi (To'g'on → IfcWall + Pset_GES_Dam), DXF birlik,
    IFC → glb/obj eksport."""
    from ges_server.models import mesh_import

    assert mesh_import.classify("Togon_asosiy")[0] == "IfcWall"
    assert mesh_import.classify("Penstock_1")[0] == "IfcPipeSegment"
    assert mesh_import.classify("Cube.001")[0] == "IfcBuildingElementProxy"
    (tmp_path / "m.mtl").write_text("newmtl beton\nKd 0.6 0.6 0.55\n")
    (tmp_path / "scene.obj").write_text(
        "mtllib m.mtl\no Togon\nusemtl beton\nv 0 0 0\nv 40 0 0\nv 40 10 0\nv 0 10 0\nv 0 0 30\nv 40 0 30\nv 40 10 30\nv 0 10 30\n"
        "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\no Quvur_1\nv 50 0 0\nv 60 0 0\nv 60 3 0\nv 50 3 3\nf 9 10 11\nf 9 11 12\n"
    )
    import zipfile

    with zipfile.ZipFile(tmp_path / "scene.zip", "w") as z:  # obj + mtl birga (rang uchun)
        z.write(tmp_path / "scene.obj", "scene.obj")
        z.write(tmp_path / "m.mtl", "m.mtl")
    with open(tmp_path / "scene.zip", "rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            files={"file": ("scene.zip", fh, "application/zip")},
            headers=users["engineer"],
        )
    assert r.status_code == 201, r.text
    v = r.json()
    f = ifcopenshell.open(str(storage.resolve(v["file_sha256"])))
    wall = f.by_type("IfcWall")[0]
    assert wall.Name == "Togon"
    ps = ifcopenshell.util.element.get_psets(wall)
    assert ps["Pset_GES_Dam"]["Balandlik_m"] == 30.0 and ps["Pset_GES_Dam"]["Uzunlik_m"] == 40.0
    assert f.by_type("IfcPipeSegment")[0].Name == "Quvur_1"
    styles = f.by_type("IfcSurfaceStyle")
    assert styles and any(abs(x.Styles[0].SurfaceColour.Red - 0.6) < 1e-6 for x in styles)
    # DXF birlik: $INSUNITS = 4 (mm) → 1000 mm = 1 m
    dxf = tmp_path / "plan.dxf"
    dxf.write_text(
        "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\n3DFACE\n8\n0\n"
        "10\n0\n20\n0\n30\n0\n11\n1000\n21\n0\n31\n0\n12\n1000\n22\n1000\n32\n0\n13\n0\n23\n1000\n33\n0\n0\nENDSEC\n0\nEOF\n"
    )
    assert mesh_import.detect_unit(dxf) == "mm"
    # eksport: glb va obj
    r = client.get(
        f"/api/versions/{v['id']}/export", params={"fmt": "glb"}, headers=users["viewer"]
    )
    assert r.status_code == 200 and r.content[:4] == b"glTF"
    r = client.get(
        f"/api/versions/{v['id']}/export", params={"fmt": "obj"}, headers=users["viewer"]
    )
    assert r.status_code == 200 and b"Togon" in r.content
    assert (
        client.get(
            f"/api/versions/{v['id']}/export", params={"fmt": "fbx"}, headers=users["viewer"]
        ).status_code
        == 400
    )
    fm = client.get("/api/import/formats", headers=users["viewer"]).json()
    assert ".obj" in fm["direct"] and "assimp" in fm


def test_import_dxf_3dface_and_extrude_and_dwg(client, users, model_id, tmp_path):
    """DXF: 3DFACE → yuza, yopiq LWPOLYLINE → extrude; qatlam = nom (GES turi), ACI rang; handle=0 tuzatiladi;
    DWG — konverter (dwg2dxf) topilsa aylanma sinov."""
    import shutil
    import subprocess
    from pathlib import Path

    import ezdxf
    from ges_server.models import mesh_import

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4  # mm
    doc.layers.add("TOGON", color=1)
    doc.layers.add("DEVOR", color=3)
    msp = doc.modelspace()
    msp.add_3dface(
        [(0, 0, 0), (4000, 0, 0), (4000, 0, 3000), (0, 0, 3000)], dxfattribs={"layer": "TOGON"}
    )
    msp.add_lwpolyline(
        [(0, 0), (5000, 0), (5000, 200), (0, 200)], close=True, dxfattribs={"layer": "DEVOR"}
    )
    dxf = tmp_path / "plan.dxf"
    doc.saveas(dxf)

    objs = mesh_import.load_objects(dxf, extrude_m=3.0)
    by = {o["name"]: o for o in objs}
    assert by["TOGON"]["ifc_class"] == "IfcWall" and by["TOGON"]["kind"] == "dam"
    assert by["TOGON"]["color"] == (1.0, 0.0, 0.0)
    assert by["TOGON"]["psets"]["Pset_GES_Import"]["Birlik"] == "mm"
    assert len(by["DEVOR"]["mesh"]["faces"]) == 12  # extrude: 2 qopqoq + 4 yon × 2
    zs = [v[2] for v in by["DEVOR"]["mesh"]["vertices"]]
    assert abs((max(zs) - min(zs)) - 3.0) < 1e-6  # natija metrda (3000 mm → 3 m)

    # dwg2dxf chiqarganidek handle=0 bo'lgan DXF ham ochiladi
    txt = dxf.read_text(encoding="utf-8").splitlines()
    for i in range(0, len(txt) - 1, 2):
        if txt[i].strip() == "5" and txt[i - 1].strip() == "ENDBLK":
            txt[i + 1] = "0"
            break
    bad = tmp_path / "bad.dxf"
    bad.write_text("\n".join(txt) + "\n", encoding="utf-8")
    assert {o["name"] for o in mesh_import.load_objects(bad, extrude_m=3.0)} == {"TOGON", "DEVOR"}

    # Extrude ko'rsatilmasa 2D kontur tashlab ketiladi, 3DFACE qoladi
    assert {o["name"] for o in mesh_import.load_objects(dxf)} == {"TOGON"}

    # API orqali (extrude_m formasi)
    with dxf.open("rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            headers=users["engineer"],
            data={"message": "dxf", "extrude_m": "3"},
            files={"file": ("plan.dxf", fh, "application/octet-stream")},
        )
    assert r.status_code == 201, r.text
    assert r.json()["imported"] == 2

    # DWG — konverter mavjud bo'lsa: DXF → DWG (dxf2dwg) → import (dwg2dxf)
    tools = mesh_import.tools()
    dwg2dxf = tools.get("dwg2dxf")
    if not dwg2dxf:
        return
    dxf2dwg = shutil.which("dxf2dwg", path=str(Path(dwg2dxf).parent))
    if not dxf2dwg:
        return
    dwg = tmp_path / "plan.dwg"
    subprocess.run([dxf2dwg, "-y", "-o", str(dwg), str(dxf)], capture_output=True, timeout=120)
    if not dwg.exists():
        return
    objs = mesh_import.load_objects(dwg, extrude_m=3.0)
    assert {o["name"] for o in objs} == {"TOGON", "DEVOR"}
    assert objs[0]["psets"]["Pset_GES_Import"]["Manba"] == "dwg"


def test_dxf_flatten_copy_in_sync():
    """server/…/dxf_flatten.py — desktop dxf_prepare.py ning nusxasi (sarlavhadan tashqari bir xil bo'lsin)."""
    from pathlib import Path

    here = Path(__file__).resolve()
    desk = here.parents[2] / "desktop" / "GesWorkbench" / "ges_workbench" / "dxf_prepare.py"
    srv = here.parents[1] / "ges_server" / "models" / "dxf_flatten.py"
    if not desk.exists():
        pytest.skip("desktop papkasi yo'q")

    def body(p: Path) -> str:
        s = p.read_text(encoding="utf-8")
        return s[s.index("from __future__") :]

    assert body(desk) == body(srv), (
        "desktop/dxf_prepare.py va server/dxf_flatten.py farq qiladi — nusxalang"
    )


def test_import_fbx_3ds_via_assimp(client, users, model_id):
    """FBX / 3DS (Blender, 3ds Max) — assimp-py bilan (CLI shart emas): obyekt nomi, rangi, uchburchaklar."""
    from pathlib import Path

    from ges_server.models import assimp_load, mesh_import

    assert assimp_load.available(), "assimp-py o'rnatilmagan"
    samples = Path(__file__).parent / "samples"
    fbx = mesh_import.load_objects(samples / "box.fbx", y_up=True)
    assert len(fbx) == 1 and len(fbx[0]["mesh"]["faces"]) == 12
    assert fbx[0]["color"] and fbx[0]["color"][0] > 0.9  # sarg'ish material (COLOR_DIFFUSE)
    tds = mesh_import.load_objects(samples / "cube.3ds")
    assert tds[0]["name"] == "Quader01" and len(tds[0]["mesh"]["faces"]) == 12
    with (samples / "box.fbx").open("rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            headers=users["engineer"],
            data={"message": "fbx", "y_up": "true"},
            files={"file": ("box.fbx", fh, "application/octet-stream")},
        )
    assert r.status_code == 201, r.text
    assert r.json()["imported"] == 1
    r = client.get("/api/import/formats", headers=users["engineer"])
    assert r.json()["assimp"]["available"] is True and ".fbx" in r.json()["assimp"]["formats"]


def test_import_step_via_ocp(client, users, model_id):
    """STEP (SolidWorks/Inventor/FreeCAD) — OpenCASCADE: har jism alohida, nomi va rangi; birlik mm."""
    from pathlib import Path

    from ges_server.models import cad_import, mesh_import

    if not cad_import.available():
        pytest.skip("cadquery-ocp o'rnatilmagan")
    step = Path(__file__).parent / "samples" / "namuna.step"
    objs = mesh_import.load_objects(step)
    by = {o["name"]: o for o in objs}
    assert by["Togon_devor"]["kind"] == "dam" and by["Togon_devor"]["color"] == (1.0, 0.0, 0.0)
    assert by["Penstock_1"]["ifc_class"] == "IfcPipeSegment"
    assert by["Togon_devor"]["psets"]["Pset_GES_Import"]["Birlik"] == "mm"
    zs = [v[2] for v in by["Togon_devor"]["mesh"]["vertices"]]
    assert abs((max(zs) - min(zs)) - 3.0) < 1e-6  # 3000 mm → 3 m
    with step.open("rb") as fh:
        r = client.post(
            f"/api/models/{model_id}/versions/import-mesh",
            headers=users["engineer"],
            data={"message": "step"},
            files={"file": ("namuna.step", fh, "application/octet-stream")},
        )
    assert r.status_code == 201, r.text
    assert r.json()["meta"]["type_counts"].get("IfcPipeSegment") == 1


def test_image_underlay_crud(client, users, model_id):
    """Rasm asosi: yuklash → ro'yxat → joylashuv/masshtab o'zgartirish → rasm olish → o'chirish."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (200, 180, 150)).save(buf, format="PNG")
    r = client.post(
        f"/api/models/{model_id}/underlays",
        headers=users["engineer"],
        data={"name": "Plan foto", "width_m": "120", "x": "10", "y": "5"},
        files={"file": ("plan.png", buf.getvalue(), "image/png")},
    )
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["width_m"] == 120 and abs(u["height_m"] - 60) < 1e-6 and u["url"].endswith("/image")
    assert (
        client.get(f"/api/models/{model_id}/underlays", headers=users["viewer"]).json()[0]["name"]
        == "Plan foto"
    )
    r = client.patch(
        f"/api/underlays/{u['id']}",
        headers=users["engineer"],
        json={"rotation_deg": 15, "opacity": 0.5, "z": 2},
    )
    assert r.status_code == 200 and r.json()["rotation_deg"] == 15 and r.json()["z"] == 2
    img = client.get(u["url"], headers=users["viewer"])
    assert img.status_code == 200 and img.headers["content-type"].startswith("image/")
    assert (
        client.patch(
            f"/api/underlays/{u['id']}", headers=users["viewer"], json={"x": 1}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/underlays/{u['id']}", headers=users["engineer"]).status_code == 204
    assert client.get(f"/api/models/{model_id}/underlays", headers=users["viewer"]).json() == []


def test_twin_preset_creates_model_site_and_photo(client, users):
    """Preset egizak: model + v1 IFC (Pset_GES_* — sim parametrlari), maydon pasporti, foto asosi."""
    project_id = users["project_id"]
    r = client.get("/api/twin/presets", headers=users["viewer"])
    assert r.status_code == 200 and any(p["id"] == "chorvoq" for p in r.json())
    r = client.post(
        f"/api/projects/{project_id}/twin", headers=users["engineer"], json={"preset": "chorvoq"}
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["elements"] >= 25 and t["model_name"].startswith("Chorvoq GES")
    g = client.get(f"/api/versions/{t['version_id']}/ges-params", headers=users["viewer"]).json()
    assert len(g["units"]) == 4 and g["dams"][0]["height_m"] == 168 and len(g["penstocks"]) == 2
    s = client.get(f"/api/projects/{project_id}/site", headers=users["viewer"]).json()
    assert (
        s["filled"]
        and s["values"]["normal_level_m"] == 890
        and s["values"]["dam_type"] == "rockfill"
    )
    if t["photo_underlay_id"]:
        us = client.get(f"/api/models/{t['model_id']}/underlays", headers=users["viewer"]).json()
        assert us and us[0]["vertical"] is True
    assert (
        client.post(
            f"/api/projects/{project_id}/twin", headers=users["viewer"], json={"preset": "chorvoq"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{project_id}/twin", headers=users["engineer"], json={"preset": "yoq"}
        ).status_code
        == 404
    )


def test_heightmap_of_twin(client, users):
    """Balandlik xaritasi: relyef + to'g'on ustki yuzasi (gerb 896 m markazda, ombor tubi pastroq)."""
    project_id = users["project_id"]
    t = client.post(
        f"/api/projects/{project_id}/twin",
        headers=users["engineer"],
        json={"preset": "chorvoq", "with_photo": False},
    ).json()
    r = client.get(f"/api/versions/{t['version_id']}/heightmap?nx=64", headers=users["viewer"])
    assert r.status_code == 200, r.text
    hm = r.json()
    nx = hm["nx"]
    assert (
        hm["ny"] == 64 and nx < 64 and len(hm["z"]) == nx * 64
    )  # kvadrat kataklar: uzun tomon (Y) 64
    assert abs(hm["dx"] - hm["dy"]) < 0.5
    i = int((0 - hm["x0"]) / hm["dx"])
    j_dam = int((0 - hm["y0"]) / hm["dy"])
    j_res = int((600 - hm["y0"]) / hm["dy"])
    z = hm["z"]
    assert abs(z[j_dam * nx + i] - 896) < 3  # to'g'on gerbi
    assert z[j_res * nx + i] < 800  # ombor tubi


def test_delete_model_with_sim_jobs(client, users):
    """Modelni o'chirish — simulyatsiya vazifalari/issue lar bo'lsa ham (FK) muammosiz."""
    project_id = users["project_id"]
    t = client.post(
        f"/api/projects/{project_id}/twin",
        headers=users["engineer"],
        json={"preset": "chorvoq", "with_photo": False},
    ).json()
    r = client.post(
        f"/api/models/{t['model_id']}/sim",
        headers=users["engineer"],
        json={"name": "s", "version_id": t["version_id"], "kind": "seismic", "params": {}},
    )
    assert r.status_code == 202, r.text
    # ikkinchi versiya (ota-bola zanjiri parent_id) — FK tartibi
    from pathlib import Path

    with (Path(__file__).parent / "samples" / "plan.png").open("rb") as fh:
        client.post(
            f"/api/models/{t['model_id']}/versions/import-image",
            headers=users["engineer"],
            data={"mode": "drawing", "width_m": "60"},
            files={"file": ("plan.png", fh, "image/png")},
        )
    assert (
        client.delete(f"/api/models/{t['model_id']}", headers=users["approver"]).status_code == 204
    )
    assert (
        client.get(f"/api/models/{t['model_id']}/versions", headers=users["viewer"]).status_code
        == 404
    )


def test_dem_grid_offline_mocked(monkeypatch, tmp_path):
    """DEM: plitka o'qish mock (internet siz) — panjara, burilish, mutlaq balandlik, IFC obyekt."""
    import numpy as np
    from ges_server.models import dem

    monkeypatch.setattr(
        dem, "_tile", lambda z, x, y: np.full((256, 256), 800.0) + np.arange(256)[None, :] * 0.5
    )
    obj, info = dem.terrain_object(41.62, 69.98, 1000, 2000, rotation_deg=-90, zoom=12, nx=20)
    assert obj["ifc_class"] == "IfcGeographicElement" and info["ny"] == 40 and info["tiles"] >= 1
    v = np.asarray(obj["mesh"]["vertices"])
    assert abs(v[:, 0].min() + 500) < 1 and abs(v[:, 1].max() - 1000) < 1
    assert 790 < obj["transform"]["z"] < 1000


def test_twin_maket_preset_and_transparency(client, users):
    """Ixcham maket (sxema 1–9): barcha presetlar pasporti chegaralarda; yarim shaffof mashina zali
    IfcSurfaceStyleRendering (Transparency) bilan; sim prefill pasportdan to'ladi."""
    from ges_server.models import twin_builder
    from ges_sim import schema, site

    for k in twin_builder.PRESETS:
        schema.parse(site.SITE_FIELDS, twin_builder.site_values(k))
    project_id = users["project_id"]
    r = client.post(
        f"/api/projects/{project_id}/twin", headers=users["engineer"], json={"preset": "maket"}
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["elements"] == 22 and d["site_filled"]
    f = ifcopenshell.open(
        str(
            storage.resolve(
                client.get(f"/api/versions/{d['version_id']}", headers=users["viewer"]).json()[
                    "file_sha256"
                ]
            )
        )
    )
    names = {e.Name for e in f.by_type("IfcProduct")}
    for n in (
        "3 Bosh quvur (penstock)",
        "4 Turbina",
        "5 Generator",
        "6 Chiqarish quvuri (draft tube)",
        "8 Boshqaruv xonasi (dispecher)",
    ):
        assert n in names
    assert sorted(round(s.Transparency, 2) for s in f.by_type("IfcSurfaceStyleRendering")) == [
        0.65,
        0.75,
    ]
    pf = client.get(
        f"/api/models/{d['model_id']}/sim/prefill?kind=flood&version_id={d['version_id']}",
        headers=users["viewer"],
    ).json()
    assert pf["site"]["crest_m"] == 245.0 and pf["site"]["initial_level_m"] == 240.0
