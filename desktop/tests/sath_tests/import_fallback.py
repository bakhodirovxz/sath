"""CAD-09: assimp-py bo'lmagan platforma (Linux/macOS wheel yo'q) — FBX Blender importeri bilan ochiladi."""

from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parents[1]


def run(ctx):
    from sath import ops_import
    from sath.shared import assimp_load

    orig = assimp_load.available
    assimp_load.available = lambda: False  # assimp-py yo'q deb
    try:
        warnings: list = []
        before = set(bpy.data.objects)
        n = ops_import.import_mesh(bpy.context, TESTS / "Namuna.fbx", report=warnings)
        assert n >= 1 and any("Blender importeri" in w for w in warnings), (n, warnings)
        m = [o for o in bpy.data.objects if o.type == "MESH" and o not in before]
        ws = [m[0].matrix_world @ v.co for v in m[0].data.vertices]  # dunyo o'lchami (obyekt burilgan)
        d = [max(w[i] for w in ws) - min(w[i] for w in ws) for i in range(3)]
        assert abs(d[0] - 0.5106) < 0.01 and abs(d[2] - 0.4062) < 0.01, d
        try:
            ops_import.import_mesh(bpy.context, TESTS / "Namuna.dwg")
            raise AssertionError("ImportError kutilgan")
        except ImportError as e:
            assert "assimp-py" in str(e)
    finally:
        assimp_load.available = orig
