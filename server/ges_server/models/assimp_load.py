"""Assimp (assimp-py, pip) bilan har qanday 3D formatni o'qish: FBX, 3DS, LWO/LWS, X, ASE, AC, MS3D, COB,
OGEX, B3D, MD2/MD3/MD5, SMD, NFF, AMF, IRRMESH, … (assimp 5.x 40+ format).

Natija — oddiy ro'yxat: [{name, vertices (N×3, float), faces (M×3, int), color (r,g,b) yoki None}].
Tugun (node) daraxti bo'ylab yuriladi: har mesh o'z tugun nomi va yig'ilgan transformatsiyasi bilan —
Blender/3ds Max dagi obyekt nomlari saqlanadi (FBX ning $AssimpFbx$ yordamchi tugunlari nomga kirmaydi).
Server (web import) va desktop (FreeCAD) da bir xil nusxa (server/ges_server/models/assimp_load.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

# assimp o'qiy oladigan, lekin trimesh/FreeCAD o'zi o'qimaydigan formatlar
ASSIMP_EXTS = {
    ".fbx",
    ".3ds",
    ".lwo",
    ".lws",
    ".x",
    ".ase",
    ".ac",
    ".ms3d",
    ".cob",
    ".scn",
    ".ogex",
    ".b3d",
    ".md2",
    ".md3",
    ".md5mesh",
    ".mdl",
    ".smd",
    ".nff",
    ".amf",
    ".irrmesh",
    ".irr",
    ".q3o",
    ".q3s",
    ".ter",
    ".hmp",
    ".xgl",
    ".zgl",
    ".ndo",
    ".sib",
    ".bvh",
    ".csm",
    ".x3d",
    ".blend",  # eski (2.7x) Blender fayllari; yangilari uchun Blender/glTF
}


def available() -> bool:
    try:
        import assimp_py  # noqa: F401

        return True
    except ImportError:
        return False


def _node_name(name: str, parent: str | None) -> str | None:
    if not name or "$AssimpFbx$" in name or name in ("RootNode", "ROOT", "Scene", "root"):
        return parent
    return name


def load(path: str | os.PathLike) -> list[dict]:
    import assimp_py

    flags = (
        assimp_py.Process_Triangulate
        | assimp_py.Process_JoinIdenticalVertices
        | assimp_py.Process_SortByPType
        | assimp_py.Process_FindDegenerates
        | assimp_py.Process_ValidateDataStructure
    )
    scene = assimp_py.import_file(str(Path(path)), flags)
    mats = list(scene.materials or [])
    out: list[dict] = []

    def color_of(idx: int):
        if 0 <= idx < len(mats):
            c = mats[idx].get("COLOR_DIFFUSE")
            if c and len(c) >= 3 and max(c[:3]) > 0:
                return (float(c[0]), float(c[1]), float(c[2]))
        return None

    def walk(node, parent_m: np.ndarray, parent_name: str | None) -> None:
        m = parent_m @ np.asarray(node.transformation, dtype=float).reshape(4, 4)
        name = _node_name(node.name, parent_name)
        for mi in node.mesh_indices or []:
            mesh = scene.meshes[mi]
            v = np.frombuffer(mesh.vertices, dtype=np.float32).reshape(-1, 3).astype(float)
            f = np.frombuffer(mesh.indices, dtype=np.uint32).reshape(-1, 3).astype(int)
            if len(v) == 0 or len(f) == 0:
                continue
            vh = np.hstack([v, np.ones((len(v), 1))]) @ m.T
            out.append(
                {
                    "name": name or mesh.name or Path(path).stem,
                    "vertices": vh[:, :3],
                    "faces": f,
                    "color": color_of(mesh.material_index),
                }
            )
        for child in node.children or []:
            walk(child, m, name)

    walk(scene.root_node, np.eye(4), None)
    if not out:
        raise ValueError("Faylda mesh topilmadi (assimp)")
    return out
