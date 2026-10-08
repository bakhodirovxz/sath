"""K2: namuna GES → IFC saqlash → yangi sessiyada ochish → har GES obyekti kind/role/params tiklanadi (mesh qayta
qurilmaydi, GUID saqlanadi) → animate_hydro rollar orqali keyframe qo'yadi; rol yo'qolsa TwinBindingError (jim emas).
Eski model (Pset_SathParametric siz, docs/samples/namuna_ges_v1.ifc): Pset_GES_* dan tur, X bo'yicha rollar."""

import tempfile
from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def _hydro(n: int, guids: list) -> tuple[dict, dict]:
    series = {
        "level": [43.0 - 0.1 * i for i in range(n)], "turbine_flow": [120.0] * n,
        "spill": [0.0] * (n - 1) + [15.0], "head_net": [42.0] * n,
    }  # fmt: skip
    result = {"series": series, "units": [{"power_mw": [0.0] + [20.0] * (n - 1)} for _ in guids]}
    units = [
        {"guid": g, "name": f"Agregat {k}", "type": "Francis", "rated_power_mw": 25.0, "rated_head_m": 42.75}
        for k, g in enumerate(guids, start=1)
    ]
    return result, {"units": units}


def run(ctx):
    import ifcopenshell.util.element as ue
    from sath import demo_plant, ges_objects, ifc, sim_anim

    out = demo_plant.build(bpy.context, head_m=45.0, units=2, unit_mw=25.0, zero_m=850.0)
    before = {ifc.guid(o): (o.ges.kind, o.ges.role, ges_objects.params_dict(o)) for o in out.values()}
    assert len(before) == 16 and all(before), before.keys()
    sp = ue.get_psets(ifc.entity(out["gen:1"]))["Pset_SathParametric"]
    assert (sp["Kind"], sp["Role"], sp["SchemaVersion"], sp["Units"]) == ("GES_Generator", "gen:1", 1, "m"), sp
    path = Path(tempfile.gettempdir()) / "sath_roundtrip.ifc"
    ifc.save(path)
    import ifcopenshell

    f_saved = ifcopenshell.open(str(path))
    texts = [p for p in f_saved.by_type("IfcPropertySingleValue") if p.Name == "Params"]
    assert len(texts) == 16 and all(p.NominalValue.is_a("IfcText") for p in texts), "Params IfcText bo'lishi kerak"

    calls: list = []
    orig = ges_objects.rebuild_mesh
    ges_objects.rebuild_mesh = lambda o: calls.append(o.name)  # tiklash mesh ni qayta qurmasligi kerak
    try:
        assert ifc.load(path)  # loyiha ochiq edi → yangi sessiya: Object.ges yo'qoladi, ifc.loaded → restore_from_ifc
    finally:
        ges_objects.rebuild_mesh = orig
    rep = ges_objects.LAST_REPORT
    assert calls == [], calls
    assert len(rep.restored) == 16 and not rep.inferred and not rep.unknown, rep.text()
    for g, (kind, role, params) in before.items():
        o = ifc.object_for_guid(g)
        assert o is not None, g
        assert (o.ges.kind, o.ges.role) == (kind, role), (o.name, o.ges.kind, o.ges.role)
        got = ges_objects.params_dict(o)
        assert got.keys() == params.keys(), o.name
        for k, v in params.items():
            same = abs(got[k] - v) <= 1e-6 * max(1.0, abs(v)) if isinstance(v, float) else got[k] == v
            assert same, (o.name, k, got[k], v)

    result, params = _hydro(6, [ifc.guid(ges_objects.by_role(f"unit:{k}")) for k in (1, 2)])
    assert sim_anim.animate_hydro(bpy.context, result, params, zero_m=850.0) == 6
    gen = ges_objects.by_role("gen:1")
    cf = [f for f in sim_anim._fcurves(gen) if f.data_path == "color"]
    assert cf and len(cf[0].keyframe_points) == 6, "generator rangi keyframe lari yo'q"
    gen.ges.role = ""  # rol yo'qolsa — jim emas
    try:
        sim_anim.animate_hydro(bpy.context, result, params, zero_m=850.0)
        raise AssertionError("TwinBindingError kutilgan")
    except sim_anim.TwinBindingError as e:
        assert "gen:1" in str(e), e
    gen.ges.role = "gen:1"

    assert ifc.load(SAMPLE)  # eski model: faqat Pset_GES_* (FreeCAD davri)
    rep = ges_objects.LAST_REPORT
    assert len(rep.inferred) == 7 and not rep.restored and not rep.unknown, rep.text()
    assert ifc.entity(ges_objects.by_role("unit:1")).Name == "Turbina 1"
    assert ifc.entity(ges_objects.by_role("penstock:3")).Name == "Bosimli quvur 3"
    p = ges_objects.params_dict(ges_objects.by_role("dam"))
    assert (p["Height"], p["Length"], p["DamType"]) == (20.0, 60.0, "Gravitatsion"), p
    path.unlink(missing_ok=True)
    print("ROUNDTRIP:", rep.text(), flush=True)

    # qo'lda qo'shilganda standart rol (controller qarori): yagona tur — o'z roli, indeksli tur — keyingi bo'sh raqam
    assert not ges_objects.by_kind("GES_Transformer") and ges_objects.by_role("dam") is not None
    t1 = ges_objects.add(bpy.context, "GES_Transformer")
    t2 = ges_objects.add(bpy.context, "GES_Transformer")
    d2 = ges_objects.add(bpy.context, "GES_Dam")  # to'g'on roli band — bo'sh qoladi (jim dublikat emas)
    assert (t1.ges.role, t2.ges.role, d2.ges.role) == ("transformer:1", "transformer:2", ""), "standart rollar"
    n = len(ges_objects.by_kind("GES_Turbine"))
    assert ges_objects.add(bpy.context, "GES_Turbine").ges.role == f"unit:{n + 1}"
    assert ges_objects.add(bpy.context, "GES_Turbine", role="unit:9").ges.role == "unit:9"

    # ommaviy o'chirishdan keyin add() ishlaydi; agregatsiz (to'g'on) modelda guid siz agregatlar — animatsiya yakunlanadi
    for o in ges_objects.by_kind_all():
        bpy.data.objects.remove(o)
    ges_objects.add(bpy.context, "GES_Dam")
    res, prm = _hydro(4, [""])
    prm["units"] = [{k: v for k, v in u.items() if k != "guid"} for u in prm["units"]]
    assert sim_anim.animate_hydro(bpy.context, res, prm, zero_m=850.0) == 4
    from sath import water

    plane = bpy.data.objects.get(water.NAME)
    assert plane is not None and plane.animation_data and plane.animation_data.action, "suv sathi keyframe lari yo'q"
    print("ROUNDTRIP: agregatsiz model animatsiyasi yakunlandi", flush=True)
