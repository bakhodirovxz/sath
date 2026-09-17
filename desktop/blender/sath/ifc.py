"""Bonsai (IFC) ko'prigi: loyiha ochish/saqlash, obyekt ↔ IFC element, Pset_GES_*, rang holati (diff/alarm)."""

from __future__ import annotations

from pathlib import Path

import bpy


def _tool():
    try:
        import bonsai.tool as tool
    except ImportError as e:
        raise RuntimeError("Bonsai addoni yoqilmagan (Edit → Preferences → Extensions → Bonsai)") from e
    return tool


def file():
    """Joriy IFC fayl (ifcopenshell) yoki None."""
    try:
        return _tool().Ifc.get()
    except RuntimeError:
        return None


def ensure_project():
    """Bonsai loyihasi yo'q bo'lsa — yangi (IFC4, My Site/Building/Storey)."""
    if file() is None:
        bpy.ops.bim.create_project()
    return file()


def load(path: Path) -> bool:
    """IFC ni Bonsai da ochadi. Loyiha allaqachon ochiq bo'lsa Bonsai yangi sessiya (read_homefile) boshlaydi —
    Scene.ges yo'qoladi; chaqiruvchi props.snapshot/restore qilsin. Qaytaradi: sessiya yangilandimi."""
    fresh = file() is not None
    bpy.ops.bim.load_project(filepath=str(path), should_start_fresh_session=fresh)
    return fresh


def save(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.bim.save_project(filepath=str(path), should_save_as=True)
    return path


def entity(obj):
    return _tool().Ifc.get_entity(obj)


def guid(obj) -> str | None:
    e = entity(obj)
    return getattr(e, "GlobalId", None) if e is not None else None


def guid_map() -> dict[str, bpy.types.Object]:
    out = {}
    for o in bpy.data.objects:
        g = guid(o)
        if g:
            out[g] = o
    return out


def object_for_guid(g: str):
    f = file()
    if f is None:
        return None
    try:
        return _tool().Ifc.get_object(f.by_guid(g))
    except RuntimeError:
        return None


def write_psets(e, psets: dict[str, dict]) -> None:
    """{pset: {name: value}} → IfcPropertySet lar (mavjud bo'lsa yangilanadi)."""
    import ifcopenshell.api.pset as api
    import ifcopenshell.util.element as ue

    f = file()
    existing = ue.get_psets(e)
    for name, values in psets.items():
        if name in existing:
            ps = f.by_id(existing[name]["id"])
        else:
            ps = api.add_pset(f, product=e, name=name)
        api.edit_pset(f, pset=ps, properties=values)


def _activate(obj) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def assign_class(obj, ifc_class: str, psets: dict[str, dict] | None = None):
    """Mesh obyektni IFC element qiladi (Bonsai konteynerga o'zi joylaydi), psetlarni yozadi."""
    ensure_project()
    _activate(obj)
    bpy.ops.bim.assign_class(ifc_class=ifc_class)
    e = entity(obj)
    if psets:
        write_psets(e, psets)
    return e


def update_representation(obj) -> None:
    bpy.ops.bim.update_representation(obj=obj.name)


def select_guids(guids: list[str]) -> int:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    n = 0
    for g in guids:
        o = object_for_guid(g)
        if o is None or o.name not in bpy.context.view_layer.objects:
            continue
        try:
            o.hide_set(False)  # ko'rinishga o'tish: yashirin bo'lsa ochamiz
            o.select_set(True)
        except RuntimeError:
            continue
        bpy.context.view_layer.objects.active = o
        n += 1
    return n


class ColorState:
    """Obyekt ranglarini vaqtincha almashtirish (diff / alarm) va qaytarish. Viewport: Object color."""

    def __init__(self):
        self.saved: dict[str, tuple] = {}

    def paint(self, colors: dict[str, tuple]) -> int:
        n = 0
        for g, rgba in colors.items():
            o = object_for_guid(g)
            if o is None:
                continue
            if o.name not in self.saved:
                self.saved[o.name] = tuple(o.color)
            o.color = rgba
            n += 1
        if n and bpy.context.screen is not None:
            for area in bpy.context.screen.areas:
                if area.type == "VIEW_3D":
                    area.spaces.active.shading.color_type = "OBJECT"
        return n

    def restore(self) -> None:
        for name, rgba in self.saved.items():
            o = bpy.data.objects.get(name)
            if o is not None:
                o.color = rgba
        self.saved.clear()


DIFF_STATE = ColorState()
ALARM_STATE = ColorState()
