"""GES_SuvSathi — yarim shaffof ko'k tekislik, model bbox ini qoplaydi, z = sath (m)."""

from __future__ import annotations

import bpy
from mathutils import Vector

NAME = "GES_SuvSathi"
COLOR = (0.22, 0.72, 0.79, 0.4)


def _material():
    m = bpy.data.materials.get(NAME)
    if m is None:
        m = bpy.data.materials.new(NAME)
        m.diffuse_color = COLOR
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
    return m


def place_water_plane(context, level_m: float):
    objs = [o for o in context.scene.objects if o.type == "MESH" and o.name != NAME]
    if not objs:
        return None
    xs, ys = [], []
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x)
            ys.append(w.y)
    size = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.2 or 10.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    ob = bpy.data.objects.get(NAME)
    if ob is None:
        me = bpy.data.meshes.new(NAME)
        me.from_pydata(
            [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)]
        )
        ob = bpy.data.objects.new(NAME, me)
        context.scene.collection.objects.link(ob)
        ob.data.materials.append(_material())
        ob.color = COLOR
        ob.show_transparent = True
    ob.location = (cx, cy, level_m)
    ob.scale = (size, size, 1.0)
    return ob
