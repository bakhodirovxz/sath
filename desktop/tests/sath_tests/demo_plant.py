"""Namuna GES: 9 komponent rollari, IFC klasslar, bosh quvur turbinaga yetadi, suv tekisliklari, Pset qiymatlari."""

import math

import bpy


def run(ctx):
    import ifcopenshell.util.element as ue
    from mathutils import Vector
    from sath import demo_plant, ges_objects, ifc, physics

    out = demo_plant.build(bpy.context, head_m=45.0, units=2, unit_mw=25.0, zero_m=850.0)
    roles = set(out)
    for r in ("dam", "intake", "spillway", "powerhouse", "controlroom", "tailrace", "unit:1", "gen:2", "draft:1", "penstock:2", "transformer:1"):
        assert r in roles, r
    assert len(out) == 6 + 5 * 2, len(out)
    classes = {r: ifc.entity(o).is_a() for r, o in out.items()}
    assert classes["gen:1"] == "IfcElectricGenerator" and classes["draft:1"] == "IfcFlowSegment", classes
    assert classes["tailrace"] == "IfcCivilElement" and classes["penstock:1"] == "IfcPipeSegment", classes
    # rol orqali topish
    assert ges_objects.by_role("unit:2") is out["unit:2"] and len(ges_objects.by_kind("GES_Generator")) == 2
    # bosh quvur chiqishi turbina spiral kamerasiga yetadi (≤ 1 m)
    pen = out["penstock:1"]
    pp = ges_objects.params_dict(pen)
    assert pp["Inclination"] > 0 and pp["Length"] > 30, pp
    path = physics.penstock_path(pp["Length"], pp["Inclination"], pp["BendRadius"], pp["OutletLength"])
    end = pen.matrix_world @ Vector(path["p3"])
    t = out["unit:1"]
    gap = (end - Vector((t.location.x, t.location.y - 2.6, t.location.z))).length
    assert gap < 1.0, (gap, tuple(end), tuple(t.location))
    # bosh quvur meshi haqiqatan egri: bbox Z va Y bo'ylab cho'zilgan
    d = pen.dimensions
    assert d.y > 20 and d.z > 10, tuple(d)
    # Pset: generator sinxron tezligi 125 ayl/min (48 qutb), to'g'on gerbi absolyut belgi
    gp = ue.get_psets(ifc.entity(out["gen:1"]))["Pset_GES_Generator"]
    assert gp["Aylanish_rpm"] == 125.0 and gp["Qutblar"] == 48, gp
    dp = ue.get_psets(ifc.entity(out["dam"]))["Pset_GES_Dam"]
    assert dp["GerbBelgisi_m"] == 850.0 + 46.0 and dp["TagBelgisi_m"] == 850.0 - 12.0, dp
    # IFC joylashuvi yozilgan (ObjectPlacement Blender location bilan mos)
    import ifcopenshell.util.placement as up

    m = up.get_local_placement(ifc.entity(t).ObjectPlacement)
    assert abs(m[0][3] - t.location.x) < 1e-3 and abs(m[2][3] - t.location.z) < 1e-3, (m[0][3], m[2][3], tuple(t.location))
    # suv tekisliklari
    up_plane, tw_plane = bpy.data.objects["GES_SuvSathi"], bpy.data.objects["GES_QuyiByef"]
    assert abs(up_plane.location.z - 43.0) < 1e-6 and abs(tw_plane.location.z + 2.0) < 1e-6
    assert up_plane.location.y < out["dam"].location.y and tw_plane.location.y > t.location.y
    assert up_plane.get("sath_region") is not None
    # sath yangilanganda mintaqa saqlanadi
    from sath import water

    water.place_water_plane(bpy.context, 40.0)
    assert abs(up_plane.location.z - 40.0) < 1e-6 and up_plane.location.y < out["dam"].location.y
    assert bpy.data.objects.get("GES_Yer") is not None
    assert tuple(out["gen:1"].color)[:3] == (0.16, 0.45, 0.78) or abs(out["gen:1"].color[2] - 0.78) < 1e-3, tuple(out["gen:1"].color)
    assert out["powerhouse"].dimensions.z > 20 and len(out["powerhouse"].data.polygons) > 12  # kesim (ichi bo'sh)
    assert bpy.context.scene.ges.hydro_zero == 850.0
    # chiqarish quvuri kanalga kiradi: diffuzor oxiri kanal boshidan keyin
    dt = out["draft:1"]
    assert dt.location.y + 2.25 + 12.0 > out["tailrace"].location.y
    assert not math.isnan(out["dam"].dimensions.x)
    print("DEMO:", len(out), "obyekt; quvur qiyaligi", round(pp["Inclination"], 1), "°, uzunlik", round(pp["Length"], 1), "m; gap", round(gap, 3))
