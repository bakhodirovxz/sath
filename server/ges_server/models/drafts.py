"""Qoralama obyektlar (web 3D da yaratilgan elementlar) → IFC ga qo'shish.

Web mesh (uchburchaklar, lokal IFC koordinatalar, metr) va joylashuvni (x, y, z, burilish z o'qi atrofida)
yuboradi; bu yerda ifcopenshell.api bilan IfcTriangulatedFaceSet (Body/MODEL_VIEW), joylashuv,
konteyner (qavat/maydon) va Pset_GES_* yoziladi. Mavjud versiya fayli nusxalanib to'ldiriladi;
versiya bo'lmasa — yangi IFC4 loyiha (Namuna GES kabi: Project → Site) yaratiladi.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.type
import ifcopenshell.api.unit
import ifcopenshell.util.representation
import numpy as np

# Web "kind" → IFC klassi (desktop GES obyektlari bilan bir xil)
IFC_CLASS = {
    "dam": "IfcWall",
    "penstock": "IfcPipeSegment",
    "turbine": "IfcFlowMovingDevice",
    "spillway": "IfcSlab",
    "powerhouse": "IfcBuildingElementProxy",
    "transformer": "IfcTransformer",
    "intake": "IfcBuildingElementProxy",
}
DEFAULT_CLASS = "IfcBuildingElementProxy"
MAX_VERTICES = 200_000


def _new_file() -> ifcopenshell.file:
    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Sath loyiha")
    ifcopenshell.api.unit.assign_unit(f)
    ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx
    )
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="GES maydoni")
    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    return f


def _container(f: ifcopenshell.file):
    for cls in ("IfcBuildingStorey", "IfcSite", "IfcBuilding"):
        items = f.by_type(cls)
        if items:
            return items[0]
    project = f.by_type("IfcProject")[0]
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="GES maydoni")
    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    return site


def _body_context(f: ifcopenshell.file):
    body = ifcopenshell.util.representation.get_context(f, "Model", "Body", "MODEL_VIEW")
    if body is not None:
        return body
    model = ifcopenshell.util.representation.get_context(f, "Model")
    if model is None:
        model = ifcopenshell.api.context.add_context(f, context_type="Model")
    return ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )


def _placement(t: dict) -> np.ndarray:
    x, y, z = (float(t.get(k, 0.0)) for k in ("x", "y", "z"))
    rz = math.radians(float(t.get("rz", 0.0)))
    c, s = math.cos(rz), math.sin(rz)
    m = np.eye(4)
    m[:3, :3] = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    m[:3, 3] = [x, y, z]
    return m


def _pset_value(f: ifcopenshell.file, v):
    if isinstance(v, bool):
        return f.createIfcBoolean(v)
    if isinstance(v, int):
        return f.createIfcInteger(v)
    if isinstance(v, float):
        return f.createIfcReal(v)
    return f.createIfcLabel(str(v))


def _capture(f: ifcopenshell.file, guid: str) -> dict | None:
    """Mavjud element (GlobalId) haqida tahrirda saqlanadigan ma'lumot: klass, konteyner, Pset lar, tur."""
    import ifcopenshell.util.element as ue

    try:
        el = f.by_guid(guid)
    except RuntimeError:
        return None
    if not el.is_a("IfcProduct"):
        return None
    psets = {}
    for name, props in ue.get_psets(el, psets_only=True, should_inherit=False).items():
        vals = {k: v for k, v in props.items() if k != "id" and v not in (None, "")}
        if vals:
            psets[name] = vals
    return {
        "class": el.is_a(),
        "name": el.Name,
        "container": ue.get_container(el, should_get_direct=True),
        "psets": psets,
        "type": ue.get_type(el),
        "predefined": getattr(el, "PredefinedType", None),
        "color": _surface_color(el),
    }


def _surface_color(el) -> tuple | None:
    """Elementning birinchi yuza rangi (IfcSurfaceStyleShading/Rendering) — tahrirda saqlash uchun."""
    rep = getattr(el, "Representation", None)
    if not rep:
        return None
    for r in rep.Representations or []:
        for item in r.Items or []:
            for st in getattr(item, "StyledByItem", None) or []:
                for style in st.Styles or []:
                    styles = [style]
                    if style.is_a("IfcPresentationStyleAssignment"):
                        styles = list(style.Styles or [])
                    for ss in styles:
                        if not ss.is_a("IfcSurfaceStyle"):
                            continue
                        for e in ss.Styles or []:
                            c = getattr(e, "SurfaceColour", None)
                            if c is not None:
                                return (float(c.Red), float(c.Green), float(c.Blue))
    return None


def add_object(f: ifcopenshell.file, body, container, obj: dict, orig: dict | None = None):
    """Bitta qoralama obyektni IFC ga qo'shadi; yaratilgan elementni qaytaradi.
    orig — tahrirlanayotgan asl element ma'lumoti (_capture): GUID, klass, konteyner, Pset lar saqlanadi."""
    mesh = obj.get("mesh") or {}
    verts = mesh.get("vertices") or []
    faces = mesh.get("faces") or []
    if not verts or not faces:
        raise ValueError(f"{obj.get('name') or obj.get('kind')}: mesh (vertices/faces) yo'q")
    if len(verts) > MAX_VERTICES:
        raise ValueError("Mesh juda katta")
    ifc_class = (
        (orig or {}).get("class")
        or obj.get("ifc_class")
        or IFC_CLASS.get(obj.get("kind", ""), DEFAULT_CLASS)
    )
    name = obj.get("name") or (orig or {}).get("name") or obj.get("kind")
    try:
        el = ifcopenshell.api.root.create_entity(f, ifc_class=ifc_class, name=name)
    except Exception:  # noqa: BLE001 — noma'lum klass (masalan IFC2X3 da IfcTransformer)
        el = ifcopenshell.api.root.create_entity(f, ifc_class=DEFAULT_CLASS, name=name)
    if orig:
        if obj.get("guid"):
            el.GlobalId = obj[
                "guid"
            ]  # GUID saqlanadi — versiyalar farqida «o'zgargan» bo'lib chiqadi
        if orig.get("predefined") and hasattr(el, "PredefinedType"):
            try:
                el.PredefinedType = orig["predefined"]
            except Exception:  # noqa: BLE001
                pass
        if orig.get("container") is not None:
            container = orig["container"]
        if orig.get("type") is not None:
            try:
                ifcopenshell.api.type.assign_type(
                    f, related_objects=[el], relating_type=orig["type"]
                )
            except Exception:  # noqa: BLE001
                pass
    vs = [[float(c) for c in v] for v in verts]
    fs = [[int(i) for i in fc] for fc in faces]
    rep = ifcopenshell.api.geometry.add_mesh_representation(
        f, context=body, vertices=[vs], faces=[fs]
    )
    ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
    color = obj.get("color") or (orig or {}).get("color")
    if color:
        _apply_color(f, rep, tuple(color))
    ifcopenshell.api.geometry.edit_object_placement(
        f, product=el, matrix=_placement(obj.get("transform") or {})
    )
    ifcopenshell.api.spatial.assign_container(f, relating_structure=container, products=[el])
    psets = dict((orig or {}).get("psets") or {})
    for pname, props in (obj.get("psets") or {}).items():
        psets[pname] = {**psets.get(pname, {}), **props}  # web qiymatlari asl Pset ustidan
    psets.pop("Pset_GES_Object", None)
    for pname, props in psets.items():
        if not props:
            continue
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name=pname)
        ifcopenshell.api.pset.edit_pset(
            f,
            pset=pset,
            properties={k: _pset_value(f, v) for k, v in props.items() if v not in (None, "")},
        )
    # Umumiy: qoralama manbasi va turi
    pset = ifcopenshell.api.pset.add_pset(f, product=el, name="Pset_GES_Object")
    ifcopenshell.api.pset.edit_pset(
        f,
        pset=pset,
        properties={
            "Manba": f.createIfcLabel("Sath web" + (" (tahrir)" if orig else "")),
            "Turi": f.createIfcLabel(str(obj.get("kind", ""))),
        },
    )
    return el


_STYLE_CACHE: dict[tuple, object] = {}


def _apply_color(f: ifcopenshell.file, rep, rgb: tuple) -> None:
    """Rang (0–1 RGB) → IfcSurfaceStyle (bir xil rang uchun bitta stil qayta ishlatiladi)."""
    import ifcopenshell.api.style

    alpha = (
        round(float(rgb[3]), 3) if len(rgb) > 3 else 1.0
    )  # 4-komponent — shaffoflik (kesim ko'rinishi)
    key = (id(f), tuple(round(float(c), 3) for c in rgb[:3]), alpha)
    style = _STYLE_CACHE.get(key)
    if style is None:
        style = ifcopenshell.api.style.add_style(f, name=f"rgb{key[1]}")
        colour = {"Name": None, "Red": key[1][0], "Green": key[1][1], "Blue": key[1][2]}
        if alpha < 1.0:
            ifcopenshell.api.style.add_surface_style(
                f,
                style=style,
                ifc_class="IfcSurfaceStyleRendering",
                attributes={
                    "SurfaceColour": colour,
                    "Transparency": 1.0 - alpha,
                    "ReflectanceMethod": "NOTDEFINED",
                },
            )
        else:
            ifcopenshell.api.style.add_surface_style(
                f,
                style=style,
                ifc_class="IfcSurfaceStyleShading",
                attributes={"SurfaceColour": colour},
            )
        _STYLE_CACHE[key] = style
    ifcopenshell.api.style.assign_representation_styles(f, shape_representation=rep, styles=[style])


def build(
    src: Path | None,
    objects: list[dict],
    out: Path,
    remove_names: list[str] | None = None,
    remove_guids: list[str] | None = None,
) -> dict:
    """src (mavjud versiya IFC) nusxasiga obyektlarni qo'shib `out` ga yozadi. src None — yangi fayl.
    remove_names — shu nomli elementlar avval olib tashlanadi (masalan parametrik relyefni DEM bilan almashtirish);
    remove_guids — GlobalId bo'yicha o'chirish (web «O'chirish»). obj["guid"] — mavjud elementni tahrirlash:
    asl element olib tashlanib, o'rniga shu GUID, klass, konteyner va Pset lar bilan yangi geometriya yoziladi."""
    f = ifcopenshell.open(str(src)) if src else _new_file()
    removed = 0
    if remove_names:
        for el in list(f.by_type("IfcProduct")):
            if el.Name in remove_names:
                ifcopenshell.api.root.remove_product(f, product=el)
                removed += 1
    for g in remove_guids or []:
        try:
            el = f.by_guid(g)
        except RuntimeError:
            continue
        if el.is_a("IfcProduct"):
            ifcopenshell.api.root.remove_product(f, product=el)
            removed += 1
    # tahrirlanadigan elementlar: avval ma'lumotni olib, keyin olib tashlaymiz
    origs: list[dict | None] = []
    for obj in objects:
        orig = _capture(f, obj["guid"]) if obj.get("guid") else None
        origs.append(orig)
        if orig is not None:
            ifcopenshell.api.root.remove_product(f, product=f.by_guid(obj["guid"]))
    body = _body_context(f)
    container = _container(f)
    guids = []
    for obj, orig in zip(objects, origs, strict=True):
        el = add_object(f, body, container, obj, orig)
        guids.append(el.GlobalId)
    f.write(str(out))
    return {"guids": guids, "count": len(guids), "schema": f.schema, "removed": removed}


def build_to_temp(
    src: Path | None, objects: list[dict], remove_guids: list[str] | None = None
) -> tuple[Path, dict]:
    tmp = Path(tempfile.mkdtemp(prefix="ges-drafts-")) / "drafts.ifc"
    info = build(src, objects, tmp, remove_guids=remove_guids)
    return tmp, info
