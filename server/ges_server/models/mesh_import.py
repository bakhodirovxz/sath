"""Blender / 3ds Max / AutoCAD fayllarini IFC ga aylantirish (web yuklash) va teskari eksport.

To'g'ridan-to'g'ri (trimesh): OBJ (+MTL rang), STL, PLY, glTF/GLB, DAE, 3MF, OFF, DXF (3D yuzalar), ZAE.
Tashqi konverter orqali (serverda o'rnatilgan bo'lsa, Docker obrazida bor):
  FBX, 3DS, LWO, X → `assimp export` → glb;  DWG → `dwg2dxf` (LibreDWG) → dxf;  BLEND → `blender -b` → glb.
  .max — yopiq format: 3ds Max dan FBX/glTF/OBJ ga eksport qiling.
Har obyekt/mesh alohida IFC element: nom saqlanadi, rang (IfcSurfaceStyle), nom bo'yicha GES turi
(«togon/dam» → IfcWall + Pset_GES_Dam, «penstock/quvur» → IfcPipeSegment, …), birlik avto (glTF — metr,
DXF — $INSUNITS), Y-up → Z-up.
Eksport: IFC → glTF/GLB/OBJ/STL (Blender, 3ds Max da ochish uchun) — IfcOpenShell geometriyasidan.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .assimp_load import ASSIMP_EXTS
from .cad_import import CAD_EXTS

DIRECT = {".obj", ".stl", ".ply", ".gltf", ".glb", ".dae", ".3mf", ".off", ".dxf", ".zae"}
VIA_ASSIMP = ASSIMP_EXTS  # assimp-py (pip) yoki `assimp` CLI

VIA_DWG = {".dwg"}
VIA_BLENDER = {".blend"}
SUPPORTED = (
    DIRECT | VIA_ASSIMP | VIA_DWG | VIA_BLENDER | CAD_EXTS | {".zip"}
)  # zip: obj+mtl, gltf+bin, dae+tekstura
UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}
MAX_TRIANGLES = 2_000_000
DXF_UNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}  # $INSUNITS

# Nom bo'yicha GES turi: (regex, ifc_class, pset nomi, kind)
NAME_RULES: list[tuple[str, str, str, str]] = [
    (r"to.?g.?on|\bdam\b|plotina", "IfcWall", "Pset_GES_Dam", "dam"),
    (r"penstock|quvur|pipe|truba", "IfcPipeSegment", "Pset_GES_Penstock", "penstock"),
    (r"turbin|agregat|unit\d|generator", "IfcFlowMovingDevice", "Pset_GES_Turbine", "turbine"),
    (r"spillway|tashlag|vodosbros", "IfcSlab", "Pset_GES_Spillway", "spillway"),
    (r"transformator|transformer|trafo", "IfcTransformer", "", "transformer"),
    (
        r"mashina|powerhouse|zal|building|bino",
        "IfcBuildingElementProxy",
        "Pset_GES_Powerhouse",
        "powerhouse",
    ),
    (r"intake|qabul|vodozabor", "IfcBuildingElementProxy", "", "intake"),
    (r"slab|plita|\bpol\b|floor", "IfcSlab", "", "slab"),
    (r"wall|devor|stena", "IfcWall", "", "wall"),
    (r"column|ustun|kolonna", "IfcColumn", "", "column"),
    (r"beam|balka|to.?sin", "IfcBeam", "", "beam"),
    (r"roof|\btom\b|krysha", "IfcRoof", "", "roof"),
]


def classify(name: str) -> tuple[str, str, str]:
    """(ifc_class, pset, kind) — obyekt nomi bo'yicha; topilmasa proxy."""
    n = name.lower()
    for rx, cls, pset, kind in NAME_RULES:
        if re.search(rx, n):
            return cls, pset, kind
    return "IfcBuildingElementProxy", "", "mesh"


def _find(name: str, extra_dirs: list[Path]) -> str | None:
    """PATH, sozlamadagi tools_dir, va odatiy Windows papkalarida (Tools/*, Program Files/*) qidiradi."""
    found = shutil.which(name)
    if found:
        return found
    for d in extra_dirs:
        if not d or not d.exists():
            continue
        for cand in [d / name, d / f"{name}.exe", *d.glob(f"**/{name}"), *d.glob(f"**/{name}.exe")]:
            if cand.is_file():
                return str(cand)
    return None


def tools() -> dict[str, str | None]:
    """Serverda mavjud tashqi konverterlar (assimp — FBX/3DS, dwg2dxf/ODA — DWG, blender — .blend)."""
    from ..config import get_settings

    home = Path.home()
    dirs = [
        get_settings().tools_dir,
        home / "Tools",
        Path("C:/Tools"),
        Path("C:/Program Files/ODA"),
        Path("C:/Program Files/Blender Foundation"),
        Path("/opt/tools"),
    ]
    dirs = [d for d in dirs if d]
    return {
        "assimp": _find("assimp", dirs),
        "dwg2dxf": _find("dwg2dxf", dirs),
        "oda": _find("ODAFileConverter", dirs),
        "blender": _find("blender", dirs),
    }


def _convert_external(path: Path, tmp: Path) -> Path:
    ext = path.suffix.lower()
    t = tools()
    if ext in VIA_DWG:
        out = tmp / (path.stem + ".dxf")
        if t["dwg2dxf"]:
            r = subprocess.run(
                [t["dwg2dxf"], "-y", "-o", str(out), str(path)], timeout=300, capture_output=True
            )
            if not out.exists() or out.stat().st_size == 0:
                raise ValueError(
                    "DWG ni o'qib bo'lmadi (dwg2dxf): "
                    + (r.stderr or r.stdout)[-300:].decode(errors="replace")
                )
            return out
        if t["oda"]:
            # ODA File Converter: <in_dir> <out_dir> <version> <type> <recurse> <audit> [filter]
            in_dir, out_dir = tmp / "oda_in", tmp / "oda_out"
            in_dir.mkdir()
            out_dir.mkdir()
            shutil.copy(path, in_dir / path.name)
            subprocess.run(
                [t["oda"], str(in_dir), str(out_dir), "ACAD2018", "DXF", "0", "1", path.name],
                timeout=600,
                capture_output=True,
            )
            res = out_dir / (path.stem + ".dxf")
            if not res.exists():
                raise ValueError("DWG ni o'qib bo'lmadi (ODA File Converter)")
            return res
        raise ValueError(
            "DWG uchun serverda konverter yo'q: LibreDWG (dwg2dxf) yoki ODA File Converter o'rnating "
            "(GES_TOOLS_DIR yoki ~/Tools) — yoki AutoCAD dan DXF ga saqlang (SAVEAS → DXF)"
        )
    if ext in VIA_BLENDER:
        if not t["blender"]:
            raise ValueError(
                ".blend uchun serverda Blender yo'q — Blender dan File → Export → glTF/OBJ qiling "
                "(yoki Sath Blender addoni)"
            )
        out = tmp / (path.stem + ".glb")
        script = tmp / "exp.py"
        script.write_text(
            "import bpy,sys\nout=sys.argv[-1]\n"
            "bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True, export_yup=False)\n",
            encoding="utf-8",
        )
        subprocess.run(
            [t["blender"], "-b", str(path), "--python", str(script), "--", str(out)],
            check=True,
            timeout=600,
            capture_output=True,
        )
        return out
    if ext in CAD_EXTS:
        from . import cad_import

        if not cad_import.available():
            raise ValueError(
                f"{ext.upper()} uchun serverda OpenCASCADE (pip install cadquery-ocp) yo'q — yoki CAD dasturidan "
                "STL/glTF ga eksport qiling"
            )
        return path
    if ext in VIA_ASSIMP:
        from . import assimp_load

        if assimp_load.available():
            return path  # load_objects to'g'ridan-to'g'ri assimp-py bilan o'qiydi
        if not t["assimp"]:
            raise ValueError(
                f"{ext.upper()} uchun serverda Assimp yo'q (pip install assimp-py) — yoki Blender/3ds Max dan "
                "glTF/OBJ ga eksport qiling"
            )
        out = tmp / (path.stem + ".glb")
        subprocess.run(
            [t["assimp"], "export", str(path), str(out), "-tri"],
            check=True,
            timeout=600,
            capture_output=True,
        )
        return out
    return path


def detect_unit(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in (".gltf", ".glb"):
        return "m"  # spesifikatsiya bo'yicha metr
    if ext == ".3mf":
        return "mm"  # 3MF default
    if ext in CAD_EXTS:
        return "mm"  # OpenCASCADE STEP/IGES ni mm ga keltiradi
    if ext == ".dxf":
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:6000]
            for i, line in enumerate(lines):
                if (
                    line.strip() == "$INSUNITS"
                    and i + 2 < len(lines)
                    and lines[i + 1].strip() == "70"
                ):
                    return DXF_UNITS.get(int(lines[i + 2].strip()))
        except (OSError, ValueError):
            return None
    return None


def _load_mtl(path: Path) -> dict[str, tuple]:
    mats: dict[str, tuple] = {}
    cur = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "newmtl" and len(p) > 1:
            cur = p[1]
        elif p[0] == "Kd" and cur and len(p) >= 4:
            mats[cur] = (float(p[1]), float(p[2]), float(p[3]))
    return mats


def _load_obj(path: Path) -> list[tuple[str, np.ndarray, np.ndarray, tuple | None]]:
    """OBJ ni obyektlar (o/g) va materiallar bo'yicha o'zimiz ajratamiz (Blender/3ds Max eksporti);
    ko'pburchaklar yelpig'ich; MTL dan diffuz rang (Kd)."""
    verts: list[list[float]] = []
    objects: list[tuple[str, list[list[int]], str | None]] = []
    cur_name, cur_faces, cur_mat = path.stem, [], None
    mtl: dict[str, tuple] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line[0] == "#":
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v" and len(parts) >= 4:
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif tag in ("o", "g"):
            if cur_faces:
                objects.append((cur_name, cur_faces, cur_mat))
            cur_name, cur_faces = (" ".join(parts[1:]) or cur_name), []
        elif tag == "usemtl" and len(parts) > 1:
            if cur_faces:  # obyekt ichida material o'zgarsa — alohida element
                objects.append((cur_name, cur_faces, cur_mat))
                cur_faces = []
            cur_mat = parts[1]
        elif tag == "mtllib" and len(parts) > 1:
            mp = path.parent / " ".join(parts[1:])
            if mp.exists():
                mtl.update(_load_mtl(mp))
        elif tag == "f" and len(parts) >= 4:
            idx = []
            for tok in parts[1:]:
                i = int(tok.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            for k in range(1, len(idx) - 1):
                cur_faces.append([idx[0], idx[k], idx[k + 1]])
    if cur_faces:
        objects.append((cur_name, cur_faces, cur_mat))
    out = []
    v_all = np.asarray(verts, dtype=float)
    for name, faces, mat in objects:
        f = np.asarray(faces, dtype=int)
        used = np.unique(f)
        remap = {int(o): i for i, o in enumerate(used)}
        out.append((name, v_all[used], np.vectorize(remap.get)(f), mtl.get(mat or "")))
    return out


def _color_of(m) -> tuple | None:
    try:
        vis = m.visual
        mat = getattr(vis, "material", None)
        if mat is not None:
            c = getattr(mat, "baseColorFactor", None)
            if c is None:
                c = getattr(mat, "diffuse", None)
            if c is not None:
                c = np.asarray(c, dtype=float)
                if c.max() > 1.0:
                    c = c / 255.0
                return (float(c[0]), float(c[1]), float(c[2]))
        if hasattr(vis, "main_color"):
            c = np.asarray(vis.main_color, dtype=float) / 255.0
            return (float(c[0]), float(c[1]), float(c[2]))
    except Exception:  # noqa: BLE001 — rang ixtiyoriy
        return None
    return None


def _fix_dxf_handles(path: Path) -> Path:
    """Konverter (dwg2dxf) chiqargan DXF da ba'zi obyektlar «0» handle bilan bo'ladi — ezdxf buni rad etadi.
    Bunday handle larni maksimaldan yuqori yangi qiymat bilan almashtirib vaqtinchalik nusxa qaytaradi."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    mx = 0
    for i in range(0, len(lines) - 1, 2):
        if lines[i].strip() in ("5", "105"):
            try:
                mx = max(mx, int(lines[i + 1].strip() or "0", 16))
            except ValueError:
                continue
    changed = False
    for i in range(0, len(lines) - 1, 2):
        if lines[i].strip() in ("5", "105") and lines[i + 1].strip() in ("", "0"):
            mx += 1
            lines[i + 1] = f"{mx:X}"
            changed = True
    if not changed:
        return path
    fixed = path.with_name(path.stem + "_fixed.dxf")
    fixed.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return fixed


def _read_dxf(path: Path):
    """DXF ni ochish: avval oddiy, keyin tiklash rejimi (recover), keyin handle larni tuzatib."""
    import ezdxf
    from ezdxf import recover

    try:
        return ezdxf.readfile(str(path))
    except Exception:  # noqa: BLE001 — buzuq/noto'liq DXF → tiklash
        pass
    try:
        doc, _aud = recover.readfile(str(path))
        return doc
    except Exception:  # noqa: BLE001
        pass
    fixed = _fix_dxf_handles(path)
    try:
        return ezdxf.readfile(str(fixed))
    except Exception:  # noqa: BLE001
        doc, _aud = recover.readfile(str(fixed))
        return doc


def _load_dxf(
    path: Path, extrude_m: float = 0.0
) -> list[tuple[str, np.ndarray, np.ndarray, tuple | None]]:
    """DXF (AutoCAD): 3DFACE, POLYLINE (polyface/polymesh), MESH, SOLID → uchburchaklar; yopiq 2D konturlar
    (LWPOLYLINE/POLYLINE/CIRCLE) extrude_m > 0 bo'lsa balandlikka ko'tariladi. Qatlam (layer) = obyekt nomi;
    3DSOLID/REGION (ACIS) o'qilmaydi — AutoCAD da 3DSOLID ni MESH ga aylantiring (MESHSMOOTH / EXPORT → FBX/OBJ)."""
    from ezdxf import colors as dxfcolors

    doc = _read_dxf(path)
    msp = doc.modelspace()
    layers: dict[str, list[list[list[float]]]] = {}  # layer → [triangles (3 nuqta)]
    acis = 0

    def add(layer: str, pts: list) -> None:
        pts = [list(map(float, tuple(p)[:3])) for p in pts]  # Vec3 kesilmaydi → tuple
        if len(pts) < 3:
            return
        tris = layers.setdefault(layer, [])
        for k in range(1, len(pts) - 1):
            tris.append([pts[0], pts[k], pts[k + 1]])

    for e in msp:
        t = e.dxftype()
        try:
            if t in ("3DFACE", "SOLID", "TRACE"):
                pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
                uniq = []
                for p in pts:
                    if not uniq or tuple(p) != tuple(uniq[-1]):
                        uniq.append(p)
                add(e.dxf.layer, uniq)
            elif t == "MESH":
                md = e.get_data()
                vs = [list(v) for v in md.vertices]
                for face in md.faces:
                    add(e.dxf.layer, [vs[int(i)] for i in face])
            elif t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh):
                if e.is_poly_face_mesh:
                    vs = [list(v.dxf.location) for v in e.vertices if v.is_poly_face_mesh_vertex]
                    for f in e.vertices:
                        if f.is_face_record:
                            idx = [abs(int(getattr(f.dxf, f"vtx{k}", 0))) for k in range(4)]
                            idx = [i - 1 for i in idx if i > 0]
                            add(e.dxf.layer, [vs[i] for i in idx if i < len(vs)])
                else:
                    m = (
                        e.get_polygon_mesh_vertex_matrix()
                        if hasattr(e, "get_polygon_mesh_vertex_matrix")
                        else None
                    )
                    if m is not None:
                        for i in range(m.m - 1):
                            for j in range(m.n - 1):
                                add(
                                    e.dxf.layer,
                                    [
                                        list(m[i, j]),
                                        list(m[i + 1, j]),
                                        list(m[i + 1, j + 1]),
                                        list(m[i, j + 1]),
                                    ],
                                )
            elif extrude_m > 0 and t in ("LWPOLYLINE", "POLYLINE", "CIRCLE"):
                if t == "CIRCLE":
                    import math

                    c, r = e.dxf.center, e.dxf.radius
                    ring = [
                        (c.x + r * math.cos(a), c.y + r * math.sin(a), c.z)
                        for a in np.linspace(0, 2 * math.pi, 32, endpoint=False)
                    ]
                elif t == "LWPOLYLINE":
                    if not e.closed:
                        continue
                    z = e.dxf.elevation
                    ring = [(x, y, z) for x, y, *_ in e.get_points()]
                else:
                    if not e.is_closed:
                        continue
                    ring = [tuple(v.dxf.location) for v in e.vertices]
                if len(ring) < 3:
                    continue
                _extrude(layers.setdefault(e.dxf.layer, []), ring, extrude_m)
            elif t in ("3DSOLID", "REGION", "BODY", "SURFACE"):
                acis += 1
        except Exception:  # noqa: BLE001 — bitta buzuq element importni to'xtatmasin
            continue
    if not layers:
        if acis:
            raise ValueError(
                f"DXF da {acis} ta 3DSOLID/REGION (ACIS) bor — ular o'qilmaydi. AutoCAD da MESHSMOOTH bilan MESH ga "
                "aylantiring yoki EXPORT → OBJ/FBX; 2D chizma bo'lsa «balandlikka ko'tarish» ni kiriting"
            )
        # 3D yuza yo'q — oddiy 2D chizma (plan/kesim): chiziqlarni yupqa lentalar sifatida qatlam bo'yicha
        # elementlarga aylantiramiz, shunda chizma 3D ko'rgichda tekis varaq bo'lib ko'rinadi
        try:  # bloklar, o'lchamlar, matn (harf konturlari), shtrix, chiqish → oddiy chiziqlar (AutoCAD ko'rinishi)
            from .dxf_flatten import flatten

            flatten(doc)
        except Exception:  # noqa: BLE001 — tekislash o'tmasa xom chiziqlar bilan davom
            pass
        _dxf_linework(msp, layers)
        if not layers:
            raise ValueError(
                "DXF da geometriya topilmadi (3DFACE/MESH/polyface yoki chiziqlar); 2D kontur bo'lsa «balandlikka "
                "ko'tarish» ni kiriting"
            )
    out = []
    offset = layers.pop("__offset__", None)
    for key, tris in layers.items():
        layer, aci = key if isinstance(key, tuple) else (key, 256)
        v = np.asarray(tris, dtype=float).reshape(-1, 3)
        f = np.arange(len(v)).reshape(-1, 3)
        col = None
        name = layer
        try:
            lay = doc.layers.get(layer)
            lay_aci = lay.color if lay is not None and lay.color > 0 else 7
            if aci in (256, 0, lay_aci):
                aci = lay_aci
            else:
                name = (
                    f"{layer} ({_ACI_NAMES.get(aci, aci)})"  # elementning o'z rangi (BYLAYER emas)
                )
            # ACI 7 (oq/qora — fonga qarab) → kulrang, har ikki fonda ko‘rinsin
            rgb = (150, 150, 150) if aci == 7 else dxfcolors.aci2rgb(aci)
            col = tuple(c / 255 for c in rgb)
        except Exception:  # noqa: BLE001
            col = None
        out.append((name, v, f, col))
    if offset is not None:
        _LAST_DXF_INFO.update(offset=offset[:2], extent=offset[2], linework=True)
    return out


_LAST_DXF_INFO: dict = {}  # oxirgi _load_dxf: {"offset": (x, y), "extent": float, "linework": bool}


_ACI_NAMES = {
    1: "qizil",
    2: "sariq",
    3: "yashil",
    4: "havorang",
    5: "ko'k",
    6: "binafsha",
    8: "kulrang",
}


def _simplify(pts: list, tol: float) -> list:
    """Douglas–Peucker: chiziqda tol dan kam og'gan nuqtalarni olib tashlaydi (shrift konturlari, yoylar)."""
    if len(pts) < 3 or tol <= 0:
        return pts
    a = np.asarray([(q[0], q[1]) for q in pts], dtype=float)
    keep = np.zeros(len(a), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(a) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = a[j] - a[i]
        ln = float(np.hypot(*seg))
        d = (
            np.abs(np.cross(seg, a[i + 1 : j] - a[i])) / ln
            if ln > 1e-12
            else np.hypot(*(a[i + 1 : j] - a[i]).T)
        )
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [q for q, k in zip(pts, keep, strict=False) if k]


_LINEWORK_SKIP_LAYERS = {"defpoints"}


def _dxf_linework(msp, layers: dict, depth: int = 0) -> None:
    """2D chizma (LINE/ARC/CIRCLE/ELLIPSE/SPLINE/polyline, bloklar, o'lcham chiziqlari) → har segment yupqa
    lenta (2 uchburchak) — chizma o'lchamining ~0.05 % kengligida; matn/shtrix tashlab ketiladi."""
    from ezdxf import path as dxfpath

    pts_all: list[tuple[float, float]] = []
    polys: list[tuple[tuple[str, int], list]] = []
    lay_colors: dict[str, int] = {}
    try:
        for lay in msp.doc.layers:
            lay_colors[lay.dxf.name] = lay.color if lay.color > 0 else 7
    except Exception:  # noqa: BLE001
        pass

    def walk(entities, d: int) -> None:
        for e in entities:
            t = e.dxftype()
            try:
                if t in ("INSERT", "DIMENSION", "LEADER", "MULTILEADER", "MLINE") and d < 4:
                    walk(e.virtual_entities(), d + 1)
                    continue
                if t not in (
                    "LINE",
                    "ARC",
                    "CIRCLE",
                    "ELLIPSE",
                    "SPLINE",
                    "LWPOLYLINE",
                    "POLYLINE",
                    "HELIX",
                ):
                    continue
                layer = str(e.dxf.layer or "0")
                if layer.lower() in _LINEWORK_SKIP_LAYERS:
                    continue
                pth = dxfpath.make_path(e)
                cv = list(pth.control_vertices())
                span = 1.0
                if cv:
                    xs_, ys_ = [q.x for q in cv], [q.y for q in cv]
                    span = max(max(xs_) - min(xs_), max(ys_) - min(ys_), 1.0)
                pts = [tuple(v) for v in pth.flattening(span / 100)]  # yoy/spline → segmentlar
                if len(pts) >= 2:
                    aci = int(e.dxf.get("color", 256) or 256)
                    if aci in (
                        0,
                        256,
                    ):  # BYBLOCK/BYLAYER → qatlam rangi (bitta elementga birlashsin)
                        aci = lay_colors.get(layer, 7)
                    polys.append(((layer, aci), pts))
                    pts_all.extend((q[0], q[1]) for q in pts)
            except Exception:  # noqa: BLE001 — bitta buzuq element chizmani to'xtatmasin
                continue

    walk(msp, depth)
    if not polys:
        return
    xs = [q[0] for q in pts_all]
    ys = [q[1] for q in pts_all]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    w = extent * 0.0005  # lenta kengligi (chizma birligida)
    # Chizma ko'pincha geodezik/lokal to'r koordinatalarida (masalan x≈532 000) — 3D ko'rgichda uzoqda va
    # aniqlik yo'qoladi; chap-pastki burchagini (0,0) ga ko'chiramiz, asl siljish Pset ga yoziladi
    ox, oy = min(xs), min(ys)
    layers["__offset__"] = (ox, oy, extent)
    for key, pts in polys:
        tris = layers.setdefault(key, [])
        pts = _simplify(pts, w / 2)  # ko'rinmaydigan og'ishlar — uchburchaklar 3–5 barobar kam
        pts = [
            (q[0] - ox, q[1] - oy, 0.0) for q in pts
        ]  # 2D chizma — tekis (adashgan Z lar tashlanadi)
        for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:], strict=False):
            dx, dy = x1 - x0, y1 - y0
            ln = (dx * dx + dy * dy) ** 0.5
            if ln < 1e-9:
                continue
            nx, ny = -dy / ln * w / 2, dx / ln * w / 2
            a = [x0 + nx, y0 + ny, z0]
            b = [x1 + nx, y1 + ny, z1]
            c = [x1 - nx, y1 - ny, z1]
            d = [x0 - nx, y0 - ny, z0]
            tris.append([a, c, b])  # normal +Z: chizma yuqoridan (plan) ko'rinsin
            tris.append([a, d, c])


def _extrude(tris: list, ring: list, h: float) -> None:
    """Yopiq kontur → prizma (tub, tepa — yelpig'ich; yon devorlar)."""
    n = len(ring)
    base = [list(map(float, p)) for p in ring]
    top = [[p[0], p[1], p[2] + h] for p in base]
    for k in range(1, n - 1):
        tris.append([base[0], base[k + 1], base[k]])
        tris.append([top[0], top[k], top[k + 1]])
    for i in range(n):
        j = (i + 1) % n
        tris.append([base[i], base[j], top[j]])
        tris.append([base[i], top[j], top[i]])


def load_objects(
    path: Path,
    unit: str = "m",
    y_up: bool = False,
    merge: bool = False,
    auto_unit: bool = True,
    classify_names: bool = True,
    extrude_m: float = 0.0,
) -> list[dict]:
    """Fayl → [{name, kind, ifc_class, psets, color, mesh:{vertices, faces}, transform}] (drafts.build formati)."""
    import trimesh

    with tempfile.TemporaryDirectory(prefix="ges-conv-") as tmp:
        if path.suffix.lower() == ".zip":
            import zipfile

            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if not n.startswith("__MACOSX") and ".." not in n]
                if sum(i.file_size for i in z.infolist()) > 2_000_000_000:
                    raise ValueError("ZIP juda katta")
                z.extractall(tmp, members=names)
            cands = [
                q
                for q in Path(tmp).rglob("*")
                if q.suffix.lower() in (DIRECT | VIA_ASSIMP | VIA_DWG | VIA_BLENDER)
            ]
            if not cands:
                raise ValueError("ZIP ichida 3D fayl topilmadi (obj/gltf/dae/…)")
            path = sorted(cands, key=lambda q: (q.suffix.lower() != ".obj", str(q)))[0]
        src = _convert_external(path, Path(tmp))
        if auto_unit:
            unit = detect_unit(src) or unit
        scale = UNITS.get(unit, 1.0)
        meshes: list[tuple[str, trimesh.Trimesh, tuple | None]] = []
        loaded = None
        if src.suffix.lower() == ".obj" and not merge:
            for name, v, f, col in _load_obj(src):
                meshes.append((name, trimesh.Trimesh(vertices=v, faces=f, process=False), col))
        elif src.suffix.lower() in CAD_EXTS:
            from . import cad_import

            for o in cad_import.load(src):
                meshes.append(
                    (
                        o["name"],
                        trimesh.Trimesh(vertices=o["vertices"], faces=o["faces"], process=False),
                        o["color"],
                    )
                )
        elif src.suffix.lower() in VIA_ASSIMP:
            from . import assimp_load

            for o in assimp_load.load(src):
                meshes.append(
                    (
                        o["name"],
                        trimesh.Trimesh(vertices=o["vertices"], faces=o["faces"], process=False),
                        o["color"],
                    )
                )
        elif src.suffix.lower() == ".dxf":
            _LAST_DXF_INFO.clear()
            for name, v, f, col in _load_dxf(
                src, extrude_m / scale
            ):  # ko'tarish metrda → chizma birligi
                meshes.append((name, trimesh.Trimesh(vertices=v, faces=f, process=False), col))
            if _LAST_DXF_INFO.get("linework") and auto_unit and unit == "mm":
                # AutoCAD odatiy $INSUNITS=mm, lekin ko'p chizmalar metrda chiziladi: varaq (ramka) 200 mm dan
                # kichik bo'lishi mumkin emas → bu metr
                if _LAST_DXF_INFO.get("extent", 1e9) < 200:
                    unit, scale = "m", 1.0
                    _LAST_DXF_INFO["unit_guess"] = "m (chizma 200 mm dan kichik — metr deb olindi)"
        else:
            loaded = trimesh.load(str(src), force="scene" if not merge else "mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            for name, geom in loaded.geometry.items():
                if not isinstance(geom, trimesh.Trimesh) or geom.faces.shape[0] == 0:
                    continue
                nodes = [n for n in loaded.graph.nodes_geometry if loaded.graph[n][1] == name] or [
                    None
                ]
                for i, node in enumerate(nodes):
                    m = geom.copy()
                    if node is not None:
                        m.apply_transform(loaded.graph[node][0])
                    label = (node or name) if len(nodes) == 1 else f"{name}_{i + 1}"
                    meshes.append((str(label), m, _color_of(geom)))
        elif isinstance(loaded, trimesh.Trimesh):
            meshes.append((path.stem, loaded, _color_of(loaded)))
        elif loaded is not None:
            raise ValueError("Faylda 3D mesh topilmadi")
    if not meshes:
        raise ValueError("Faylda 3D mesh topilmadi (faqat chiziqlar/nuqtalar?)")
    total = sum(int(m.faces.shape[0]) for _, m, _ in meshes)
    if total > MAX_TRIANGLES:
        raise ValueError(
            f"Juda ko'p uchburchak: {total} > {MAX_TRIANGLES} — Blender da Decimate qiling"
        )
    out = []
    for name, m, col in meshes:
        v = np.asarray(m.vertices, dtype=float) * scale
        if y_up:  # Y yuqoriga → Z yuqoriga: (x, y, z) → (x, −z, y)
            v = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
        f = np.asarray(m.faces, dtype=int)
        c = v.mean(axis=0)
        v = v - c
        cls, pset, kind = (
            classify(name) if classify_names else ("IfcBuildingElementProxy", "", "mesh")
        )
        ext = v.max(axis=0) - v.min(axis=0)
        psets: dict[str, dict] = {
            "Pset_GES_Import": {
                "Manba": path.suffix.lower().lstrip("."),
                "Uchburchaklar": int(f.shape[0]),
                "Birlik": unit,
                **(
                    {
                        "Asl_siljish_X": round(float(_LAST_DXF_INFO["offset"][0]), 3),
                        "Asl_siljish_Y": round(float(_LAST_DXF_INFO["offset"][1]), 3),
                    }
                    if src.suffix.lower() == ".dxf" and _LAST_DXF_INFO.get("offset")
                    else {}
                ),
                **(
                    {"Birlik_izoh": _LAST_DXF_INFO["unit_guess"]}
                    if src.suffix.lower() == ".dxf" and _LAST_DXF_INFO.get("unit_guess")
                    else {}
                ),
            }
        }
        if pset == "Pset_GES_Dam":
            psets[pset] = {
                "Balandlik_m": round(float(ext[2]), 2),
                "Uzunlik_m": round(float(max(ext[0], ext[1])), 2),
                "TagKengligi_m": round(float(min(ext[0], ext[1])), 2),
            }
        elif pset == "Pset_GES_Penstock":
            psets[pset] = {
                "Uzunlik_m": round(float(ext.max()), 2),
                "Diametr_m": round(float(sorted(ext)[1]), 2),
            }
        elif pset:
            psets[pset] = {}
        out.append(
            {
                "kind": kind,
                "name": str(name)[:120] or "Mesh",
                "ifc_class": cls,
                "color": col,
                "transform": {"x": float(c[0]), "y": float(c[1]), "z": float(c[2]), "rz": 0.0},
                "psets": psets,
                "mesh": {"vertices": v.round(5).tolist(), "faces": f.tolist()},
            }
        )
    return out


# --- IFC → glTF / OBJ / STL (Blender, 3ds Max uchun) ---
def export_ifc(path: Path, fmt: str = "glb") -> bytes:
    """IFC dan barcha elementlar geometriyasi (dunyo koordinatalari, metr, ranglar) → glb/obj/stl baytlar;
    element nomi va GUID saqlanadi (Blender da obyekt nomi = "Nom [GUID]")."""
    import ifcopenshell
    import ifcopenshell.geom
    import trimesh

    f = ifcopenshell.open(str(path))
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    scene = trimesh.Scene()
    it = ifcopenshell.geom.iterator(s, f, 1)
    if it.initialize():
        while True:
            sh = it.get()
            try:
                el = f.by_id(sh.id)
                v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
                fc = np.asarray(sh.geometry.faces, dtype=int).reshape(-1, 3)
                if len(fc):
                    m = trimesh.Trimesh(vertices=v, faces=fc, process=False)
                    mats = list(sh.geometry.materials)
                    if mats and getattr(mats[0], "diffuse", None) is not None:
                        d = mats[0].diffuse
                        rgb = [d.r(), d.g(), d.b()] if hasattr(d, "r") else list(d)[:3]
                        m.visual.face_colors = [
                            int(max(min(float(x), 1), 0) * 255) for x in rgb
                        ] + [255]
                    name = f"{el.Name or el.is_a()} [{el.GlobalId}]"
                    scene.add_geometry(m, node_name=name, geom_name=name)
            except Exception:  # noqa: BLE001 — bitta element xatosi eksportni to'xtatmasin
                pass
            if not it.next():
                break
    if not scene.geometry:
        raise ValueError("IFC da geometriya topilmadi")
    if fmt == "obj":
        data = scene.export(file_type="obj")
        return data.encode("utf-8") if isinstance(data, str) else data
    if fmt == "stl":
        return scene.to_mesh().export(file_type="stl")
    return scene.export(file_type="glb")
