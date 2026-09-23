"""CAD import umumiy yordamchilari — server (web import), Blender addoni va FreeCAD workbench uchun bitta kod.

* `detect_units_and_axis(path)` — fayl birligi va yuqori o'q: DXF `$INSUNITS`, FBX `GlobalSettings`
  (`UnitScaleFactor`, `UpAxis`), glTF (spetsifikatsiya: metr, Y-up), 3MF/STEP (mm). Aniqlanmasa `uncertain=True`
  — chaqiruvchi foydalanuvchidan so'raydi yoki natijada belgi qaytaradi, jimgina taxmin qilmaydi (CAD-04).
* `dxf_face_vertices` / `dxf_triangles` / `iter_dxf_entities` — DXF 3D yuzalar: SOLID/TRACE 0-1-3-2, 3DFACE
  0-1-2-3 tartib (CAD-02), INSERT bloklar rekursiv, transformatsiya bilan (CAD-03).
* `split_guid` / `guid_from_props` / `gltf_node_guids` — eksportdagi `"Nom [GUID]"` va `sath_guid` xususiyatini
  qayta importda o'qish (CAD-07).
* `classify_name` — obyekt nomi bo'yicha GES turi / IFC sinfi.

Sof Python (bpy, FreeCAD, numpy siz); ezdxf faqat DXF funksiyalarida (argument sifatida entity keladi).
Kanonik manba: common/sath_common/cad_common.py; nusxalar desktop/build/sync_blender.py bilan yangilanadi (qo'lda tahrirlamang).
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}
DXF_INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}  # $INSUNITS kodi → birlik
MM_EXTS = {".3mf", ".step", ".stp", ".iges", ".igs", ".brep"}  # 3MF default; OpenCASCADE mm ga keltiradi
GLTF_EXTS = {".gltf", ".glb"}
# Birlik/o'q ma'lumoti faylda bo'lmaganda odatiy yuqori o'q (faqat taklif — uncertain bilan qaytadi)
DEFAULT_Y_UP = {
    ".fbx", ".obj", ".x", ".dae", ".ms3d", ".md2", ".md3", ".md5mesh", ".smd", ".b3d", ".lwo", ".lws",
}  # fmt: skip
DEFAULT_Z_UP = {".3ds", ".ase", ".dxf", ".dwg", ".stl", ".ply", ".off", ".blend"} | MM_EXTS

# Nom bo'yicha GES turi: (regex, ifc_class, pset nomi, kind)
NAME_RULES: list[tuple[str, str, str, str]] = [
    (r"to.?g.?on|\bdam\b|plotina", "IfcWall", "Pset_GES_Dam", "dam"),
    (r"penstock|quvur|pipe|truba", "IfcPipeSegment", "Pset_GES_Penstock", "penstock"),
    (r"turbin|agregat|unit\d|generator", "IfcFlowMovingDevice", "Pset_GES_Turbine", "turbine"),
    (r"spillway|tashlag|vodosbros", "IfcSlab", "Pset_GES_Spillway", "spillway"),
    (r"transformator|transformer|trafo", "IfcTransformer", "", "transformer"),
    (r"mashina|powerhouse|zal|building|bino", "IfcBuildingElementProxy", "Pset_GES_Powerhouse", "powerhouse"),
    (r"intake|qabul|vodozabor", "IfcBuildingElementProxy", "", "intake"),
    (r"slab|plita|\bpol\b|floor", "IfcSlab", "", "slab"),
    (r"wall|devor|stena", "IfcWall", "", "wall"),
    (r"column|ustun|kolonna", "IfcColumn", "", "column"),
    (r"beam|balka|to.?sin", "IfcBeam", "", "beam"),
    (r"roof|\btom\b|krysha", "IfcRoof", "", "roof"),
]


def classify_name(name: str) -> tuple[str, str, str]:
    """(ifc_class, pset, kind) — obyekt nomi bo'yicha; topilmasa IfcBuildingElementProxy."""
    n = (name or "").lower()
    for rx, cls, pset, kind in NAME_RULES:
        if re.search(rx, n):
            return cls, pset, kind
    return "IfcBuildingElementProxy", "", "mesh"


# --- birlik va o'q (CAD-04) ------------------------------------------------------------------------------------


@dataclass
class UnitInfo:
    """Fayl birligi va yuqori o'qi. unit — UNITS kaliti yoki None (noma'lum); scale — 1 birlik necha metr;
    up_axis — "Y" / "Z" / None; source — qayerdan aniqlandi; uncertain — foydalanuvchi tasdiqlashi kerak."""

    unit: str | None = None
    scale: float | None = None
    up_axis: str | None = None
    source: str = ""
    uncertain: bool = True
    axis_uncertain: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def unit_name(scale: float) -> str | None:
    """Metrdagi masshtab → UNITS nomi (aniq mos kelsa)."""
    for k, v in UNITS.items():
        if abs(v - scale) <= 1e-9 * max(v, scale):
            return k
    return None


def dxf_insunits(path: str | Path, max_lines: int = 20000) -> int | None:
    """DXF HEADER dan $INSUNITS kodi (matnli DXF). Topilmasa None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            prev2 = prev1 = ""
            for i, line in enumerate(fh):
                if i > max_lines:
                    break
                s = line.strip()
                if prev2 == "$INSUNITS" and prev1 == "70":
                    return int(s)
                if s == "ENDSEC" and prev2 == "$INSUNITS":
                    return None
                if s == "ENTITIES":  # header tugadi
                    break
                prev2, prev1 = prev1, s
    except (OSError, ValueError):
        return None
    return None


def detect_units_and_axis(path: str | Path) -> UnitInfo:
    """Fayl birligi va yuqori o'qi (faqat fayldagi ma'lumot yoki format spetsifikatsiyasi bo'yicha)."""
    p = Path(path)
    ext = p.suffix.lower()
    info = UnitInfo()
    if ext in DEFAULT_Y_UP:
        info.up_axis = "Y"
    elif ext in DEFAULT_Z_UP:
        info.up_axis = "Z"
    if ext in GLTF_EXTS:
        return UnitInfo("m", 1.0, "Y", "glTF spetsifikatsiyasi", False, False)
    if ext in MM_EXTS:
        return UnitInfo("mm", 0.001, "Z", f"{ext[1:].upper()} (mm)", False, False)
    if ext == ".dxf":
        info.up_axis, info.axis_uncertain = "Z", False  # AutoCAD WCS — Z yuqoriga
        code = dxf_insunits(p)
        if code in DXF_INSUNITS:
            u = DXF_INSUNITS[code]
            info.unit, info.scale, info.source, info.uncertain = u, UNITS[u], "$INSUNITS", False
        else:
            info.source = "$INSUNITS yo'q" if code is None else f"$INSUNITS={code} (birliksiz)"
            info.note = "DXF da birlik ko'rsatilmagan — birlikni tanlang"
        return info
    if ext == ".fbx":
        meta = fbx_info(p)
        f = meta.get("unit_scale")
        if isinstance(f, (int, float)) and f > 0:
            info.scale = float(f) * 0.01  # FBX: UnitScaleFactor — 1 birlik necha sm
            info.unit = unit_name(info.scale)
            info.source, info.uncertain = "FBX UnitScaleFactor", False
        up = meta.get("up_axis")
        if up in (1, 2):
            info.up_axis, info.axis_uncertain = ("Y" if up == 1 else "Z"), False
            if meta.get("up_sign", 1) < 0:
                info.note = "FBX UpAxisSign manfiy — o'q teskari bo'lishi mumkin"
                info.axis_uncertain = True
        if info.uncertain:
            info.note = info.note or "FBX da birlik (UnitScaleFactor) topilmadi"
        return info
    info.note = f"{ext[1:].upper() or 'fayl'} da birlik ma'lumoti yo'q"
    return info


def to_z_up(v: tuple | list) -> tuple[float, float, float]:
    """Y yuqoriga → Z yuqoriga: (x, y, z) → (x, −z, y)."""
    return (float(v[0]), -float(v[2]), float(v[1]))


# --- FBX (binar / ASCII) metama'lumoti ---------------------------------------------------------------------------

_FBX_MAGIC = b"Kaydara FBX Binary  \x00"


def _fbx_props(data: bytes, pos: int, n: int) -> tuple[list, int]:
    out: list = []
    for _ in range(n):
        t = data[pos : pos + 1]
        pos += 1
        if t == b"Y":
            out.append(struct.unpack_from("<h", data, pos)[0])
            pos += 2
        elif t == b"C":
            out.append(bool(data[pos]))
            pos += 1
        elif t == b"I":
            out.append(struct.unpack_from("<i", data, pos)[0])
            pos += 4
        elif t == b"F":
            out.append(struct.unpack_from("<f", data, pos)[0])
            pos += 4
        elif t == b"D":
            out.append(struct.unpack_from("<d", data, pos)[0])
            pos += 8
        elif t == b"L":
            out.append(struct.unpack_from("<q", data, pos)[0])
            pos += 8
        elif t in (b"S", b"R"):
            ln = struct.unpack_from("<I", data, pos)[0]
            raw = data[pos + 4 : pos + 4 + ln]
            out.append(raw.decode("utf-8", errors="replace") if t == b"S" else raw)
            pos += 4 + ln
        elif t in (b"f", b"d", b"l", b"i", b"b"):
            _cnt, _enc, clen = struct.unpack_from("<III", data, pos)
            pos += 12
            out.append(None)  # massivlar (geometriya) kerak emas
            pos += clen
        else:
            raise ValueError(f"FBX: noma'lum xususiyat turi {t!r}")
    return out, pos


def _fbx_nodes(data: bytes, pos: int, end: int, wide: bool, depth: int = 0):
    """(name, props, children) daraxti; geometriya massivlari o'tkazib yuboriladi."""
    head = "<QQQB" if wide else "<IIIB"
    hsize = struct.calcsize(head)
    nodes = []
    while pos + hsize <= end:
        end_off, nprops, plen, nlen = struct.unpack_from(head, data, pos)
        if end_off == 0:
            break
        name = data[pos + hsize : pos + hsize + nlen].decode("ascii", errors="replace")
        ppos = pos + hsize + nlen
        props = []
        if name in ("GlobalSettings", "Properties70", "P", "Objects", "Model", "Definitions"):
            props, _ = _fbx_props(data, ppos, nprops)
        children = []
        cpos = ppos + plen
        if cpos < end_off and depth < 6 and name in (
            "GlobalSettings", "Properties70", "Objects", "Model",
        ):  # fmt: skip
            children = _fbx_nodes(data, cpos, end_off, wide, depth + 1)
        nodes.append((name, props, children))
        pos = end_off
    return nodes


def _p70(children) -> dict:
    out = {}
    for name, _props, sub in children:
        if name != "Properties70":
            continue
        for pn, pp, _ in sub:
            if pn == "P" and pp and isinstance(pp[0], str):
                out[pp[0]] = pp[4] if len(pp) > 4 else None
    return out


def fbx_info(path: str | Path) -> dict:
    """FBX: {"unit_scale": UnitScaleFactor, "up_axis": 0/1/2, "up_sign": ±1, "models": {nom: {xususiyat: qiymat}}}.
    models — Model tugunlarining foydalanuvchi xususiyatlari (Blender «Custom Properties», masalan sath_guid)."""
    out: dict = {"models": {}}
    try:
        data = Path(path).read_bytes()
    except OSError:
        return out
    if data.startswith(_FBX_MAGIC):
        try:
            version = struct.unpack_from("<I", data, 23)[0]
            nodes = _fbx_nodes(data, 27, len(data), version >= 7500)
        except (struct.error, ValueError, IndexError):
            return out
        for name, _props, children in nodes:
            if name == "GlobalSettings":
                p = _p70(children)
                out["unit_scale"] = p.get("UnitScaleFactor")
                out["up_axis"] = p.get("UpAxis")
                out["up_sign"] = p.get("UpAxisSign", 1)
            elif name == "Objects":
                for cn, cp, cc in children:
                    if cn == "Model" and len(cp) > 1 and isinstance(cp[1], str):
                        mname = cp[1].split("\x00")[0]
                        props = {k: v for k, v in _p70(cc).items() if isinstance(v, (str, int, float))}
                        out["models"][mname] = props
        return out
    # ASCII FBX
    txt = data[:4_000_000].decode("utf-8", errors="replace")
    for key, field_ in (("UnitScaleFactor", "unit_scale"), ("UpAxis", "up_axis"), ("UpAxisSign", "up_sign")):
        m = re.search(rf'P:\s*"{key}"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*([-+0-9.eE]+)', txt)
        if m:
            val = float(m.group(1))
            out[field_] = val if field_ == "unit_scale" else int(val)
    for m in re.finditer(r'Model:\s*\d+\s*,\s*"Model::([^"]+)"', txt):
        seg = txt[m.end() : m.end() + 4000]
        g = re.search(r'P:\s*"(sath_guid|guid)"\s*,\s*"KString"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"([^"]*)"', seg)
        if g:
            out["models"][m.group(1)] = {g.group(1): g.group(2)}
    return out


# --- GUID (CAD-07) -----------------------------------------------------------------------------------------------

IFC_GUID = r"[0-9A-Za-z_$]{22}"
_NAME_GUID = re.compile(rf"^(.*?)\s*\[({IFC_GUID})\]$")
_ONLY_GUID = re.compile(rf"^{IFC_GUID}$")
GUID_KEYS = ("sath_guid", "guid", "GlobalId", "ifc_guid")


def split_guid(name: str) -> tuple[str, str | None]:
    """"Devor [2O2Fr$t4X7Zf8NOew3FLOH]" → ("Devor", "2O2Fr$t4X7Zf8NOew3FLOH"); GUID yo'q — (name, None)."""
    m = _NAME_GUID.match((name or "").strip())
    if not m:
        return name, None
    return (m.group(1).strip() or name), m.group(2)


def is_guid(value) -> bool:
    return isinstance(value, str) and bool(_ONLY_GUID.match(value.strip()))


def guid_from_props(props: dict | None) -> str | None:
    """Foydalanuvchi xususiyatlari (glTF extras, FBX user props, Blender custom props) dan IFC GUID."""
    if not isinstance(props, dict):
        return None
    for k in GUID_KEYS:
        for key in (k, k.lower(), k.upper()):
            v = props.get(key)
            if is_guid(v):
                return v.strip()
    ex = props.get("extras")
    return guid_from_props(ex) if isinstance(ex, dict) and ex is not props else None


def gltf_json(path: str | Path) -> dict | None:
    """glTF/GLB ning JSON qismi (bufferlarsiz)."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return None
    try:
        if data[:4] == b"glTF":
            ln = struct.unpack_from("<I", data, 12)[0]
            return json.loads(data[20 : 20 + ln].decode("utf-8"))
        return json.loads(data.decode("utf-8"))
    except (ValueError, struct.error, UnicodeDecodeError):
        return None


def gltf_node_guids(path: str | Path) -> dict[str, str]:
    """glTF tugun nomi → GUID (tugun yoki uning mesh extras idagi sath_guid/guid)."""
    js = gltf_json(path)
    if not js:
        return {}
    meshes = js.get("meshes") or []
    out = {}
    for n in js.get("nodes") or []:
        g = guid_from_props(n.get("extras"))
        mi = n.get("mesh")
        if g is None and isinstance(mi, int) and 0 <= mi < len(meshes):
            g = guid_from_props(meshes[mi].get("extras"))
        if g and n.get("name"):
            out[n["name"]] = g
    return out


# --- DXF 3D yuzalar (CAD-02, CAD-03) -----------------------------------------------------------------------------

DXF_MAX_DEPTH = 8
DXF_FACE_TYPES = {"3DFACE", "SOLID", "TRACE"}
DXF_3D_TYPES = DXF_FACE_TYPES | {"MESH", "POLYLINE", "POLYFACE", "POLYMESH"}
DXF_ACIS_TYPES = {"3DSOLID", "REGION", "BODY", "SURFACE"}
DXF_2D_TYPES = {
    "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE", "HELIX", "TEXT", "MTEXT",
    "ATTRIB", "HATCH", "MPOLYGON", "DIMENSION", "ARC_DIMENSION", "LEADER", "MULTILEADER", "MLEADER", "MLINE",
}  # fmt: skip


def _xyz(p) -> tuple[float, float, float]:
    t = tuple(p)
    return (float(t[0]), float(t[1]), float(t[2]) if len(t) > 2 else 0.0)


def dxf_face_vertices(e) -> list[tuple[float, float, float]]:
    """3DFACE / SOLID / TRACE uchlari to'g'ri aylanish tartibida (WCS), ketma-ket takrorlarsiz.
    DXF da SOLID/TRACE 0-1-3-2 («Z» shakl), 3DFACE 0-1-2-3 tartibda saqlanadi."""
    t = e.dxftype()
    if hasattr(e, "wcs_vertices"):  # ezdxf: SOLID/TRACE uchun OCS → WCS va 0-1-3-2 tartib, 3DFACE — 0-1-2-3
        raw = list(e.wcs_vertices())
    else:
        order = (0, 1, 3, 2) if t in ("SOLID", "TRACE") else (0, 1, 2, 3)
        raw = [e.dxf.get(f"vtx{i}") for i in order]
    pts: list[tuple[float, float, float]] = []
    for p in raw:
        if p is None:
            continue
        q = _xyz(p)
        if not pts or q != pts[-1]:
            pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def fan(pts: list) -> list[list]:
    """Qavariq ko'pburchak → uchburchaklar (yelpig'ich, 0-k-(k+1))."""
    return [[pts[0], pts[k], pts[k + 1]] for k in range(1, len(pts) - 1)]


def dxf_triangles(e) -> list[list] | None:
    """3D yuza entity → uchburchaklar [[p0, p1, p2], …] (WCS). Yuza turi bo'lmasa None."""
    t = e.dxftype()
    if t in DXF_FACE_TYPES:
        return fan(dxf_face_vertices(e))
    if t == "MESH":
        md = e.get_data()
        vs = [_xyz(v) for v in md.vertices]
        tris: list[list] = []
        for face in md.faces:
            tris += fan([vs[int(i)] for i in face])
        return tris
    if t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh):
        tris = []
        if e.is_poly_face_mesh:
            vs = [_xyz(v.dxf.location) for v in e.vertices if v.is_poly_face_mesh_vertex]
            for f in e.vertices:
                if f.is_face_record:
                    idx = [abs(int(f.dxf.get(f"vtx{k}", 0) or 0)) for k in range(4)]
                    tris += fan([vs[i - 1] for i in idx if 0 < i <= len(vs)])
        else:
            m = e.get_mesh_vertex_cache() if hasattr(e, "get_mesh_vertex_cache") else None
            if m is not None:
                mc, nc = e.dxf.m_count, e.dxf.n_count
                for i in range(mc - 1):
                    for j in range(nc - 1):
                        tris += fan([_xyz(m[i, j]), _xyz(m[i + 1, j]), _xyz(m[i + 1, j + 1]), _xyz(m[i, j + 1])])
        return tris
    return None


def iter_dxf_entities(entities, max_depth: int = DXF_MAX_DEPTH, stats: dict | None = None):
    """Entity lar bo'ylab yuradi; INSERT (blok) larni `virtual_entities()` bilan rekursiv yoyadi — natija WCS da,
    blok transformatsiyasi (joy, masshtab, burilish, ichma-ich bloklar) qo'llangan. «0» qatlamdagi blok elementlari
    INSERT qatlamiga, BYBLOCK rang INSERT rangiga o'tadi (AutoCAD qoidasi). Chuqurlik cheklangan, o'z-o'zini
    chaqiruvchi blok (sikl) o'tkazib yuboriladi. stats: {"insert": n, "insert_skipped": n}."""
    st = stats if stats is not None else {}

    def walk(ents, depth: int, chain: tuple[str, ...], layer: str | None, color: int | None):
        for e in ents:
            if layer is not None:
                try:
                    if e.dxf.get("layer", "0") == "0":
                        e.dxf.layer = layer
                    if color is not None and int(e.dxf.get("color", 256) or 256) == 0:
                        e.dxf.color = color
                except Exception:  # noqa: BLE001 — atribut qo'llanmaydigan entity
                    pass
            if e.dxftype() != "INSERT":
                yield e
                continue
            name = str(e.dxf.get("name", ""))
            if depth >= max_depth or name in chain:
                st["insert_skipped"] = st.get("insert_skipped", 0) + 1
                continue
            try:
                sub = list(e.virtual_entities())
            except Exception:  # noqa: BLE001 — buzuq blok/transformatsiya importni to'xtatmasin
                st["insert_skipped"] = st.get("insert_skipped", 0) + 1
                continue
            st["insert"] = st.get("insert", 0) + 1
            ins_color = int(e.dxf.get("color", 256) or 256)
            yield from walk(sub, depth + 1, (*chain, name), str(e.dxf.get("layer", "0")), ins_color)

    yield from walk(entities, 0, (), None, None)
