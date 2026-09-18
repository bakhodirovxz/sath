"""«Namuna GES» — rasmdagi 9 komponentli stansiya egizagi bir tugma bilan: to'g'on, suv qabul minorasi, egri bosh
quvurlar, turbina + generator, chiqarish quvuri, daryo oqimi kanali, mashina zali, transformatorlar, boshqaruv xonasi,
suv tashlagich; ikki suv tekisligi (yuqori/quyi byef) va yer plitasi.

Koordinatalar (m): Y — oqim yo'nalishi, X — ko'ndalang, Z — yuqoriga; mashina zali poli z = 0 (model 0 belgisi),
quyi byef z = −2, yuqori byef z_up = H − 2 (H — brutto napor), gerb z_up + 3, to'g'on/kanal tagi z = −12.
Agregat parametrlari napordan: Q = P/(ρ·g·H_net·η), D_quvur = √(4Q/(π·v)), v = 4 m/s; generator 48 qutb (125 ayl/min).
Har obyekt `obj.ges.role` bilan belgilanadi — simulyatsiya animatsiyalari shu rollar orqali obyektlarni topadi.
"""

from __future__ import annotations

import math

import bpy

from . import ges_objects, ifc, physics, water

RHO_G = 9806.65
TAILWATER = -2.0
BED = -12.0
SPACING = 14.0
Y_TURBINE = 22.0
GROUND = "GES_Yer"


def _place(obj, x: float, y: float, z: float, rot_z_deg: float = 0.0) -> None:
    obj.location = (x, y, z)
    obj.rotation_euler = (0.0, 0.0, math.radians(rot_z_deg))
    ifc.sync_placement(obj)


def _add(context, kind: str, name: str, role: str, **params):
    obj = ges_objects.add(context, kind, name)
    obj.ges.role = role
    if params:
        ges_objects.set_params(obj, **params)
    return obj


def _ground(context, xr: float, y0: float, y1: float):
    ob = bpy.data.objects.get(GROUND)
    if ob is None:
        me = bpy.data.meshes.new(GROUND)
        me.from_pydata(
            [(-0.5, -0.5, -1), (0.5, -0.5, -1), (0.5, 0.5, -1), (-0.5, 0.5, -1), (-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)],
            [],
            [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
        )
        ob = bpy.data.objects.new(GROUND, me)
        context.scene.collection.objects.link(ob)
        ob.color = (0.36, 0.42, 0.30, 1.0)
    ob.location = (0.0, (y0 + y1) / 2, BED)
    ob.scale = (2 * xr, y1 - y0, 2.0)
    return ob


def build(context, head_m: float = 45.0, units: int = 2, unit_mw: float = 25.0, zero_m: float = 0.0) -> dict:
    """Stansiyani quradi, {rol: obyekt} qaytaradi. Bonsai loyihasi bo'lmasa yaratiladi."""
    n = max(1, min(4, int(units)))
    H = max(10.0, float(head_m))
    ifc.ensure_project()
    z_up = TAILWATER + H
    crest = z_up + 3.0
    dam_h = crest - BED
    bw = round(0.8 * dam_h, 1)
    ld = n * SPACING + 60.0
    h_net = 0.95 * H
    q_unit = unit_mw * 1e6 / (RHO_G * h_net * 0.92)
    d_pen = math.sqrt(4 * q_unit / (math.pi * 4.0))
    out: dict[str, bpy.types.Object] = {}

    dam = _add(
        context, "GES_Dam", "To'g'on", "dam",
        Length=ld, Height=dam_h, CrestWidth=6.0, BaseWidth=bw,
        CrestElevation=zero_m + crest, BaseElevation=zero_m + BED,
    )  # fmt: skip
    _place(dam, -ld / 2, -bw, BED)
    out["dam"] = dam

    z_sill = z_up - min(25.0, 0.55 * H)
    intake = _add(
        context, "GES_Intake", "Suv qabul qilgich", "intake",
        Width=n * SPACING + 6.0, Depth=8.0, Height=crest + 2.0 - z_sill,
        SillElevation=zero_m + z_sill, DesignFlow=round(n * q_unit, 1), Openings=n,
    )  # fmt: skip
    _place(intake, 0.0, -bw - 4.0, z_sill)
    out["intake"] = intake

    sp = _add(
        context, "GES_Spillway", "Suv tashlagich", "spillway",
        Width=12.0, Length=bw + 4.0, Thickness=1.0, CrestElevation=zero_m + z_up, Gates=2,
    )  # fmt: skip
    _place(sp, ld / 2 - 20.0, -bw, z_up - 1.0)
    out["spillway"] = sp

    l_ph, w_ph, h_ph = n * SPACING + 16.0, 36.0, 22.0
    ph = _add(
        context, "GES_Powerhouse", "Mashina zali", "powerhouse",
        Length=l_ph, Width=w_ph, Height=h_ph, Units=n, FloorElevation=zero_m, View="Kesim",
    )  # fmt: skip
    _place(ph, 0.0, Y_TURBINE + 2.0, 0.0)
    out["powerhouse"] = ph

    cr = _add(
        context, "GES_ControlRoom", "Boshqaruv xonasi", "controlroom",
        Length=12.0, Width=8.0, Height=4.0, FloorElevation=zero_m + 10.0,
    )  # fmt: skip
    _place(cr, l_ph / 2 - 8.0, Y_TURBINE + 2.0, 10.0)
    out["controlroom"] = cr

    wt = n * SPACING + 10.0
    tr = _add(
        context, "GES_Tailrace", "Daryo oqimi kanali", "tailrace",
        Width=wt, Length=40.0, Depth=11.0, BedSlope=0.001, Manning=0.03, BedElevation=zero_m + BED,
        DesignTailwater=zero_m + TAILWATER, DesignFlow=round(n * q_unit, 1),
    )  # fmt: skip
    _place(tr, 0.0, Y_TURBINE + 14.0, BED)
    out["tailrace"] = tr

    # Bosh quvur kirishi — to'g'onning quyi byef yuzasida (minora bilan tunnel orqali bog'langan deb olinadi),
    # quvur rasmdagidek qiya yuzada ochiq holda mashina zaliga tushadi
    z_in = z_sill + 3.0
    y_in = -(bw - 6.0) / 2 * (z_in - BED) / dam_h + 0.5
    for k in range(1, n + 1):
        x = (k - 1 - (n - 1) / 2) * SPACING
        t = _add(
            context, "GES_Turbine", f"Agregat {k}", f"unit:{k}",
            TurbineType="Francis", RatedPower=unit_mw, RatedHead=round(h_net, 1), RatedFlow=round(q_unit, 2),
            Efficiency=0.92, RunnerDiameter=3.0, Height=4.0,
        )  # fmt: skip
        _place(t, x, Y_TURBINE, -2.0)
        out[f"unit:{k}"] = t
        g = _add(
            context, "GES_Generator", f"Generator {k}", f"gen:{k}",
            RatedPower=round(unit_mw / 0.9, 1), Voltage=10.5, Poles=48, Frequency=50.0, StatorDiameter=6.0, Height=3.5,
        )  # fmt: skip
        _place(g, x, Y_TURBINE, 2.0)
        out[f"gen:{k}"] = g
        dt = _add(
            context, "GES_DraftTube", f"Chiqarish quvuri {k}", f"draft:{k}",
            InletDiameter=3.0, ConeHeight=5.0, OutletWidth=8.0, OutletHeight=4.0, DiffuserLength=12.0,
            SuctionHead=round(-2.0 - TAILWATER, 2),
        )  # fmt: skip
        _place(dt, x, Y_TURBINE, -2.0)
        out[f"draft:{k}"] = dt
        dz, dy = z_in + 2.0, (Y_TURBINE - 2.6) - y_in
        alpha, length = physics.solve_penstock(dz, dy, 8.0, 6.0)
        pen = _add(
            context, "GES_Penstock", f"Bosh quvur {k}", f"penstock:{k}",
            Length=round(length, 2), Diameter=round(d_pen, 2), WallThickness=0.02, Roughness=0.1,
            Inclination=round(alpha, 3), BendRadius=8.0, OutletLength=6.0,
        )  # fmt: skip
        _place(pen, x, y_in, z_in)
        out[f"penstock:{k}"] = pen
        tf = _add(
            context, "GES_Transformer", f"Transformator {k}", f"transformer:{k}",
            RatedPower=round(unit_mw / 0.9, 1), VoltageHV=110.0, VoltageLV=10.5,
        )  # fmt: skip
        _place(tf, l_ph / 2 + 8.0, Y_TURBINE - 12.0 + (k - 1) * 10.0, 0.0)
        out[f"transformer:{k}"] = tf

    _ground(context, ld / 2 + 30.0, -bw - 70.0, Y_TURBINE + 80.0)
    water.place_water_plane(context, z_up, (-ld / 2 - 30.0, ld / 2 + 30.0, -bw - 70.0, -bw))
    water.place_tailwater_plane(context, TAILWATER, (-wt / 2, wt / 2, Y_TURBINE + 14.0, Y_TURBINE + 80.0))
    s = context.scene.ges
    s.hydro_zero = float(zero_m)
    s.hydro_level0 = 0.0
    return out


def frame_view(context) -> None:
    """Ko'rinish: quyi byef tomondan, o'ngdan-yuqoridan (kesim devor tomoni), GES obyektlari bbox bo'yicha
    (yer va suv tekisliklarisiz), obyekt ranglari."""
    from mathutils import Euler, Vector

    pts = [o.matrix_world @ Vector(c) for o in ges_objects.by_kind_all() for c in o.bound_box]
    if not pts:
        return
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, radius = (lo + hi) / 2, (hi - lo).length / 2
    for area in getattr(context.screen, "areas", []) if context.screen else []:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            r3d = sp.region_3d
            r3d.view_perspective = "PERSP"
            r3d.view_rotation = Euler((math.radians(62.0), 0.0, math.radians(140.0))).to_quaternion()
            r3d.view_location = center
            r3d.view_distance = radius * 1.7
            sp.shading.color_type = "OBJECT"
            sp.clip_end = max(sp.clip_end, 5000.0)


class SATH_OT_build_demo_plant(bpy.types.Operator):
    """Rasmdagi GES (9 komponent) egizagini qurish: to'g'on, suv qabul, egri bosh quvurlar, turbina+generator,
    chiqarish quvuri, kanal, zal, transformatorlar, boshqaruv xonasi, tashlama; IFC + Pset_GES_*"""

    bl_idname = "sath.build_demo_plant"
    bl_label = "Namuna GES qurish"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.ges
        try:
            out = build(context, s.demo_head, s.demo_units, s.demo_unit_mw, s.hydro_zero)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Qurish xatosi: {e}")
            return {"CANCELLED"}
        frame_view(context)
        s.twin_note = f"{len(out)} obyekt: {s.demo_units} agregat, H = {s.demo_head:.0f} m"
        self.report({"INFO"}, s.twin_note)
        return {"FINISHED"}


CLASSES = (SATH_OT_build_demo_plant,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
