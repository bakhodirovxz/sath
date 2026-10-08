"""K2: namuna GES → IFC saqlash → yangi sessiyada ochish → har GES obyekti kind/role/params tiklanadi (mesh qayta
qurilmaydi, GUID saqlanadi) → animate_hydro rollar orqali keyframe qo'yadi; rol yo'qolsa TwinBindingError (jim emas;
governor/seismic ham animatsiyani yakunlab, keyin xabar beradi).
Eski model (Pset_SathParametric siz, docs/samples/namuna_ges_v1.ifc): Pset_GES_* dan tur, X bo'yicha rollar; o'lchamlar
taxminiy — geometrik bo'lmagan tahrir/rol faqat psetlarni yozadi (I1), geometrik tahrir mesh ni o'zgartirmaydi,
«O'lchamlarni tasdiqlash» dan keyin representation — tessellation, bbox = ges_kinds.build (C1)."""

import json
import tempfile
from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def _param(o, name):
    return next(p for p in o.ges.params if p.name == name)


def _reps(o):
    from sath import ifc

    return [(r.id(), r.RepresentationType, tuple(i.is_a() for i in r.Items)) for r in ifc.entity(o).Representation.Representations]


def _dims(o):
    bpy.context.view_layer.update()
    return tuple(round(x, 4) for x in o.dimensions)


def _assert_tessellated_like_build(o):
    """C1: representation — tessellation (ekstruziyaga «moslangan» emas), Blender mesh bbox = ges_kinds.build."""
    from sath import ges_objects, ifc
    from sath.shared import ges_kinds

    body = [r for r in ifc.entity(o).Representation.Representations if r.RepresentationIdentifier == "Body"]
    assert len(body) == 1 and body[0].RepresentationType == "Tessellation", _reps(o)
    assert all(i.is_a() in ("IfcPolygonalFaceSet", "IfcTriangulatedFaceSet") for i in body[0].Items), _reps(o)
    v, _ = ges_kinds.build(o.ges.kind, ges_objects.params_dict(o))
    want = v.max(axis=0) - v.min(axis=0)
    got = _dims(o)
    assert all(abs(g - w) <= 2e-3 * max(1.0, w) for g, w in zip(got, want, strict=True)), (o.name, got, want.round(4).tolist())


def _legacy_edits(path: Path):
    """I1 + C1 + M3 + M7: namuna (FreeCAD davri, yagona IfcExtrudedAreaSolid) elementlarini tahrirlash."""
    import ifcopenshell
    import ifcopenshell.util.element as ue
    from sath import ges_objects, ifc

    t, t2, pn = (ges_objects.by_role(r) for r in ("unit:1", "unit:2", "penstock:1"))
    assert t.ges.inferred and pn.ges.inferred and not t.ges.ifc_dirty
    rep0, dims0, nv0 = _reps(t), _dims(t), len(t.data.vertices)
    assert rep0[0][1] == "SweptSolid", rep0

    # geometrik bo'lmagan parametr va rol — faqat psetlar; mesh va representation o'zgarmaydi
    _param(t, "RatedPower").value_float = 30.0
    assert t.ges.ifc_dirty and not t.ges.geom_dirty
    t.ges.role = "unit:7"
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and not t.ges.ifc_dirty
    assert (_reps(t), _dims(t), len(t.data.vertices)) == (rep0, dims0, nv0), "taxminiy obyekt geometriyasi o'zgardi"
    ps = ue.get_psets(ifc.entity(t))
    assert ps["Pset_GES_Turbine"]["Quvvat_MW"] == 30.0 and ps["Pset_GES_Turbine"]["FIK"] == 0.92, ps  # M3: shovqinsiz
    sp = ps["Pset_SathParametric"]
    assert sp["Approximate"] is True and sp["Role"] == "unit:7", sp
    assert json.loads(sp["Params"])["Efficiency"] == 0.92
    t.ges.role = "unit:1"
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and _reps(t) == rep0

    # geometrik tahrir taxminiy obyektda: mesh qayta qurilmaydi, foydalanuvchiga aytiladi; sync/rebuild ham tegmaydi
    _param(t, "RunnerDiameter").value_float = 2.0
    assert t.ges.geom_dirty and t.ges.ifc_dirty and "taxminiy" in bpy.context.scene.ges.status
    assert len(t.data.vertices) == nv0 and _dims(t) == dims0
    assert bpy.ops.sath.sync_ifc() == {"FINISHED"} and _reps(t) == rep0 and not t.ges.ifc_dirty
    for o in bpy.context.view_layer.objects:
        o.select_set(o is t)
    assert bpy.ops.sath.rebuild_object() == {"FINISHED"} and _reps(t) == rep0 and _dims(t) == dims0

    # M7: IFC ga yozilmagan o'zgarishi bor obyekt qo'lda «IFC dan tiklash» da tegilmaydi
    _param(t2, "RatedPower").value_float = 33.0
    assert bpy.ops.sath.restore_ges() == {"FINISHED"}
    rep = ges_objects.LAST_REPORT
    assert rep.skipped == [t2.name] and ges_objects.params_dict(t2)["RatedPower"] == 33.0, rep.text()
    assert t.ges.role == "unit:1" and t2.ges.role == "unit:2" and ges_objects.by_role("unit:3") is not None
    assert t.ges.inferred and ges_objects.params_dict(t)["RunnerDiameter"] == 2.0  # pset dagi kiritilgan qiymat

    # C1: tasdiqlash → tessellation (59 mm plastinka emas), bbox = build(params); Approximate = False
    assert bpy.ops.sath.confirm_dimensions(obj=t.name) == {"FINISHED"}
    assert not (t.ges.inferred or t.ges.geom_dirty or t.ges.ifc_dirty)
    _assert_tessellated_like_build(t)
    assert ue.get_psets(ifc.entity(t))["Pset_SathParametric"]["Approximate"] is False
    # C1: taxminiy bo'lmagan, lekin eski (IfcExtrudedAreaSolid) element — oddiy geometrik tahrir + sync
    pn.ges.inferred = False
    assert _reps(pn)[0][1] == "SweptSolid"
    _param(pn, "Length").value_float = 30.0
    assert pn.ges.geom_dirty and bpy.ops.sath.sync_ifc() == {"FINISHED"} and not pn.ges.geom_dirty
    _assert_tessellated_like_build(pn)

    ifc.save(path)
    f = ifcopenshell.open(str(path))
    for o in (t, pn):
        e = f.by_guid(ifc.guid(o))
        assert [r.RepresentationType for r in e.Representation.Representations] == ["Tessellation"], e.Name
    assert ifc.load(path)  # qayta ochish: tasdiqlangan — to'liq, qolganlari — taxminiy
    rep = ges_objects.LAST_REPORT
    assert not rep.unknown and len(rep.restored) == 2 and len(rep.inferred) == 5, rep.text()
    assert not ges_objects.by_role("unit:1").ges.inferred and ges_objects.by_role("unit:2").ges.inferred
    assert {o.ges.role for o in ges_objects.by_kind("GES_Turbine")} == {"unit:1", "unit:2", "unit:3"}
    assert ges_objects.params_dict(ges_objects.by_role("unit:1"))["RunnerDiameter"] == 2.0
    print("ROUNDTRIP: eski model tahrirlari (I1/C1) — OK", flush=True)


def _governor_and_seismic_finish():
    """M1: governor/seismic rol topilmasa ham qolgan obyektlarni animatsiya qiladi, keyin TwinBindingError."""
    from sath import ges_objects, sim_anim

    u1 = ges_objects.by_role("unit:1")
    u1.ges.role = ""
    res = {"series": {"t": [0.0, 0.5, 1.0, 1.5], "frequency_hz": [50.0, 49.6, 49.9, 50.0]}}
    try:
        sim_anim.animate_governor(bpy.context, res)
        raise AssertionError("TwinBindingError kutilgan (governor)")
    except sim_anim.TwinBindingError as e:
        assert "unit:1" in str(e), e
    u2 = ges_objects.by_role("unit:2")
    rot = [f for f in sim_anim._fcurves(u2) if f.data_path == "rotation_euler"]
    assert rot and len(rot[0].keyframe_points) == 4, "unit:2 aylanishi barcha kadrlarda bo'lishi kerak"
    assert bpy.context.scene.frame_current == 1  # _finish chaqirilgan
    u1.ges.role = "unit:1"
    pens = ges_objects.by_kind("GES_Penstock")
    roles = [p.ges.role for p in pens]
    for p in pens:
        p.ges.role = ""
    res = {"structures": [
        {"name": "Bosimli quvur", "sa_g": 0.3, "period_s": 0.4}, {"name": "To'g'on", "sa_g": 0.1, "period_s": 0.3},
    ]}  # fmt: skip
    try:
        sim_anim.animate_seismic(bpy.context, res, fps=4, duration_s=1.0)
        raise AssertionError("TwinBindingError kutilgan (seismic)")
    except sim_anim.TwinBindingError as e:
        assert "Bosimli quvur" in str(e), e
    dam = ges_objects.by_role("dam")
    loc = [f for f in sim_anim._fcurves(dam) if f.data_path == "location"]
    assert loc and len(loc[0].keyframe_points) == 4, "to'g'on (keyingi inshoot) animatsiya qilinmadi"
    sim_anim.clear_animation(bpy.context)
    for p, r in zip(pens, roles, strict=True):
        p.ges.role = r


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
    _governor_and_seismic_finish()

    assert ifc.load(SAMPLE)  # eski model: faqat Pset_GES_* (FreeCAD davri)
    rep = ges_objects.LAST_REPORT
    assert len(rep.inferred) == 7 and not rep.restored and not rep.unknown, rep.text()
    assert ifc.entity(ges_objects.by_role("unit:1")).Name == "Turbina 1"
    assert ifc.entity(ges_objects.by_role("penstock:3")).Name == "Bosimli quvur 3"
    p = ges_objects.params_dict(ges_objects.by_role("dam"))
    assert (p["Height"], p["Length"], p["DamType"]) == (20.0, 60.0, "Gravitatsion"), p
    print("ROUNDTRIP:", rep.text(), flush=True)
    _legacy_edits(path)
    path.unlink(missing_ok=True)

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
