"""DXF/DWG ni AutoCAD kabi **tahrirlanadigan** obyektlar sifatida ochish (FreeCAD C++ importeri o'rniga).

Har DXF elementi — alohida FreeCAD obyekti, o'z rangi va qatlami bilan:
  * LINE → Draft Line, LWPOLYLINE/POLYLINE (bulge siz) → Draft Wire, ARC/CIRCLE → Draft Circle,
    bulge li polilinya / ELLIPSE / SPLINE → Part egri (yoylar, bezier, B-spline)
  * TEXT / MTEXT / ATTRIB → Draft Text (matn, balandlik, burilish — tahrirlanadi)
  * DIMENSION (chiziqli/tekislangan) → Draft Dimension, ko'rsatilgan qiymat AutoCAD dagidek (Override)
    — nuqtalari siljitilsa qayta hisoblanmaydi (Override ni bo'shatib qayta hisoblatish mumkin);
    burchak/radius/diametr o'lchamlar → chiziqlar + matn (portlatilgan)
  * LEADER / MULTILEADER → chiziqlar + matn;  HATCH → shtrix chiziqlari (bitta obyekt), SOLID → yuza
  * INSERT (blok) → tarkibi (rekursiv «EXPLODE»), obyekt nomida blok nomi; atributlar → matn
  * Qatlamlar → Draft Layer (rang, chiziq turi: DASHED/CENTER/HIDDEN…); elementlar o'z rangida
  * MIRROR dan qolgan teskari OCS (extrusion 0,0,-1) → to'g'rilanadi;  rasm/OLE/VIEWPORT/POINT — kirmaydi

ezdxf (paket ichida, Mod/Ges/vendor) bilan o'qiladi; FreeCAD ning importDXF ishlatilmaydi.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import FreeCAD

V = FreeCAD.Vector

# DXF chiziq turi nomi → FreeCAD DrawStyle
_DRAW_STYLES = (
    ("DASHDOT", "Dashdot"),
    ("CENTER", "Dashdot"),
    ("PHANTOM", "Dashdot"),
    ("DASHED", "Dashed"),
    ("HIDDEN", "Dashed"),
    ("DOT", "Dotted"),
)
EXPLODE_TYPES = {"INSERT", "LEADER", "MULTILEADER", "MLEADER", "ARC_DIMENSION"}
DROP = {
    "OLE2FRAME",
    "IMAGE",
    "VIEWPORT",
    "WIPEOUT",
    "POINT",
    "ACAD_TABLE",
    "XLINE",
    "RAY",
    "ATTDEF",
}
MAX_DEPTH = 8


def _gui() -> bool:
    return FreeCAD.GuiUp


def _draw_style(linetype: str | None) -> str:
    lt = (linetype or "").upper()
    for key, style in _DRAW_STYLES:
        if key in lt:
            return style
    return "Solid"


def _aci_rgb(aci: int) -> tuple[float, float, float]:
    from ezdxf import colors as dxfcolors

    if aci == 7:
        return (0.55, 0.55, 0.55)  # oq/qora — qora fonda ham, oq fonda ham ko'rinsin
    try:
        r, g, b = dxfcolors.aci2rgb(int(aci))
        return (r / 255, g / 255, b / 255)
    except Exception:  # noqa: BLE001
        return (0.55, 0.55, 0.55)


class _Ctx:
    """Import holati: qatlamlar, ranglar, statistika."""

    def __init__(self, fc_doc, dxf_doc):
        self.doc = fc_doc
        self.dxf = dxf_doc
        self.layers: dict[str, object] = {}
        self.layer_aci: dict[str, int] = {}
        self.layer_lt: dict[str, str] = {}
        self.block_of: dict[str, str] = {}  # entity handle → blok nomi (portlatilgan)
        self.insert_color: dict[str, int] = {}  # entity handle → INSERT rangi (BYBLOCK uchun)
        self.stats: dict[str, int] = {}
        self.objects: list = []
        for lay in dxf_doc.layers:
            self.layer_aci[lay.dxf.name] = lay.color if lay.color > 0 else 7
            self.layer_lt[lay.dxf.name] = lay.dxf.get("linetype", "Continuous")

    def count(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    def layer(self, name: str):
        if name in self.layers:
            return self.layers[name]
        import Draft

        rgb = _aci_rgb(self.layer_aci.get(name, 7))
        lay = Draft.make_layer(
            name,
            line_color=rgb,
            shape_color=rgb,
            line_width=1.0,
            draw_style=_draw_style(self.layer_lt.get(name)),
        )
        if getattr(lay, "ViewObject", None) is not None:
            vo = lay.ViewObject
            for prop in ("OverrideLineColorChildren", "OverrideShapeAppearanceChildren"):
                if hasattr(vo, prop):
                    setattr(vo, prop, False)  # elementlar o'z rangida qolsin
        self.layers[name] = lay
        return lay

    def color_of(self, e) -> tuple[float, float, float]:
        rgb = e.rgb if hasattr(e, "rgb") else None
        if rgb:
            return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        aci = int(e.dxf.get("color", 256) or 256)
        if aci == 0:  # BYBLOCK
            aci = self.insert_color.get(e.dxf.handle, 256)
        if aci in (0, 256):
            aci = self.layer_aci.get(e.dxf.layer, 7)
        return _aci_rgb(aci)

    def style(self, obj, e, kind: str) -> None:
        """Rang, chiziq turi, qatlam, nom."""
        block = self.block_of.get(e.dxf.handle)
        obj.Label = f"{block}: {kind}" if block else kind
        layer_name = e.dxf.layer or "0"
        try:
            lay = self.layer(layer_name)
            lay.Proxy.addObject(lay, obj)
        except Exception:  # noqa: BLE001
            pass
        self.objects.append(obj)
        if not _gui() or getattr(obj, "ViewObject", None) is None:
            return
        vo = obj.ViewObject
        rgb = self.color_of(e)
        lt = e.dxf.get("linetype", "BYLAYER") or "BYLAYER"
        if lt.upper() == "BYLAYER":
            lt = self.layer_lt.get(layer_name, "Continuous")
        for prop, val in (
            ("LineColor", rgb),
            ("PointColor", rgb),
            ("ShapeColor", rgb),
            ("TextColor", rgb),
            ("DrawStyle", _draw_style(lt)),
            ("LineWidth", 1.0),
        ):
            try:
                if hasattr(vo, prop):
                    setattr(vo, prop, val)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(vo, "ShapeAppearance"):
            try:
                mat = vo.ShapeAppearance[0]
                mat.DiffuseColor = rgb
                vo.ShapeAppearance = (mat,)
            except Exception:  # noqa: BLE001
                pass


# ---------- geometriya ----------


def _vec(p) -> FreeCAD.Vector:
    return V(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)


def _placement(pt, rotation_deg: float = 0.0) -> FreeCAD.Placement:
    return FreeCAD.Placement(_vec(pt), FreeCAD.Rotation(V(0, 0, 1), rotation_deg))


def _path_to_shape(e):
    """ezdxf Path (bulge li polilinya, ellips, spline, helix) → Part.Wire (chiziq + bezier egrilari)."""
    import Part
    from ezdxf import path as dxfpath
    from ezdxf.path import Command

    pth = dxfpath.make_path(e)
    edges = []
    start = _vec(pth.start)
    for cmd in pth.commands():
        if cmd.type == Command.LINE_TO:
            end = _vec(cmd.end)
            if (end - start).Length > 1e-9:
                edges.append(Part.LineSegment(start, end).toShape())
            start = end
        elif cmd.type == Command.CURVE3_TO:
            end = _vec(cmd.end)
            bz = Part.BezierCurve()
            bz.setPoles([start, _vec(cmd.ctrl), end])
            edges.append(bz.toShape())
            start = end
        elif cmd.type == Command.CURVE4_TO:
            end = _vec(cmd.end)
            bz = Part.BezierCurve()
            bz.setPoles([start, _vec(cmd.ctrl1), _vec(cmd.ctrl2), end])
            edges.append(bz.toShape())
            start = end
        elif cmd.type == Command.MOVE_TO:
            start = _vec(cmd.end)
    if not edges:
        return None
    try:
        return Part.Wire(Part.__sortEdges__(edges))
    except Exception:  # noqa: BLE001
        return Part.Compound(edges)


def _add_line(ctx: _Ctx, e):
    import Draft

    a, b = _vec(e.dxf.start), _vec(e.dxf.end)
    if (b - a).Length < 1e-9:
        return
    ctx.style(Draft.make_line(a, b), e, "Chiziq")


def _add_polyline(ctx: _Ctx, e):
    import Draft

    t = e.dxftype()
    if t == "POLYLINE" and not e.is_2d_polyline and not e.is_3d_polyline:
        return _add_part(ctx, e, "Mesh")  # polyface/polymesh — Part orqali
    has_bulge = t == "LWPOLYLINE" and e.has_arc
    if t == "POLYLINE":
        has_bulge = any(abs(v.dxf.get("bulge", 0.0)) > 1e-9 for v in e.vertices)
    if has_bulge:
        return _add_part(ctx, e, "Polilinya")
    if t == "LWPOLYLINE":
        z = float(e.dxf.elevation or 0.0)
        pts = [V(float(x), float(y), z) for x, y, *_ in e.get_points()]
        closed = bool(e.closed)
    else:
        pts = [_vec(v.dxf.location) for v in e.vertices]
        closed = bool(e.is_closed)
    # takror nuqtalar
    clean = [pts[0]] if pts else []
    for q in pts[1:]:
        if (q - clean[-1]).Length > 1e-9:
            clean.append(q)
    if closed and len(clean) > 2 and (clean[0] - clean[-1]).Length < 1e-9:
        clean.pop()
    if len(clean) < 2:
        return
    ctx.style(Draft.make_wire(clean, closed=closed and len(clean) > 2, face=False), e, "Polilinya")


def _add_circle(ctx: _Ctx, e):
    import Draft

    c = e.dxf.center
    r = float(e.dxf.radius)
    if r <= 0:
        return
    if e.dxftype() == "ARC":
        obj = Draft.make_circle(
            r,
            placement=_placement(c),
            face=False,
            startangle=float(e.dxf.start_angle),
            endangle=float(e.dxf.end_angle),
        )
        ctx.style(obj, e, "Yoy")
    else:
        ctx.style(Draft.make_circle(r, placement=_placement(c), face=False), e, "Aylana")


def _add_part(ctx: _Ctx, e, kind: str):
    shape = _path_to_shape(e)
    if shape is None:
        return
    obj = ctx.doc.addObject("Part::Feature", "Egri")
    obj.Shape = shape
    ctx.style(obj, e, kind)


def _add_text(ctx: _Ctx, e):
    import Draft

    t = e.dxftype()
    if t == "MTEXT":
        lines = [ln for ln in e.plain_text(split=True)]
        height = float(e.dxf.char_height or 2.5)
        ins = e.dxf.insert
        rot = 0.0
        try:
            rot = float(e.get_rotation())
        except Exception:  # noqa: BLE001
            rot = float(e.dxf.get("rotation", 0.0) or 0.0)
        # MTEXT nuqtasi — birinchi satrning yuqori chap burchagi; Draft Text — birinchi satr bazasi
        att = int(e.dxf.get("attachment_point", 1) or 1)
        n = max(len(lines), 1)
        spacing = float(e.dxf.get("line_spacing_factor", 1.0) or 1.0) * 1.67
        top_rows = {1: 0, 2: 0, 3: 0, 4: n / 2, 5: n / 2, 6: n / 2, 7: n, 8: n, 9: n}[att]
        # matn blokining yuqori chetigacha masofa → bazaga: birinchi satr = yuqoridan bir balandlik pastda
        dy = -height + top_rows * height * spacing
        a = math.radians(rot)
        base = V(float(ins.x) - dy * math.sin(a), float(ins.y) + dy * math.cos(a), float(ins.z))
        just = {1: "Left", 4: "Left", 7: "Left", 2: "Center", 5: "Center", 8: "Center"}.get(
            att, "Right"
        )
        if just != "Left":
            # markaz/o'ng tekislangan MTEXT: Draft Text Justification bilan
            pass
        obj = Draft.make_text(
            lines, placement=_placement(base, rot), height=height, line_spacing=spacing / 1.67
        )
    else:  # TEXT / ATTRIB
        text = e.dxf.text or ""
        if not text.strip():
            return
        height = float(e.dxf.height or 2.5)
        rot = float(e.dxf.get("rotation", 0.0) or 0.0)
        # tekislangan matnlar (align_point) bo'lsa ezdxf insert ni hisoblab beradi
        ins = e.dxf.insert
        try:  # tekislangan (markaz/o'ng/fit) matnlarda joy — align_point
            if (
                int(e.dxf.get("halign", 0) or 0) or int(e.dxf.get("valign", 0) or 0)
            ) and e.dxf.hasattr("align_point"):
                ap = e.dxf.align_point
                if abs(ap.x) + abs(ap.y) > 1e-9:
                    ins = ap
        except Exception:  # noqa: BLE001
            pass
        obj = Draft.make_text([text], placement=_placement(ins, rot), height=height)
        halign = int(e.dxf.get("halign", 0) or 0)
        just = {0: "Left", 1: "Center", 2: "Right", 4: "Center"}.get(halign, "Left")
    if _gui() and getattr(obj, "ViewObject", None) is not None:
        try:
            obj.ViewObject.Justification = just
        except Exception:  # noqa: BLE001
            pass
    ctx.style(obj, e, "Matn")


def _dim_text(dim) -> str:
    """AutoCAD chizgan (blokdagi) matn — qiymat, prefiks/suffiks, o'zgartirilgan matn bilan."""
    try:
        for v in dim.virtual_entities():
            if v.dxftype() == "MTEXT":
                return " ".join(v.plain_text(split=True))
            if v.dxftype() == "TEXT":
                return v.dxf.text
    except Exception:  # noqa: BLE001
        pass
    txt = dim.dxf.get("text", "") or ""
    if txt and txt != "<>":
        return txt
    try:
        m = dim.get_measurement()
        return f"{m:.4g}"
    except Exception:  # noqa: BLE001
        return ""


def _add_dimension(ctx: _Ctx, dim, msp) -> None:
    import Draft

    kind = int(dim.dxf.dimtype) & 0x0F
    if kind not in (0, 1):
        return _explode_into(ctx, dim, msp, "O'lcham")
    p1, p2 = _vec(dim.dxf.defpoint2), _vec(dim.dxf.defpoint3)
    pl = _vec(dim.dxf.defpoint)  # o'lcham chizig'i nuqtasi
    if (p2 - p1).Length < 1e-9:
        return
    obj = Draft.make_dimension(p1, p2, pl)
    if obj is None:
        return
    if kind == 0:  # burilgan (rotated): yo'nalish burchak bilan
        a = math.radians(float(dim.dxf.get("angle", 0.0) or 0.0))
        obj.Direction = V(math.cos(a), math.sin(a), 0)
    ov = dim.override() if hasattr(dim, "override") else None

    def sty(name, default):
        try:
            return float(ov.get(name, default)) if ov is not None else default
        except Exception:  # noqa: BLE001
            return default

    scale = sty("dimscale", 1.0) or 1.0  # 0 — «chizma masshtabi» → 1
    text = _dim_text(dim)
    if _gui() and getattr(obj, "ViewObject", None) is not None:
        vo = obj.ViewObject
        blk = str((ov.get("dimblk", "") if ov is not None else "") or "").upper()
        tick = "OBLIQUE" in blk or "ARCHTICK" in blk or sty("dimtsz", 0.0) > 0
        arrow = "Tick" if tick else "Arrow"
        # Draft belgisi (Tick/Arrow) DXF dagidan kattaroq chiqadi — yarmi yetarli
        size = (
            (sty("dimtsz", 0.0) if tick and sty("dimtsz", 0.0) > 0 else sty("dimasz", 0.18))
            * scale
            * 0.5
        )
        for name, val in (
            ("Override", text),
            ("FontSize", sty("dimtxt", 0.18) * scale),
            ("ArrowTypeStart", arrow),
            ("ArrowTypeEnd", arrow),
            ("ArrowSizeStart", size),
            ("ArrowSizeEnd", size),
            ("ArrowSize", size),
            ("ExtOvershoot", sty("dimexe", 0.18) * scale),
            ("DimOvershoot", size if tick else 0.0),
            ("ExtLines", 0.0),
            ("ShowUnit", False),
            ("Decimals", int(sty("dimdec", 2))),
            ("DisplayMode", "World"),
            ("ScaleMultiplier", 1.0),
        ):
            try:
                if hasattr(vo, name):
                    setattr(vo, name, val)
            except Exception:  # noqa: BLE001 — xususiyat bo'lmasa o'tkazib yuboriladi
                pass
    ctx.style(obj, dim, "O'lcham")
    ctx.count("DIMENSION")
    try:
        msp.delete_entity(dim)  # 2-bosqichda qayta portlatilmasin (takror chiqmasin)
    except Exception:  # noqa: BLE001
        pass


def _add_hatch(ctx: _Ctx, h):
    import Part
    from ezdxf import path as dxfpath
    from ezdxf.math import Vec2
    from ezdxf.render import hatching

    edges = []
    try:
        paths = list(dxfpath.from_hatch(h))
        for p in paths:
            pts = [_vec(v) for v in p.flattening(0.5)]
            for a, b in zip(pts, pts[1:], strict=False):
                if (b - a).Length > 1e-9:
                    edges.append(Part.LineSegment(a, b).toShape())
        if h.dxf.solid_fill:
            box = dxfpath.bbox(paths)
            step = max(box.size.magnitude / 60, 1e-6)
            base = hatching.HatchBaseLine(Vec2(0, 0), Vec2(1, 0), Vec2(0, step))
            polys = [[Vec2(v) for v in p.flattening(0.5)] for p in paths]
            for ln in hatching.hatch_polygons(base, polys):
                edges.append(Part.LineSegment(_vec(ln.start), _vec(ln.end)).toShape())
        else:
            for s, t in hatching.hatch_entity(h):
                edges.append(Part.LineSegment(_vec(s), _vec(t)).toShape())
    except Exception:  # noqa: BLE001
        pass
    if not edges:
        return
    obj = ctx.doc.addObject("Part::Feature", "Shtrix")
    obj.Shape = Part.Compound(edges)
    ctx.style(obj, h, "Shtrix")


def _add_solid(ctx: _Ctx, e):
    import Part

    pts = [_vec(e.dxf.vtx0), _vec(e.dxf.vtx1), _vec(e.dxf.vtx3), _vec(e.dxf.vtx2)]
    uniq = [pts[0]]
    for q in pts[1:]:
        if (q - uniq[-1]).Length > 1e-9:
            uniq.append(q)
    if len(uniq) < 3:
        return
    try:
        face = Part.Face(Part.makePolygon(uniq + [uniq[0]]))
    except Exception:  # noqa: BLE001
        return
    obj = ctx.doc.addObject("Part::Feature", "Yuza")
    obj.Shape = face
    ctx.style(obj, e, "Yuza")


def _explode_into(ctx: _Ctx, e, msp, block_name: str | None) -> list:
    """INSERT / LEADER / murakkab o'lchamni model fazosiga portlatish; yangi elementlar ro'yxati."""
    color = int(e.dxf.get("color", 256) or 256)
    layer = e.dxf.layer
    try:
        new = list(e.explode())
    except Exception:  # noqa: BLE001
        try:
            msp.delete_entity(e)
        except Exception:  # noqa: BLE001
            pass
        ctx.count("skip_" + e.dxftype())
        return []
    for n in new:
        h = n.dxf.handle
        if block_name:
            ctx.block_of[h] = block_name
        if int(n.dxf.get("color", 256) or 256) == 0:
            ctx.insert_color[h] = color if color != 0 else ctx.insert_color.get(e.dxf.handle, 256)
        if n.dxf.layer == "0" and layer and layer != "0":
            n.dxf.layer = layer  # blok ichidagi «0» qatlam → INSERT qatlami (AutoCAD qoidasi)
    ctx.count(e.dxftype())
    return new


def _upright_all(msp) -> None:
    from ezdxf.upright import upright

    for e in list(msp):
        if not e.dxf.is_supported("extrusion"):
            continue
        ex = e.dxf.get("extrusion", None)
        if ex is not None and ex.z < 0:
            try:
                upright(e)
            except Exception:  # noqa: BLE001
                pass


def build(fc_doc, dxf_doc) -> dict:
    """ezdxf hujjati → FreeCAD obyektlari. Statistika qaytaradi."""
    ctx = _Ctx(fc_doc, dxf_doc)
    msp = dxf_doc.modelspace()
    # 1) tashlanadiganlar, bloklar/chiqish yozuvlari (rekursiv)
    for e in [e for e in msp if e.dxftype() in DROP]:
        msp.delete_entity(e)
        ctx.count("drop")
    for _ in range(MAX_DEPTH):
        todo = [e for e in msp if e.dxftype() in EXPLODE_TYPES]
        if not todo:
            break
        for e in todo:
            name = e.dxf.name if e.dxftype() == "INSERT" else ctx.block_of.get(e.dxf.handle)
            _explode_into(ctx, e, msp, name)
    for e in [e for e in msp if e.dxftype() in DROP]:
        msp.delete_entity(e)
    _upright_all(msp)
    # 2) elementlar
    for e in list(msp):
        t = e.dxftype()
        try:
            if t == "LINE":
                _add_line(ctx, e)
            elif t in ("LWPOLYLINE", "POLYLINE"):
                _add_polyline(ctx, e)
            elif t in ("ARC", "CIRCLE"):
                _add_circle(ctx, e)
            elif t in ("ELLIPSE", "SPLINE", "HELIX"):
                _add_part(ctx, e, "Ellips" if t == "ELLIPSE" else "Spline")
            elif t in ("TEXT", "MTEXT", "ATTRIB"):
                _add_text(ctx, e)
            elif t == "DIMENSION":
                _add_dimension(ctx, e, msp)
                continue
            elif t in ("HATCH", "MPOLYGON"):
                _add_hatch(ctx, e)
            elif t in ("SOLID", "TRACE"):
                _add_solid(ctx, e)
            elif t == "3DFACE":
                _add_solid(ctx, e)
            else:
                ctx.count("skip_" + t)
                continue
            ctx.count(t)
        except Exception as ex:  # noqa: BLE001 — bitta element chizmani to'xtatmasin
            ctx.count("err_" + t)
            FreeCAD.Console.PrintLog(f"Sath DXF: {t} o'tkazib yuborildi: {ex}\n")
    # portlatilgan o'lchamlar (burchak/radius) → ularning elementlari ham 2-bosqichda qo'shiladi:
    for e in list(msp):
        if e.dxftype() == "DIMENSION":
            for n in _explode_into(ctx, e, msp, "O'lcham"):
                try:
                    t = n.dxftype()
                    if t == "LINE":
                        _add_line(ctx, n)
                    elif t in ("LWPOLYLINE", "POLYLINE"):
                        _add_polyline(ctx, n)
                    elif t in ("ARC", "CIRCLE"):
                        _add_circle(ctx, n)
                    elif t in ("TEXT", "MTEXT"):
                        _add_text(ctx, n)
                    elif t in ("SOLID", "TRACE"):
                        _add_solid(ctx, n)
                except Exception:  # noqa: BLE001
                    ctx.count("err_dim")
    ctx.stats["obyektlar"] = len(ctx.objects)
    return ctx.stats


def _flatten_z(doc, stats: dict) -> None:
    """2D chizma (deyarli hamma element Z=0) — adashib Z balandlikda qolgan matn/o'lchamlar varaqqa tushiriladi,
    aks holda «Fit» chizmani nuqtaga aylantiradi."""
    zs = []
    for o in doc.Objects:
        t = getattr(getattr(o, "Proxy", None), "Type", "")
        if t == "Text":
            zs.append(abs(o.Placement.Base.z))
        elif t == "LinearDimension":
            zs.append(max(abs(o.Start.z), abs(o.End.z), abs(o.Dimline.z)))
        elif hasattr(o, "Shape") and not o.Shape.isNull() and o.Shape.BoundBox.isValid():
            zs.append(max(abs(o.Shape.BoundBox.ZMin), abs(o.Shape.BoundBox.ZMax)))
    if not zs or sum(1 for z in zs if z < 1e-6) < 0.9 * len(zs):
        return  # 3D chizma — tegilmaydi
    n = 0
    for o in doc.Objects:
        t = getattr(getattr(o, "Proxy", None), "Type", "")
        try:
            if t == "Text" and abs(o.Placement.Base.z) > 1e-6:
                pl = o.Placement
                pl.Base = V(pl.Base.x, pl.Base.y, 0)
                o.Placement = pl
                n += 1
            elif (
                t == "LinearDimension"
                and max(abs(o.Start.z), abs(o.End.z), abs(o.Dimline.z)) > 1e-6
            ):
                o.Start, o.End, o.Dimline = (V(q.x, q.y, 0) for q in (o.Start, o.End, o.Dimline))
                n += 1
        except Exception:  # noqa: BLE001
            pass
    if n:
        stats["z_tekislandi"] = n


def import_file(filename: str, doc=None):
    """DXF faylni tahrirlanadigan obyektlar sifatida ochish. doc=None → yangi hujjat."""
    from ges_workbench import dxf_prepare

    if not dxf_prepare.ensure_ezdxf():
        raise RuntimeError("ezdxf topilmadi (Mod/Ges/vendor)")
    t0 = time.time()
    dxf_doc = dxf_prepare._read(Path(filename))
    if doc is None:
        doc = FreeCAD.newDocument(Path(filename).stem)
    stats = build(doc, dxf_doc)
    _flatten_z(doc, stats)
    doc.recompute()
    stats["sekund"] = round(time.time() - t0, 1)
    FreeCAD.Console.PrintMessage(f"Sath: DXF tahrirlanadigan import — {stats}\n")
    if _gui():
        try:
            import FreeCADGui

            FreeCADGui.SendMsgToActiveView("ViewFit")
            FreeCADGui.activeDocument().activeView().viewTop()
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001
            pass
    return doc, stats
