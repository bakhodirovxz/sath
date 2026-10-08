"""Bonsai (IFC) ko'prigi: loyiha ochish/saqlash, obyekt ↔ IFC element, Pset_GES_*, rang holati (diff/alarm)."""

from __future__ import annotations

import contextlib
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
    Scene.ges yo'qoladi; chaqiruvchi props.snapshot/restore qilsin. Qaytaradi: sessiya yangilandimi.
    K3: epoch oshadi (oldingi model uchun boshlangan fon vazifalari natijasi tashlanadi), `ifc.loaded` e'lon qilinadi."""
    from . import session
    from .core import events

    fresh = file() is not None
    bpy.ops.bim.load_project(filepath=str(path), should_start_fresh_session=fresh)
    session.bump_epoch()
    events.publish("ifc.loaded", path=str(path))
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


def stamp_guids() -> int:
    """IFC elementli obyektlarga `sath_guid` custom property yozadi — Blender eksporti (glTF extras, FBX custom
    properties) GUID ni olib ketadi, qayta importda element yangilanadi, ikki barobar bo'lmaydi (CAD-07)."""
    n = 0
    for o in bpy.data.objects:
        g = guid(o)
        if g and o.get("sath_guid") != g:
            o["sath_guid"] = g
            n += 1
    return n


def object_for_guid(g: str):
    f = file()
    if f is None:
        return None
    try:
        return _tool().Ifc.get_object(f.by_guid(g))
    except RuntimeError:
        return None


def write_psets(e, psets: dict[str, dict], text: tuple[str, ...] = ()) -> None:
    """{pset: {name: value}} → IfcPropertySet lar (mavjud bo'lsa yangilanadi). `text` dagi nomlar IfcText bo'lib
    yoziladi — IfcLabel 255 belgi bilan cheklangan (K2: Pset_SathParametric.Params JSON)."""
    import ifcopenshell.api.pset as api
    import ifcopenshell.util.element as ue

    f = file()
    existing = ue.get_psets(e)
    for name, values in psets.items():
        if name in existing:
            ps = f.by_id(existing[name]["id"])
        else:
            ps = api.add_pset(f, product=e, name=name)
        props = {k: (f.create_entity("IfcText", v) if k in text and isinstance(v, str) else v) for k, v in values.items()}
        api.edit_pset(f, pset=ps, properties=props)


def _activate(obj) -> None:
    for o in bpy.context.view_layer.objects:
        if o is not None:  # ommaviy o'chirilgan obyektlar view layer sinxronlanguncha None bo'lib turadi
            o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def assign_class(obj, ifc_class: str, psets: dict[str, dict] | None = None):
    """Mesh obyektni IFC element qiladi (Bonsai konteynerga o'zi joylaydi), psetlarni yozadi."""
    name = obj.name
    ensure_project()
    obj = bpy.data.objects.get(name, obj)  # create_project dan keyin havola yangilanadi
    _activate(obj)
    bpy.ops.bim.assign_class(ifc_class=ifc_class)
    e = entity(obj)
    if psets:
        write_psets(e, psets)
    return e


_warned_batch = False


def _has_ref(value, ids: set[int]) -> bool:
    import ifcopenshell

    if isinstance(value, ifcopenshell.entity_instance):
        return value.id() in ids
    if isinstance(value, (tuple, list)):
        return any(_has_ref(v, ids) for v in value)
    return False


def _has_any_ref(value) -> bool:
    import ifcopenshell

    if isinstance(value, ifcopenshell.entity_instance):
        return True
    if isinstance(value, (tuple, list)):
        return any(_has_any_ref(v) for v in value)
    return False


def _record_batch_inverses(tr, ids: set[int]) -> dict:
    """Chiziqli batch yozuvi: o'chiriladigan har bir elementning o'z oldinga havolalari va tirik (o'chirilmaydigan)
    havola qiluvchilarning shu elementlarga ishora qiluvchi atributlari — {id: [(indeks, qiymat)]}, BIR marta."""
    inv: dict = {}
    survivors: dict = {}
    for i in ids:
        el = tr.file.by_id(i)
        fwd = [(k, tr.serialise_value(el, el[k])) for k in range(len(el)) if _has_any_ref(el[k])]
        if fwd:
            inv[i] = fwd
        for r in tr.file.get_inverse(el):
            if r.id() not in ids:
                survivors[r.id()] = r
    for rid, r in survivors.items():
        refs = [(k, tr.serialise_value(r, r[k])) for k in range(len(r)) if _has_ref(r[k], ids)]
        if refs:
            inv[rid] = refs
    return inv


# Faqat shu versiyada sinalgan (undo_rep headless testi). Har bir Bonsai/ifcopenshell yangilanishida undo_rep bilan
# qayta tekshirib, keyin bu yerga yangi versiyani yozing — boshqa versiyada yamoq yoqilmaydi (sekin, lekin to'g'ri).
_BATCH_PATCH_VERSION = "0.9.0"


@contextlib.contextmanager
def _linear_batch_delete():
    """ifcopenshell 0.9.0: tranzaksiya ichidagi batch o'chirish har bir yuz uchun butun Faces ro'yxatini qayta
    serializatsiya qiladi (kvadratik; 30 ming yuzda soatlar). Bu yerda batch yozuvi chiziqli: o'chirilgan har bir
    element uchun (1) o'z oldinga havolalari va (2) tirik (o'chirilmaydigan) havola qiluvchilarning atributlari
    unbatch da BIR marta yoziladi — rollback (Ctrl+Z) hamma elementni qayta yaratgach ularni qayta bog'laydi.
    Faqat ifcopenshell 0.9.0 (aniq versiya) va faqat faol IFC fayl tranzaksiyasi uchun. Yozuv xato bersa —
    upstream (element bo'yicha, sekin) yozuvga qaytiladi; asl unbatch HAR DOIM chaqiriladi (fayl batch da qolmaydi)."""
    global _warned_batch
    try:
        import ifcopenshell
        from ifcopenshell.file import Transaction

        ok = ifcopenshell.version == _BATCH_PATCH_VERSION and all(
            hasattr(Transaction, a)
            for a in ("store_delete", "unbatch", "serialise_value", "serialise_entity_instance", "get_element_inverses")
        )
    except (ImportError, AttributeError):
        ok = False
    if not ok:
        if not _warned_batch:
            _warned_batch = True
            print(
                f"sath: ifcopenshell {_BATCH_PATCH_VERSION} emas — tez batch o'chirish yoqilmadi "
                "(katta mesh sekin bo'lishi mumkin)"
            )
        yield
        return
    f = file()
    orig_delete, orig_unbatch = Transaction.store_delete, Transaction.unbatch

    def store_delete(self, element):
        if not self.is_batched or self.file is not f:
            return orig_delete(self, element)
        self.batch_delete_ids.add(element.id())
        self.operations.append({"action": "delete", "inverses": {}, "value": self.serialise_entity_instance(element)})

    def unbatch(self):
        try:
            if self.file is f and self.is_batched and self.batch_delete_ids:
                ids = set(self.batch_delete_ids)
                try:
                    inv = _record_batch_inverses(self, ids)
                    self.batch_inverses = [inv] if inv else []
                except Exception as e:  # noqa: BLE001 — kutilmagan element: upstream yozuviga qaytamiz
                    print(f"sath: tez batch yozuvi bajarilmadi ({e}) — upstream (sekin) yozuv ishlatildi")
                    self.batch_inverses = [self.get_element_inverses(self.file.by_id(i)) for i in ids]
        finally:
            orig_unbatch(self)

    Transaction.store_delete, Transaction.unbatch = store_delete, unbatch
    try:
        yield
    finally:
        Transaction.store_delete, Transaction.unbatch = orig_delete, orig_unbatch


def update_representation(obj) -> None:
    with _linear_batch_delete():
        bpy.ops.bim.update_representation(obj=obj.name)


def sync_placement(obj) -> None:
    """Blender joylashuvini (location/rotation) IFC ObjectPlacement ga yozish (saqlashni kutmasdan)."""
    if entity(obj) is None:
        return
    try:
        bpy.ops.bim.edit_object_placement(obj=obj.name)
    except RuntimeError as e:  # noqa: BLE001
        print("sath: joylashuvni yozib bo'lmadi", obj.name, e)


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
