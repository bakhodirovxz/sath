"""Namunaviy GES IFC modeli (to'g'on, mashina zali, bosimli quvurlar) — sinov uchun.

Ishga tushirish:  python docs/samples/make_sample_ges.py [chiqish.ifc] [--v2]
--v2: ikkinchi versiya (bitta quvur o'chirilgan, to'g'on balandroq, yangi transformator) — diff sinovi uchun.
"""

import sys
import uuid

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid
import ifcopenshell.util.unit
import numpy as np

NS = uuid.UUID("6f1c7e2a-5b1d-4c0e-9a6b-3d2f1e0c9b8a")


def stable_guid(name: str) -> str:
    """Bir xil nomli element har versiyada bir xil GUID ga ega — diff ishlashi uchun."""
    return ifcopenshell.guid.compress(uuid.uuid5(NS, name).hex)


def pset(f, product, name, properties):
    ps = ifcopenshell.api.pset.add_pset(f, product=product, name=name)
    ifcopenshell.api.pset.edit_pset(f, pset=ps, properties=properties)


def place(f, obj, x=0.0, y=0.0, z=0.0, rot_z_deg=0.0, rot_x_deg=0.0):
    m = np.eye(4)
    a, b = np.deg2rad(rot_z_deg), np.deg2rad(rot_x_deg)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    m[:3, :3] = rz @ rx
    m[:3, 3] = [x, y, z]
    ifcopenshell.api.geometry.edit_object_placement(f, product=obj, matrix=m)


def box(f, body, obj, length, width, height, x=0, y=0, z=0, rot=0.0):
    rep = ifcopenshell.api.geometry.add_wall_representation(
        f, context=body, length=length, height=height, thickness=width
    )
    ifcopenshell.api.geometry.assign_representation(f, product=obj, representation=rep)
    place(f, obj, x, y, z, rot)


def pipe(f, body, obj, length, diameter, x=0, y=0, z=0, rot=0.0):
    # Profil radiusi loyiha birligida (default mm) — API funksiyalari esa metr qabul qiladi
    radius = diameter / 2 / ifcopenshell.util.unit.calculate_unit_scale(f)
    profile = f.createIfcCircleProfileDef("AREA", None, None, radius)
    rep = ifcopenshell.api.geometry.add_profile_representation(
        f, context=body, profile=profile, depth=length
    )
    ifcopenshell.api.geometry.assign_representation(f, product=obj, representation=rep)
    place(f, obj, x, y, z, rot_x_deg=rot)  # Z o'qi bo'ylab ekstruziya → rot_x=-90 bilan +Y ga


def build(v2: bool = False) -> ifcopenshell.file:
    f = ifcopenshell.api.project.create_file(version="IFC4")
    proj = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Namuna GES")
    ifcopenshell.api.unit.assign_unit(f)
    model = ifcopenshell.api.context.add_context(f, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="GES maydoni")
    bld = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Mashina zali")
    st0 = ifcopenshell.api.root.create_entity(
        f, ifc_class="IfcBuildingStorey", name="Turbina qavati"
    )
    st1 = ifcopenshell.api.root.create_entity(
        f, ifc_class="IfcBuildingStorey", name="Generator qavati"
    )
    st1.Elevation = 6.0
    ifcopenshell.api.aggregate.assign_object(f, relating_object=proj, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[bld])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=bld, products=[st0, st1])
    place(f, st1, z=6.0)

    for e in (proj, site, bld, st0, st1):
        e.GlobalId = stable_guid(f"{e.is_a()}:{e.Name}")

    def ent(cls, name, container, **attrs):
        e = ifcopenshell.api.root.create_entity(f, ifc_class=cls, name=name)
        e.GlobalId = stable_guid(f"{cls}:{name}")
        for k, v in attrs.items():
            setattr(e, k, v)
        ifcopenshell.api.spatial.assign_container(f, relating_structure=container, products=[e])
        return e

    # To'g'on — uzun qalin devor
    dam = ent("IfcWall", "To'g'on", site, PredefinedType="SOLIDWALL")
    box(f, body, dam, length=60, width=8, height=22 if v2 else 20, x=-30, y=-25, z=0)
    pset(
        f,
        dam,
        "Pset_GES_Dam",
        {"Turi": "Gravitatsion", "Balandlik_m": 22.0 if v2 else 20.0, "Uzunlik_m": 60.0},
    )

    # Suv tashlagich
    spill = ent("IfcSlab", "Suv tashlagich", site)
    box(f, body, spill, length=12, width=10, height=1.0, x=10, y=-17, z=12)

    # Mashina zali — pol, devorlar
    floor = ent("IfcSlab", "Turbina qavati poli", st0, PredefinedType="FLOOR")
    box(f, body, floor, length=30, width=14, height=0.5, x=-15, y=0, z=0)
    for i, (x, y, L, rot) in enumerate(
        [(-15, 0, 30, 0), (-15, 14, 30, 0), (-15, 0, 14, 90), (15, 0, 14, 90)]
    ):
        w = ent("IfcWall", f"Zal devori {i + 1}", st0)
        box(f, body, w, length=L, width=0.4, height=12, x=x, y=y, z=0.5, rot=rot)

    # Agregatlar — 3 ta turbina + generator
    units = 3
    for i in range(units):
        x = -10 + i * 10
        t = ent("IfcFlowMovingDevice", f"Turbina {i + 1}", st0)
        box(f, body, t, length=3, width=3, height=2.5, x=x - 1.5, y=5.5, z=0.5)
        pset(
            f,
            t,
            "Pset_GES_Turbine",
            {"Turi": "Francis", "Quvvat_MW": 25.0, "Napor_m": 45.0, "Sarf_m3s": 62.0},
        )
        g = ent("IfcElectricGenerator", f"Generator {i + 1}", st1)
        box(f, body, g, length=3, width=3, height=2.0, x=x - 1.5, y=5.5, z=6.0)
        # Bosimli quvur — to'g'ondan turbinaga
        if v2 and i == 1:
            continue  # v2 da 2-quvur o'chirilgan
        p = ent("IfcPipeSegment", f"Bosimli quvur {i + 1}", site)
        pipe(f, body, p, length=22, diameter=2.4, x=x, y=-17, z=8, rot=-90)
        pset(f, p, "Pset_GES_Penstock", {"Diametr_m": 2.4, "Uzunlik_m": 18.0, "Material": "Po'lat"})

    if v2:
        tr = ent("IfcTransformer", "Transformator", site)
        box(f, body, tr, length=4, width=3, height=3, x=20, y=6, z=0)

    return f


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "sample_ges.ifc"
    build(v2="--v2" in sys.argv).write(out)
    print("yozildi:", out)
