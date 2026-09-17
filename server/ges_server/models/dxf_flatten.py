"""DXF tekislash — desktop/GesWorkbench/ges_workbench/dxf_prepare.py ning nusxasi (server Docker obrazida desktop papkasi yo'q).
O'zgartirganda ikkalasini ham yangilang (sync_fork.py farqni tekshiradi). Mazmuni: dxf_prepare hujjatiga qarang."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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
EXPLODE = {"INSERT", "DIMENSION", "ARC_DIMENSION", "LEADER", "MULTILEADER", "MLEADER"}
TEXT_KINDS = {"TEXT", "ATTRIB"}
MAX_DEPTH = 8


def ensure_ezdxf() -> bool:
    """ezdxf ni topish: o'rnatilgan yoki Mod/Ges/vendor (paket bilan keladi)."""
    try:
        import ezdxf  # noqa: F401

        return True
    except ImportError:
        pass
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.append(str(vendor))
    try:
        import ezdxf  # noqa: F401

        return True
    except ImportError:
        return False


def _fix_handles(path: Path) -> Path:
    """dwg2dxf (LibreDWG) ba'zi obyektlarga «0» handle yozadi — ezdxf rad etadi; yangi handle bilan nusxa."""
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


def _read(path: Path):
    import ezdxf
    from ezdxf import recover

    try:
        return ezdxf.readfile(str(path))
    except Exception:  # noqa: BLE001 — konverter chiqargan DXF ko'pincha noto'liq
        pass
    try:
        doc, _aud = recover.readfile(str(path))
        return doc
    except Exception:  # noqa: BLE001
        pass
    fixed = _fix_handles(path)
    try:
        return ezdxf.readfile(str(fixed))
    except Exception:  # noqa: BLE001
        doc, _aud = recover.readfile(str(fixed))
        return doc


def _count(log: dict, key: str) -> None:
    log[key] = log.get(key, 0) + 1


def _delete(msp, e) -> None:
    try:
        msp.delete_entity(e)
    except Exception:  # noqa: BLE001
        pass


def _explode_all(msp, log: dict) -> None:
    """INSERT/DIMENSION/LEADER/MULTILEADER larni rekursiv portlatish (blok ichida blok bo'lishi mumkin)."""
    for _ in range(MAX_DEPTH):
        todo = [e for e in msp if e.dxftype() in EXPLODE]
        if not todo:
            return
        for e in todo:
            t = e.dxftype()
            try:
                e.explode()  # INSERT uchun ATTRIB lar TEXT bo'lib chiqadi
                _count(log, t)
            except Exception:  # noqa: BLE001 — portlamasa tashlab yuboramiz (FreeCAD ham o'qimasdi)
                _delete(msp, e)
                _count(log, "skip_" + t)


def _mtext_to_text(msp, log: dict) -> None:
    from ezdxf.addons import MTextExplode

    mtexts = [e for e in msp if e.dxftype() == "MTEXT"]
    if not mtexts:
        return
    with MTextExplode(msp) as xpl:
        for m in mtexts:
            try:
                xpl.explode(m, destroy=True)
                _count(log, "MTEXT")
            except Exception:  # noqa: BLE001 — bo'lmasa oddiy satrlar
                try:
                    lines = m.plain_text(split=True)
                    h = m.dxf.char_height or 2.5
                    ins = m.dxf.insert
                    for i, line in enumerate(lines):
                        if line.strip():
                            msp.add_text(
                                line,
                                height=h,
                                dxfattribs={
                                    "layer": m.dxf.layer,
                                    "color": m.dxf.color,
                                    "insert": (ins.x, ins.y - i * h * 1.6, ins.z),
                                },
                            )
                    _delete(msp, m)
                    _count(log, "MTEXT_plain")
                except Exception:  # noqa: BLE001
                    _delete(msp, m)
                    _count(log, "skip_MTEXT")


def _text_to_paths(msp, log: dict) -> None:
    from ezdxf.addons import text2path

    for e in [e for e in msp if e.dxftype() in TEXT_KINDS]:
        try:
            if not (e.dxf.text or "").strip():
                _delete(msp, e)
                continue
            text2path.explode(e, kind=text2path.Kind.LWPOLYLINES, target=msp)
            _count(log, "TEXT")
        except Exception:  # noqa: BLE001 — shrift topilmasa matn tushib qoladi, chizma buzilmaydi
            _delete(msp, e)
            _count(log, "skip_TEXT")


def _hatch_to_lines(msp, log: dict) -> None:
    from ezdxf import path as dxfpath
    from ezdxf.math import Vec2
    from ezdxf.render import hatching

    for h in [e for e in msp if e.dxftype() in ("HATCH", "MPOLYGON")]:
        attrs = {"layer": h.dxf.layer, "color": h.dxf.color}
        try:
            paths = list(dxfpath.from_hatch(h))
            for p in paths:  # chegara
                pts = [(v.x, v.y) for v in p.flattening(0.5)]
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
            if h.dxf.solid_fill:
                # to'ldirilgan → zich gorizontal shtrix (chegara o'lchamiga qarab ~60 chiziq)
                box = dxfpath.bbox(paths)
                step = max(box.size.magnitude / 60, 1e-6)
                base = hatching.HatchBaseLine(Vec2(0, 0), Vec2(1, 0), Vec2(0, step))
                polys = [[Vec2(v) for v in p.flattening(0.5)] for p in paths]
                for line in hatching.hatch_polygons(base, polys):
                    msp.add_line(line.start, line.end, dxfattribs=attrs)
            else:
                for s, t in hatching.hatch_entity(h):
                    msp.add_line(s, t, dxfattribs=attrs)
            _delete(msp, h)
            _count(log, "HATCH")
        except Exception:  # noqa: BLE001 — chegaragina qoladi
            _delete(msp, h)
            _count(log, "skip_HATCH")


def _solids(msp, log: dict) -> None:
    for e in [e for e in msp if e.dxftype() in ("SOLID", "TRACE")]:
        try:
            pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx3, e.dxf.vtx2]  # SOLID tartibi 0-1-3-2
            msp.add_lwpolyline(
                [(p.x, p.y) for p in pts],
                close=True,
                dxfattribs={"layer": e.dxf.layer, "color": e.dxf.color},
            )
            _delete(msp, e)
            _count(log, "SOLID")
        except Exception:  # noqa: BLE001
            pass


def _upright(msp, log: dict) -> None:
    """Teskari OCS (extrusion 0,0,-1 — AutoCAD MIRROR dan qolgan) yoy/aylana/polilinyalarni oddiy holatga
    keltiradi: FreeCAD importeri ularni X bo'yicha noto'g'ri (aksincha) joylashtiradi."""
    from ezdxf.upright import upright

    for e in list(msp):
        if not e.dxf.is_supported("extrusion"):
            continue
        ex = e.dxf.get("extrusion", None)
        if ex is None or ex.z >= 0:
            continue
        try:
            upright(e)
            _count(log, "upright")
        except Exception:  # noqa: BLE001
            _count(log, "skip_upright")


def _drop(msp, log: dict) -> None:
    for e in [e for e in msp if e.dxftype() in DROP]:
        _delete(msp, e)
        _count(log, "drop_" + e.dxftype())


def flatten(doc) -> dict:
    """Ochilgan ezdxf hujjatining model fazosini joyida tekislaydi (saqlamaydi). Server (web import) ham shu
    funksiyani ishlatadi — natijada 2D chizma webda ham AutoCAD dagidek chiqadi."""
    log: dict = {}
    msp = doc.modelspace()
    _drop(msp, log)
    _explode_all(msp, log)
    _drop(msp, log)  # blok ichidan chiqqanlar
    _mtext_to_text(msp, log)
    _text_to_paths(msp, log)
    _hatch_to_lines(msp, log)
    _solids(msp, log)
    _upright(msp, log)
    log["entities"] = len(msp)
    return log


def prepare(path: str | os.PathLike, out_dir: str | None = None) -> tuple[str, dict]:
    """DXF → tekislangan vaqtinchalik DXF. Qaytaradi (yo'l, statistika). ezdxf bo'lmasa asl yo'l."""
    src = Path(path)
    if not ensure_ezdxf():
        return str(src), {"ezdxf": "yo'q"}
    doc = _read(src)
    log = flatten(doc)
    out = Path(out_dir or tempfile.mkdtemp(prefix="ges-dxf-")) / src.name
    _save_clean(doc, doc.modelspace(), out)
    return str(out), log


def _save_clean(doc, msp, out: Path) -> None:
    """Konverter (dwg2dxf) chiqargan hujjatni ezdxf qayta saqlay olmaydi (jadvallar noto'liq) — shuning uchun
    toza yangi hujjat: qatlamlar (rang, chiziq turi) + tekislangan elementlar nusxasi."""
    import ezdxf

    new = ezdxf.new("R2010", setup=True)  # setup → standart chiziq turlari (DASHED, CENTER …)
    new.header["$INSUNITS"] = doc.header.get("$INSUNITS", 0)
    for lay in doc.layers:
        name = lay.dxf.name
        if name in new.layers:
            continue
        attrs = {"color": lay.color if lay.color > 0 else 7}
        lt = lay.dxf.get("linetype", "Continuous")
        if lt in new.linetypes:
            attrs["linetype"] = lt
        try:
            new.layers.add(name, **attrs)
        except Exception:  # noqa: BLE001
            pass
    nmsp = new.modelspace()
    for e in list(msp):
        try:
            c = e.copy()
            if c.dxf.hasattr("linetype") and c.dxf.linetype not in new.linetypes:
                c.dxf.discard("linetype")
            nmsp.add_entity(c)
        except Exception:  # noqa: BLE001 — bitta element uchun butun chizma yo'qolmasin
            continue
    new.saveas(str(out))
