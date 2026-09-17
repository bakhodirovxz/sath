# FreeCAD ichida (GUI siz) ishga tushiriladi:
#   "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" desktop\tests\fc_headless.py
# Tekshiradi: GES obyektlar, IFC eksport (eski eksporter), NativeIFC ochish/kengaytirish/round-trip (GUID lar).
import os
import pathlib
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "desktop", "GesWorkbench"))
OUT = os.path.join(tempfile.gettempdir(), "sath")
os.makedirs(OUT, exist_ok=True)

import FreeCAD  # noqa: E402
import ifcopenshell  # noqa: E402
import ifcopenshell.util.element  # noqa: E402
from ges_workbench import ges_objects, ifc_io  # noqa: E402


def psets(path):
    f = ifcopenshell.open(path)
    return [
        (
            p.is_a(),
            p.Name,
            {
                k: v
                for k, v in ifcopenshell.util.element.get_psets(p).items()
                if k.startswith("Pset_GES")
            },
        )
        for p in f.by_type("IfcProduct")
    ]


ok = True
try:
    doc = FreeCAD.newDocument("A")
    for k in ges_objects.OBJECTS:
        o = ges_objects.make(k)
        assert not o.Shape.isNull() and o.IfcProperties, k
    out = os.path.join(OUT, "fc_new.ifc")
    ifc_io.save_ifc(doc, pathlib.Path(out))
    rows = psets(out)
    assert sum(1 for r in rows if r[2]) == len(ges_objects.OBJECTS), rows
    print("1) yangi hujjat -> IFC: OK", len(rows), "element")
except Exception:
    ok = False
    traceback.print_exc()

try:
    src = os.path.join(ROOT, "docs", "samples", "namuna_ges_v1.ifc")
    doc = ifc_io.open_ifc(pathlib.Path(src))
    assert ifc_io.project_object(doc) is doc
    n0 = len(doc.Objects)
    ifc_io.expand_all(doc)
    assert len(doc.Objects) >= 20, len(doc.Objects)
    ges_objects.make("GES_Turbine", "Turbina 4")
    out2 = os.path.join(OUT, "fc_roundtrip.ifc")
    ifc_io.save_ifc(doc, pathlib.Path(out2))
    rows = psets(out2)
    t4 = [r for r in rows if r[1] and r[1].startswith("Turbina 4")]
    assert t4 and t4[0][2].get("Pset_GES_Turbine"), t4
    g0 = {p.GlobalId for p in ifcopenshell.open(src).by_type("IfcProduct")}
    g1 = {p.GlobalId for p in ifcopenshell.open(out2).by_type("IfcProduct")}
    assert g0 <= g1, "GUID lar yo'qoldi"
    print(
        "2) NativeIFC round-trip: OK",
        n0,
        "->",
        len(doc.Objects),
        "obyekt,",
        len(rows),
        "element, GUID saqlangan",
    )
except Exception:
    ok = False
    traceback.print_exc()

# 3) DWG konverter: ~/Tools/libredwg yoki dastur ichidagi tools/libredwg topilib sozlamaga yoziladi;
#    topilsa DXF → DWG → DXF aylanma (FreeCAD ning o'z importDWG.convertToDxf orqali)
try:
    from ges_workbench import converters

    path = converters.ensure_dwg_converter(force=True)
    if not path:
        print("3) DWG konverter yo'q — o'tkazib yuborildi (~/Tools/libredwg/dwg2dxf.exe qo'ying)")
    else:
        import importDWG

        out = importDWG.convertToDxf(
            os.path.join(HERE, "Namuna.dwg")
        )  # ezdxf + dxf2dwg bilan yasalgan
        assert out and os.path.getsize(out) > 1000, out
        import importDXF
        from ges_workbench import dxf_edit, dxf_prepare

        d2 = FreeCAD.newDocument("dwg")
        if dxf_prepare.ensure_ezdxf():
            # tahrirlanadigan import: 3DFACE → yuza, yopiq polilinya → Draft Wire, qatlamlar
            d2, stats = dxf_edit.import_file(out, d2)
            kinds = sorted(getattr(getattr(o, "Proxy", None), "Type", o.TypeId) for o in d2.Objects)
            assert "Wire" in kinds and "Layer" in kinds, kinds
            assert any(o.Label.startswith("Yuza") for o in d2.Objects), kinds
        else:
            stats = {"ezdxf": "yo'q — FreeCAD importeri"}
            importDXF.insert(out, d2.Name)
        assert len(d2.Objects) >= 1, "DXF dan obyekt chiqmadi"
        print(
            "3) DWG konverter:",
            path,
            "— Namuna.dwg ochildi,",
            len(d2.Objects),
            "obyekt;",
            stats,
        )
except Exception:
    ok = False
    traceback.print_exc()

# 4) FBX (assimp-py, vendor) — Fayl → Ochish orqali (FreeCAD.loadFile import turlaridan foydalanadi)
try:
    from ges_workbench import assimp_load, mesh_open

    mesh_open._ensure_vendor()
    if assimp_load.available():
        FreeCAD.loadFile(os.path.join(HERE, "Namuna.fbx"))
        d4 = FreeCAD.ActiveDocument
        meshes = [o for o in d4.Objects if o.TypeId == "Mesh::Feature"]
        assert meshes and meshes[0].Mesh.CountFacets == 12, [o.TypeId for o in d4.Objects]
        print("4) FBX (assimp): OK", meshes[0].Label, meshes[0].Mesh.CountFacets, "uchburchak")
    else:
        print("4) FBX: assimp-py yo'q — o'tkazib yuborildi")
except Exception:
    ok = False
    traceback.print_exc()

print("NATIJA:", "OK" if ok else "XATO")
