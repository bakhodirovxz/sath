"""GES parametrik obyektlari Blender da: parametrlar obyektda (Object.ges), sxema va geometriya — sof Python
`shared/ges_kinds` (+ `shared/geom`, numpy; FreeCAD siz), IFC element + Pset_GES_* Bonsai da. Mesh Blender ga
numpy massivlari bilan (`foreach_set`) uzatiladi. K4: parametr o'zgarsa FAQAT mesh qayta quriladi va `ifc_dirty`
belgilanadi; IFC ga (representation, psetlar) `sath.sync_ifc` yozadi — IfcOperator ichida, bitta undo qadami.

Qayta qurish faqat GEOMETRIK parametr o'zgarganda (`ges_kinds.Param.geometric`, `geom_dirty`): quvvat, FIK, material,
rol kabi o'zgarishlar faqat psetlarni yozadi — mesh va IFC representation tegilmaydi (I1).
Taxminiy obyektlar (`inferred`: eski Pset_GES_* dan tiklangan, geometrik parametrlarning ko'pi pset da yo'q — default):
geometrik parametr o'zgarsa mesh QAYTA QURILMAYDI (IFC dagi asl geometriya qoladi), foydalanuvchiga haqiqiy
o'lchamlarni kiritib «O'lchamlarni tasdiqlash» (sath.confirm_dimensions) bosish aytiladi; faqat shu operator taxminiy
obyekt geometriyasini parametrlardan quradi. Belgi IFC da ham saqlanadi (Pset_SathParametric.Approximate)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import bpy
import numpy as np

from . import ifc
from .core import events, ui_tasks
from .core.ifc_ops import IfcOperator, SathOpError
from .shared import ges_kinds

KIND_ITEMS = [(k, s.label, "") for k, s in ges_kinds.KINDS.items()]
KIND_LABEL = {k: s.label for k, s in ges_kinds.KINDS.items()}


def _enum_items(self, context):
    return [(x, x, "") for x in self.items.split(";") if x]


_pending: set[str] = set()
DEBOUNCE = 0.15


def flush_pending():
    """Kechiktirilgan mesh qayta qurish (timer yoki darhol): FAQAT mesh — IFC ga yozish `sath.sync_ifc` da (K4: timer
    ichida bpy.ops/IFC tranzaksiyasi yo'q). Xatolar holat qatori va popup da (avval print ga yutilardi)."""
    names = sorted(_pending)
    _pending.clear()
    errors = []
    for n in names:
        obj = bpy.data.objects.get(n)
        if obj is not None and obj.ges.kind:
            try:
                rebuild_mesh(obj)
            except Exception as e:  # noqa: BLE001 — bitta obyekt xatosi qolganini to'xtatmasin
                errors.append(f"{n}: {e}")
    if errors:
        ui_tasks.show_error("GES qayta qurish", "; ".join(errors))
    return None


_warned_inferred: set[str] = set()
INFERRED_HINT = (
    "o'lchamlar taxminiy — geometriya IFC dan olingan, mesh qayta qurilmadi. Barcha haqiqiy o'lchamlarni kiriting "
    "va «O'lchamlarni tasdiqlash» tugmasini bosing"
)


def _hold_inferred(obj) -> None:
    """Taxminiy obyektning birinchi geometrik tahriri: mesh o'zgarmaydi, foydalanuvchiga bir marta aytiladi."""
    obj.ges.geom_dirty = True
    if obj.name not in _warned_inferred:
        _warned_inferred.add(obj.name)
        ui_tasks.show_error("GES: o'lchamlar taxminiy", f"{obj.name}: {INFERRED_HINT}")


def _changed(self, context):
    obj = self.id_data
    g = getattr(obj, "ges", None)
    if g is None or not g.kind or g.busy:
        return
    g.ifc_dirty = True
    if self.name not in ges_kinds.geometric_params(g.kind):
        return  # faqat psetlar (sync_ifc) — mesh va representation tegilmaydi
    if g.inferred:
        _hold_inferred(obj)
        return
    g.geom_dirty = True
    _pending.add(obj.name)
    if bpy.app.background:  # testlar: darhol
        flush_pending()
        return
    if not bpy.app.timers.is_registered(flush_pending):
        bpy.app.timers.register(flush_pending, first_interval=DEBOUNCE)


def _role_changed(self, context):
    if self.kind and not self.busy:
        self.ifc_dirty = True  # rol Pset_SathParametric da — keyingi sync_ifc yozadi


class GesParam(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ptype: bpy.props.StringProperty()  # length | float | int | enum
    items: bpy.props.StringProperty()  # enum: "a;b;c"
    value_float: bpy.props.FloatProperty(precision=3, update=_changed)
    value_int: bpy.props.IntProperty(update=_changed)
    value_enum: bpy.props.EnumProperty(items=_enum_items, update=_changed)


class GesObject(bpy.types.PropertyGroup):
    kind: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty(default=False)
    role: bpy.props.StringProperty(
        description="Egizakdagi roli: unit:1, gen:1, draft:1, penstock:1, dam, tailrace…", update=_role_changed
    )
    ifc_dirty: bpy.props.BoolProperty(default=False, description="Parametrlar IFC ga yozilmagan (sath.sync_ifc)")
    geom_dirty: bpy.props.BoolProperty(
        default=False, description="Geometrik parametr o'zgargan — sync_ifc representation ni ham yozadi"
    )
    inferred: bpy.props.BoolProperty(
        default=False,
        description="O'lchamlar taxminiy (eski Pset_GES_* dan): geometriya IFC dagidek, tasdiqlanmaguncha qayta qurilmaydi",
    )
    params: bpy.props.CollectionProperty(type=GesParam)


def clean_float(x: float) -> float:
    """FloatProperty float32 shovqinini olib tashlash (0.92 → 0.9200000166893005 → 0.92): 7 ta muhim raqam — float32
    aniqligi; IFC (Pset_GES_*, Params JSON) ga toza qiymat yoziladi."""
    return float(f"{x:.7g}")


def params_dict(obj) -> dict:
    out = {}
    for p in obj.ges.params:
        if p.ptype == "enum":
            out[p.name] = p.value_enum
        elif p.ptype == "int":
            out[p.name] = p.value_int
        else:
            out[p.name] = clean_float(p.value_float)
    return out


def set_params(obj, **values) -> None:
    """Bir nechta parametrni bir yo'la o'rnatib, mesh ni bir marta qayta qurish (har birida emas; faqat geometrik
    parametr o'zgargan bo'lsa, taxminiy obyektda — yo'q); IFC ga — sync_ifc."""
    g = obj.ges
    before = params_dict(obj)
    g.busy = True
    try:
        for p in g.params:
            if p.name not in values:
                continue
            v = values[p.name]
            if p.ptype == "enum":
                p.value_enum = str(v)
            elif p.ptype == "int":
                p.value_int = int(v)
            else:
                p.value_float = float(v)
    finally:
        g.busy = False
    after = params_dict(obj)
    g.ifc_dirty = True
    if any(before[k] != after[k] for k in ges_kinds.geometric_params(g.kind)):
        if g.inferred:
            _hold_inferred(obj)
            return
        rebuild_mesh(obj)
        g.geom_dirty = True


def by_role(role: str):
    return next((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.role == role), None)


def by_kind_all() -> list:
    return [o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind]


def by_kind(kind: str) -> list:
    return sorted((o for o in bpy.data.objects if getattr(o, "ges", None) and o.ges.kind == kind), key=lambda o: o.name)


def _fill_schema(obj, kind: str, values: dict | None = None) -> None:
    """Sxema (ges_kinds) → obj.ges.params; values — parametrlar (tekshiriladi), yo'q bo'lsa defaultlar."""
    vals = ges_kinds.normalize(kind, values)
    g = obj.ges
    g.busy = True
    try:
        g.kind = kind
        g.params.clear()
        for prm in ges_kinds.spec(kind).params:
            p = g.params.add()
            p.name, p.label, p.ptype = prm.name, prm.label, prm.ptype
            v = vals[prm.name]
            if prm.ptype == "enum":
                p.items = ";".join(prm.items)
                p.value_enum = v
            elif prm.ptype == "int":
                p.value_int = v
            else:
                p.value_float = v
    finally:
        g.busy = False


def set_mesh(me, verts: np.ndarray, faces: np.ndarray) -> None:
    """(V float64, F int64 uchburchak) → bpy Mesh, numpy foreach_set bilan (from_pydata Python ro'yxatlarisiz)."""
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"set_mesh: yuzlar (N, 3) uchburchak bo'lishi kerak, berilgan shakl {faces.shape}")
    me.clear_geometry()
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(faces, dtype=np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update(calc_edges=True)


def rebuild_mesh(obj) -> None:
    """Parametrlardan mesh (ges_kinds.build). Yaroqsiz parametr — ValueError (matn foydalanuvchiga)."""
    v, f = ges_kinds.build(obj.ges.kind, params_dict(obj))
    set_mesh(obj.data, v, f)


def write_ifc(obj, geometry: bool = True) -> None:
    """IFC element (yo'q bo'lsa assign_class) yoki — `geometry` bo'lsa — representation, keyin Pset_GES_* +
    Pset_SathParametric (K2: tur, rol, barcha parametrlar, Approximate — qayta ochilganda to'liq tiklanadi).
    Representation yozilmasa (ifc.RepresentationNotUpdated) — hech narsa «sinxron» deb belgilanmaydi."""
    g = obj.ges
    p = params_dict(obj)
    ps = {**ges_kinds.psets(g.kind, p), **ges_kinds.parametric_pset(g.kind, g.role, p, approximate=g.inferred)}
    e = ifc.entity(obj)
    if e is None:
        e = ifc.assign_class(obj, ges_kinds.spec(g.kind).ifc_class)
    elif geometry:
        ifc.update_representation(obj)
    ifc.write_psets(e, ps, text=("Params",))
    g.ifc_dirty = False
    if geometry:
        g.geom_dirty = False


def rebuild(obj) -> None:
    """Mesh (ges_kinds) + IFC (representation, psetlar)."""
    rebuild_mesh(obj)
    write_ifc(obj)


def dirty_objects() -> list:
    return [o for o in by_kind_all() if o.ges.ifc_dirty]


def sync_ifc(objs=None, force_geometry: bool = False) -> int:
    """IFC bilan sinxronlanmagan (yoki berilgan) GES obyektlarini IFC ga yozadi. IfcOperator ichida chaqiriladi
    (sath.sync_ifc, sath.rebuild_object, sath.confirm_dimensions, commit) — bitta undo qadami. Avval HAMMA obyekt
    tekshiriladi: geometrik o'zgarishi bor (yoki `force_geometry`) obyektlar mesh i parametrlardan qayta quriladi
    (kechikkan timer ham shu yerda), qolganlari faqat tekshiriladi — yaroqsiz parametr bo'lsa IFC ga hech narsa
    yozilmaydi (SathOpError). Geometrik bo'lmagan o'zgarish (quvvat, rol…) — faqat psetlar, mesh/representation
    tegilmaydi. Taxminiy (`inferred`) obyekt geometriyasi bu yerda HECH QACHON qayta qurilmaydi (sath.confirm_dimensions).
    Bonsai representation ni yozmagan obyektlar «sinxronlanmagan» bo'lib qoladi va xato nomlari bilan ko'tariladi."""
    todo = dirty_objects() if objs is None else list(objs)
    _pending.difference_update(o.name for o in todo)
    plan = []
    for o in todo:
        geo = (force_geometry or o.ges.geom_dirty) and not o.ges.inferred
        try:
            if geo:
                rebuild_mesh(o)
            else:
                ges_kinds.validate(o.ges.kind, params_dict(o))
        except ValueError as e:
            raise SathOpError(f"{o.name}: {e}") from e
        plan.append((o, geo))
    failed = []
    for o, geo in plan:
        try:
            write_ifc(o, geometry=geo)
        except ifc.RepresentationNotUpdated as e:
            failed.append(str(e))
    if failed:
        raise SathOpError("IFC ga yozilmadi (obyektlar sinxronlanmagan bo'lib qoldi): " + "; ".join(failed))
    return len(plan)


def default_role(kind: str) -> str:
    """Rol berilmagan qo'lda qo'shilgan obyekt uchun: yagona tur — o'z roli (band bo'lmasa), indeksli tur (unit:, gen:, …) —
    birinchi bo'sh raqam (demo_plant sxemasi). Band bo'lsa — "" (egizak bog'lamaydi, lekin jim ham emas)."""
    role = ges_kinds.spec(kind).role
    taken = {o.ges.role for o in by_kind_all() if o.ges.role}
    if not role.endswith(":"):
        return "" if role in taken else role
    n = 1
    while f"{role}{n}" in taken:
        n += 1
    return f"{role}{n}"


def add(context, kind: str, name: str | None = None, role: str = "", **params):
    """GES obyekti: parametrlar darhol beriladi (keyin set_params bilan qayta qurish shart emas). `role` berilmasa —
    turning birinchi bo'sh roli (`default_role`)."""
    s = ges_kinds.spec(kind)
    ges_kinds.validate(kind, params)  # avval tekshiruv: yaroqsiz parametrda data-block yaratilmaydi
    ifc.ensure_project()  # GUI da create_project sahnani qayta quradi (obyekt havolasi eskiradi)
    me = bpy.data.meshes.new(kind)
    obj = bpy.data.objects.new(name or s.label, me)
    try:
        context.scene.collection.objects.link(obj)
        obj.color = (*s.color, 1.0)
        _fill_schema(obj, kind, params)
        obj.ges.role = role or default_role(kind)
        rebuild(obj)
    except Exception:
        _discard(obj, me)
        raise
    return obj


def _discard(obj, me) -> None:
    """add() xatosi: Blender obyekti, mesh(lar) va — assign_class ulgurgan bo'lsa — IFC element ham o'chiriladi
    (yetim qolmaydi). IfcOperator ichida bu o'chirish ham o'sha tranzaksiyaga yoziladi."""
    meshes = [me, obj.data]  # Bonsai assign_class mesh ni almashtirishi (eskisini o'chirishi) mumkin
    try:
        ifc.discard_entity(obj)
    except Exception as e:  # noqa: BLE001 — asl xato yo'qolmasin; IFC qoldig'i — orphans()/purge
        print("sath: add() xatosidan keyin IFC elementini o'chirib bo'lmadi:", e)
    bpy.data.objects.remove(obj)
    for m in meshes:
        try:
            if m is not None and m.users == 0:
                bpy.data.meshes.remove(m)
        except ReferenceError:  # allaqachon o'chirilgan (Bonsai yoki ro'yxatda takror)
            pass


@dataclass
class RestoreReport:
    restored: list[str] = field(default_factory=list)  # Pset_SathParametric dan (to'liq)
    # o'lchamlar taxminiy: Pset_GES_* dan (geometriya parametrlari qisman, rol taxminiy) yoki Approximate=True
    inferred: list[str] = field(default_factory=list)
    unknown: list[tuple[str, str]] = field(default_factory=list)  # (obyekt, sabab)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # IFC ga yozilmagan o'zgarishi bor — tiklanmadi (M7)

    def text(self) -> str:
        s = f"GES: {len(self.restored)} tiklandi, {len(self.inferred)} taxminiy, {len(self.unknown)} noma'lum"
        if self.unknown:
            s += " — " + "; ".join(f"{n}: {why}" for n, why in self.unknown[:3])
        if self.skipped:
            s += f"; {len(self.skipped)} o'tkazildi (IFC ga yozilmagan o'zgarish bor: {', '.join(self.skipped[:5])})"
        return s


LAST_REPORT = RestoreReport()


def _set_role(obj, role: str) -> None:
    g = obj.ges
    g.busy = True  # K4: rol o'zgarishi «ifc_dirty» qo'ymasin (tiklash IFC ni o'zgartirmaydi)
    try:
        g.role = role
    finally:
        g.busy = False


def _next_free(role: str, taken: set[str]) -> str:
    """Indeksli rol (unit:2) band bo'lsa — shu turdagi birinchi bo'sh raqam; yagona rol (dam) — ""."""
    if ":" not in role:
        return ""
    prefix = role.split(":", 1)[0] + ":"
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


def restore_from_ifc(skip_dirty: bool = False) -> RestoreReport:
    """K2: IFC elementli obyektlar → obj.ges (kind, role, params, inferred) Pset_SathParametric dan, bo'lmasa
    Pset_GES_* dan (rollar X bo'yicha). Mesh qayta QURILMAYDI — GUID va geometriya IFC dagidek qoladi; tanilmaganlar
    hisobotda. `skip_dirty` (qo'lda «IFC dan tiklash»): IFC ga yozilmagan o'zgarishi bor obyektlar tegilmaydi."""
    import ifcopenshell.util.element as ue

    global LAST_REPORT
    rep = RestoreReport()
    guess = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or getattr(obj, "ges", None) is None:
            continue
        e = ifc.entity(obj)
        if e is None:
            continue
        if skip_dirty and obj.ges.kind and obj.ges.ifc_dirty:
            rep.skipped.append(obj.name)
            continue
        try:
            r = ges_kinds.from_psets(ue.get_psets(e))
        except ges_kinds.UnknownKind as err:
            rep.unknown.append((obj.name, str(err)))
            continue
        except Exception as err:  # noqa: BLE001 — bitta buzuq element butun faylni to'xtatmasin
            rep.unknown.append((obj.name, f"{type(err).__name__}: {err}"))
            continue
        if r is None:
            continue
        # pset dan (rolsiz) tiklanganda — qo'lda «IFC dan tiklash» da obyektning mavjud roli saqlanadi
        role = r.role or (obj.ges.role if obj.ges.kind == r.kind else "")
        try:
            _fill_schema(obj, r.kind, r.params)
            _set_role(obj, role)
            obj.ges.inferred = r.approximate
            obj.ges.geom_dirty = False  # mesh — IFC dagi geometriya
            obj.color = (*ges_kinds.spec(r.kind).color, 1.0)
        except Exception as err:  # noqa: BLE001
            rep.unknown.append((obj.name, f"{type(err).__name__}: {err}"))
            continue
        _warned_inferred.discard(obj.name)
        rep.warnings += [f"{obj.name}: {w}" for w in r.warnings]
        if r.approximate:
            rep.inferred.append(obj.name)
        else:
            rep.restored.append(obj.name)
        if not role and r.source != "parametric":  # Pset_SathParametric dagi bo'sh rol — ataylab (bog'lanmagan)
            guess.append((obj.name, r.kind, obj.matrix_world.translation.x))
    if guess:  # X bo'yicha; band rol (qisman sinxronlangan eski model) — keyingi bo'sh raqam, yagona tur — rolsiz
        taken = {o.ges.role for o in by_kind_all() if o.ges.role}
        for name, role in ges_kinds.infer_roles(guess).items():
            if role in taken:
                role = _next_free(role, taken)
            if role:
                _set_role(bpy.data.objects[name], role)
                taken.add(role)
    LAST_REPORT = rep
    return rep


def _on_ifc_loaded(payload: dict) -> None:
    rep = restore_from_ifc()
    if rep.unknown or rep.warnings:
        ui_tasks.show_error("GES tiklash", rep.text() + ("; " + "; ".join(rep.warnings[:3]) if rep.warnings else ""))
    elif rep.restored or rep.inferred:
        ui_tasks.status(rep.text())


class SATH_OT_restore_ges(bpy.types.Operator):
    """GES obyektlarining tur, rol va parametrlarini IFC psetlaridan qayta tiklash (mesh o'zgarmaydi; IFC ga yozilmagan o'zgarishi bor obyektlar o'tkaziladi). Bonsai ning o'z File → Open i bilan ochilgan modelda shu tugmani bosing"""

    bl_idname = "sath.restore_ges"
    bl_label = "IFC dan tiklash"
    bl_options = {"REGISTER", "UNDO"}  # faqat Blender xususiyatlari (IFC o'zgarmaydi) — oddiy Blender undo

    def execute(self, context):
        rep = restore_from_ifc(skip_dirty=True)
        self.report({"WARNING"} if rep.unknown or rep.skipped else {"INFO"}, rep.text())
        return {"FINISHED"}


class SATH_OT_add_object(IfcOperator, bpy.types.Operator):
    """GES obyekti qo'shish (sof Python geometriya, IFC element + Pset_GES_*; bitta undo qadami)"""

    bl_idname = "sath.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    def _execute(self, context):
        try:
            obj = add(context, self.kind)
        except ValueError as e:  # yaroqsiz parametr — kutilgan xato
            raise SathOpError(f"Obyekt yaratilmadi: {e}") from e
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"{KIND_LABEL[self.kind]} qo'shildi")
        return {"FINISHED"}


class SATH_OT_rebuild_object(IfcOperator, bpy.types.Operator):
    """Tanlangan GES obyektlarini qayta hisoblash va IFC ga yozish"""

    bl_idname = "sath.rebuild_object"
    bl_label = "Qayta qurish"
    bl_options = {"REGISTER", "UNDO"}

    def _execute(self, context):
        objs = [o for o in context.view_layer.objects if o.select_get() and o.ges.kind]
        sync_ifc(objs, force_geometry=True)  # mesh + IFC; yaroqsiz parametr — SathOpError (op.report, traceback siz)
        held = [o.name for o in objs if o.ges.inferred]
        if held:  # taxminiy obyekt geometriyasi faqat sath.confirm_dimensions bilan
            self.report({"WARNING"}, f"{', '.join(held[:5])}: {INFERRED_HINT}")
        else:
            self.report({"INFO"}, f"{len(objs)} obyekt qayta qurildi")
        return {"FINISHED"}


class SATH_OT_confirm_dimensions(IfcOperator, bpy.types.Operator):
    """Taxminiy (eski IFC dan tiklangan) obyekt: kiritilgan o'lchamlar haqiqiy — mesh va IFC representation shu parametrlardan qayta quriladi (bitta undo qadami)"""

    bl_idname = "sath.confirm_dimensions"
    bl_label = "O'lchamlarni tasdiqlash"
    bl_options = {"REGISTER", "UNDO"}
    sath_needs_project = False
    obj: bpy.props.StringProperty(options={"SKIP_SAVE"})  # bo'sh — faol obyekt

    @classmethod
    def poll(cls, context):
        return ifc.file() is not None

    def _target(self, context):
        o = bpy.data.objects.get(self.obj) if self.obj else context.active_object
        return o if o is not None and getattr(o, "ges", None) and o.ges.kind and o.ges.inferred else None

    def invoke(self, context, event):
        o = self._target(context)
        if o is None:
            self.report({"ERROR"}, "Taxminiy GES obyekti tanlanmagan")
            return {"CANCELLED"}
        msg = f"«{o.name}» geometriyasi panelda kiritilgan o'lchamlardan qayta quriladi (IFC dagi asl shakl almashadi)"
        return context.window_manager.invoke_confirm(self, event, title=self.bl_label, message=msg)

    def _execute(self, context):
        o = self._target(context)
        if o is None:
            raise SathOpError("Taxminiy GES obyekti tanlanmagan")
        o.ges.inferred = False  # Pset_SathParametric.Approximate = False bo'lib yoziladi
        try:
            sync_ifc([o], force_geometry=True)
        except Exception:
            o.ges.inferred = True
            raise
        _warned_inferred.discard(o.name)
        self.report({"INFO"}, f"{o.name}: o'lchamlar tasdiqlandi, geometriya qayta qurildi")
        return {"FINISHED"}


class SATH_OT_sync_ifc(IfcOperator, bpy.types.Operator):
    """Parametrlari o'zgargan GES obyektlarini IFC ga yozish (representation, Pset_GES_*, Pset_SathParametric)"""

    bl_idname = "sath.sync_ifc"
    bl_label = "IFC ga qo'llash"
    bl_options = {"REGISTER", "UNDO"}
    sath_needs_project = False

    @classmethod
    def poll(cls, context):
        return ifc.file() is not None  # M6: loyiha yo'q — tranzaksiya ichida create_project chaqirilmasin

    def _execute(self, context):
        if ifc.file() is None:
            raise SathOpError("IFC loyiha ochilmagan")
        n = sync_ifc()
        self.report({"INFO"}, f"{n} obyekt IFC ga yozildi" if n else "IFC sinxron")
        return {"FINISHED"}


class SATH_OT_purge_orphans(IfcOperator, bpy.types.Operator):
    """IFC dagi yetim entitylarni o'chirish (Blender obyekti yo'q GES elementlari, bog'lanmagan pset/representation)"""

    bl_idname = "sath.purge_orphans"
    bl_label = "Yetim IFC entitylarni o'chirish"
    bl_options = {"REGISTER", "UNDO"}
    sath_needs_project = False

    def _execute(self, context):
        n = ifc.purge_orphans()
        self.report({"INFO"}, f"{n} yetim entity o'chirildi")
        return {"FINISHED"}


class SATH_PT_objects(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Sath"
    bl_label = "GES obyektlari"

    def draw(self, context):
        lay = self.layout
        s = context.scene.ges
        box = lay.box()
        row = box.row(align=True)
        row.prop(s, "demo_head")
        row.prop(s, "demo_units")
        row = box.row(align=True)
        row.prop(s, "demo_unit_mw")
        row.operator("sath.build_demo_plant", icon="ADD")
        if s.twin_note:
            box.label(text=s.twin_note, icon="INFO")
        grid = lay.grid_flow(columns=2, align=True)
        for k, label, _ in KIND_ITEMS:
            grid.operator("sath.add_object", text=label).kind = k
        n_dirty = len(dirty_objects())
        if n_dirty:
            row = lay.row(align=True)
            row.label(text=f"{n_dirty} obyekt IFC bilan sinxronlanmagan", icon="ERROR")
            row.operator("sath.sync_ifc", text="IFC ga qo'llash", icon="EXPORT")
        lay.operator("sath.restore_ges", icon="FILE_REFRESH")
        obj = context.active_object
        if obj is None or not obj.ges.kind:
            return
        box = lay.box()
        box.label(text=f"{KIND_LABEL.get(obj.ges.kind, obj.ges.kind)}: {obj.name}", icon="MOD_BUILD")
        if obj.ges.inferred:
            col = box.column(align=True)
            col.label(text="O'lchamlar taxminiy — geometriya IFC dan olingan", icon="ERROR")
            if obj.ges.geom_dirty:
                col.label(text="O'lchamlar o'zgardi — mesh tasdiqlanguncha eski")
            col.operator("sath.confirm_dimensions", icon="CHECKMARK")
        for p in obj.ges.params:
            row = box.row()
            if p.ptype == "enum":
                row.prop(p, "value_enum", text=p.label)
            elif p.ptype == "int":
                row.prop(p, "value_int", text=p.label)
            else:
                row.prop(p, "value_float", text=p.label + (", m" if p.ptype == "length" else ""))
        box.operator("sath.rebuild_object", icon="FILE_REFRESH")


CLASSES = (
    GesParam,
    GesObject,
    SATH_OT_add_object,
    SATH_OT_rebuild_object,
    SATH_OT_confirm_dimensions,
    SATH_OT_sync_ifc,
    SATH_OT_purge_orphans,
    SATH_OT_restore_ges,
    SATH_PT_objects,
)


_off_loaded = None


def register():
    global _off_loaded
    if os.environ.get("SATH_PANELS_OPEN"):  # GUI sinovi (ui.py bilan bir xil)
        SATH_PT_objects.bl_category = "Item"
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)
    _off_loaded = events.subscribe("ifc.loaded", _on_ifc_loaded)


def unregister():
    global _off_loaded
    if _off_loaded is not None:
        _off_loaded()
        _off_loaded = None
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
