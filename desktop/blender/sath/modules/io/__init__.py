"""Fayl I/O moduli: DWG/DXF (ezdxf, LibreDWG/ODA) va mesh (assimp) import — serverga ulanmasdan ishlaydi.
4-quyi-loyihada ochiq formatlar round-trip va konnektorlar shu modulga qo'shiladi."""

from __future__ import annotations

import bpy

from ... import ops_import
from ...core.panels import SathPanel


class SATH_PT_import(SathPanel, bpy.types.Panel):
    bl_label = "Import"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("sath.import_dxf", icon="GREASEPENCIL")
        col.operator("sath.import_mesh", icon="MESH_DATA")


def _menu(layout, context):
    layout.operator("sath.import_dxf")
    layout.operator("sath.import_mesh")


def register(api):
    api.adopt("io", ops_import)  # File → Import bandlari ham (ops_import.register)
    api.register_classes("io", [SATH_PT_import])
    api.ui.main_menu("io", _menu)
