# Sath app template: Blender ochilganda GES-BIM ish muhiti — N-panel ochiq (Sath yorlig'i),
# viewport Object-color rejimi (diff/alarm ranglari uchun), metr birliklari.

import bpy
from bpy.app.handlers import persistent


def _setup_screens():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.show_region_ui = True
                space.shading.color_type = "OBJECT"
                space.overlay.show_relationship_lines = False


def _setup_scenes():
    for scene in bpy.data.scenes:
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.length_unit = "METERS"
        scene.unit_settings.scale_length = 1.0


@persistent
def load_handler(_):
    _setup_screens()
    _setup_scenes()


def register():
    bpy.app.handlers.load_factory_startup_post.append(load_handler)


def unregister():
    bpy.app.handlers.load_factory_startup_post.remove(load_handler)
