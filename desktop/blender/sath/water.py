"""GES_SuvSathi (yuqori byef) / GES_QuyiByef — yarim shaffof ko'k tekislik, z = sath (m). Sukutda model bbox ini
qoplaydi; `sath_region` xususiyati (xmin, xmax, ymin, ymax) o'rnatilgan bo'lsa o'sha mintaqada qoladi — keyingi
sath yangilanishlarida faqat z o'zgaradi."""

from __future__ import annotations

import bpy
from mathutils import Vector

NAME = "GES_SuvSathi"
TAIL_NAME = "GES_QuyiByef"
COLOR = (0.22, 0.72, 0.79, 0.4)
PLANES = (NAME, TAIL_NAME)


def _material(name: str = NAME):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.diffuse_color = COLOR
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
    return m


def _plane(context, name: str):
    ob = bpy.data.objects.get(name)
    if ob is None:
        me = bpy.data.meshes.new(name)
        me.from_pydata(
            [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)]
        )
        ob = bpy.data.objects.new(name, me)
        context.scene.collection.objects.link(ob)
        ob.data.materials.append(_material(name))
        ob.color = COLOR
        ob.show_transparent = True
    return ob


def place_plane(context, name: str, level_m: float, region: tuple[float, float, float, float] | None = None):
    """Tekislik `name` ni z = level ga; region berilsa (xmin, xmax, ymin, ymax) — o'sha mintaqa va eslab qolinadi."""
    ob = _plane(context, name)
    if region is None:
        region = ob.get("sath_region")
    if region is None:
        objs = [o for o in context.scene.objects if o.type == "MESH" and o.name not in PLANES]
        if not objs:
            return None
        xs, ys = [], []
        for o in objs:
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                xs.append(w.x)
                ys.append(w.y)
        pad = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.1
        region = (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)
    else:
        ob["sath_region"] = list(region)
    xmin, xmax, ymin, ymax = region
    ob.location = ((xmin + xmax) / 2, (ymin + ymax) / 2, level_m)
    ob.scale = (max(xmax - xmin, 1.0), max(ymax - ymin, 1.0), 1.0)
    return ob


def place_water_plane(context, level_m: float, region=None):
    return place_plane(context, NAME, level_m, region)


def place_tailwater_plane(context, level_m: float, region=None):
    return place_plane(context, TAIL_NAME, level_m, region)
