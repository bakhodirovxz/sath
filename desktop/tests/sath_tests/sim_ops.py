"""Suv sathi tekisligi sahna bbox ini qoplaydi va qayta chaqirilganda yangilanadi."""

import bpy


def run(ctx):
    from sath import water

    bpy.ops.mesh.primitive_cube_add(size=10, location=(5, 5, 0))
    ob = water.place_water_plane(bpy.context, 3.5)
    assert ob.name == "GES_SuvSathi" and abs(ob.location.z - 3.5) < 1e-6 and ob.scale.x >= 12.0
    ob2 = water.place_water_plane(bpy.context, 7.0)
    assert ob2 is ob and abs(ob.location.z - 7.0) < 1e-6
    assert sum(1 for o in bpy.data.objects if o.name.startswith("GES_SuvSathi")) == 1
    for op in ("sim_catalog", "sim_pick", "sim_prefill", "sim_run", "sim_water", "safety_check"):
        assert hasattr(bpy.ops.sath, op), op
    assert bpy.ops.sath.sim_pick.poll() is False  # katalog yuklanmagan
    assert hasattr(bpy.types, "SATH_PT_sim")
