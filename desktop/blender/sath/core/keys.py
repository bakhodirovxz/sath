"""Sath klaviatura yorliqlari (spec §5). Yadro (ui.py: Ctrl+Shift+G → «Sath» menyusi) va modullar
(api.ui.keymap) shu modul orqali qo'shadi — ITEMS ro'yxati bo'yicha headless `keymap` sinovi Blender standart
keymapi va Bonsai yorliqlari bilan to'qnashuvni tekshiradi. conflicts() va boshqalar — bpy siz (pytest)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NamedTuple


class Chord(NamedTuple):
    keymap: str
    type: str
    value: str
    ctrl: int  # 0 | 1 | -1 (ixtiyoriy — Blender KM_ANY)
    shift: int
    alt: int
    oskey: int
    idname: str
    owner: str  # "sath:<egasi>" | "blender" | "addon"
    menu: str = ""  # wm.call_menu / call_panel nomi


# 3D ko'rinishda bir vaqtda ishlaydigan keymaplar. Rejim keymaplari («Object Mode», «Mesh» …) «3D View» dan
# OLDIN ishlov beradi — shu yerdagi bir xil chord Sath yorlig'ini yopadi (yoki aksincha).
VIEW3D_KEYMAPS = frozenset({
    "Window", "Screen", "Frames", "User Interface", "3D View Generic", "3D View", "Object Mode",
    "Object Non-modal", "Mesh", "Curve", "Curves", "Armature", "Pose", "Metaball", "Lattice", "Font",
    "Point Cloud", "Particle", "Sculpt", "Weight Paint", "Vertex Paint", "Image Paint", "Grease Pencil",
    "Grease Pencil Edit Mode",
})  # fmt: skip
GLOBAL_KEYMAPS = frozenset({"Window", "Screen"})
# Ataylab ustun qo'yilgan: (keymap, boshqa amal) → sabab. Addon elementi o'sha keymap boshiga qo'shiladi.
ALLOWED = {
    ("Object Mode", "collection.objects_add_active"): (
        "Ctrl+Shift+G — Sath menyusi (spec §5: saqlanadi); «faol obyektni kolleksiyaga qo'shish» "
        "Object → Collection menyusida qoladi"
    ),
}
_VALUES = frozenset({"PRESS", "CLICK", "ANY"})  # bir bosishda birga ishlaydigan qiymatlar
_CALLS = frozenset({"wm.call_menu", "wm.call_menu_pie", "wm.call_panel"})
ITEMS: list[tuple[str, object, object]] = []  # (egasi, keymap, keymap_item) — faol Sath yorliqlari


def add(owner: str, idname: str, key: str, *, km_name: str = "3D View", space_type: str = "VIEW_3D",
        ctrl: bool = False, shift: bool = False, alt: bool = False,
        **properties) -> tuple[object | None, Callable[[], None]]:  # fmt: skip
    """Addon keyconfig ga yorliq; qaytaradi (kmi, off). Keyconfig yo'q bo'lsa — (None, hech narsa)."""
    import bpy

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return None, lambda: None
    km = kc.keymaps.new(name=km_name, space_type=space_type)
    kmi = km.keymap_items.new(idname, key, "PRESS", ctrl=ctrl, shift=shift, alt=alt)
    for k, v in properties.items():
        setattr(kmi.properties, k, v)
    entry = (owner, km, kmi)
    ITEMS.append(entry)

    def off() -> None:
        for i, e in enumerate(ITEMS):
            if e is entry:
                del ITEMS[i]
                km.keymap_items.remove(kmi)
                return

    return kmi, off


def chord(kmi, keymap: str, owner: str) -> Chord:
    any_ = bool(getattr(kmi, "any", False))

    def m(v) -> int:
        return -1 if any_ else int(v)

    menu = getattr(kmi.properties, "name", "") if kmi.idname in _CALLS else ""
    return Chord(keymap, kmi.type, kmi.value, m(kmi.ctrl), m(kmi.shift), m(kmi.alt), m(kmi.oskey),
                 kmi.idname, owner, menu)  # fmt: skip


def chord_from_event(keymap: str, idname: str, event: dict, props: dict | None,
                     owner: str = "blender") -> Chord:  # fmt: skip
    """blender_default.generate_keymaps() elementi (idname, event, props) → Chord."""
    any_ = bool(event.get("any"))

    def m(k: str) -> int:
        v = event.get(k)
        return -1 if any_ or v == -1 else int(bool(v))

    menu = ""
    if props and idname in _CALLS:
        menu = dict(props.get("properties", ())).get("name", "")
    return Chord(keymap, event["type"], event.get("value", "PRESS"), m("ctrl"), m("shift"), m("alt"),
                 m("oskey"), idname, owner, menu)  # fmt: skip


def _mod(a: int, b: int) -> bool:
    return a == b or a == -1 or b == -1


def overlaps(a: Chord, b: Chord) -> bool:
    return (
        a.type == b.type and a.value in _VALUES and b.value in _VALUES
        and _mod(a.ctrl, b.ctrl) and _mod(a.shift, b.shift) and _mod(a.alt, b.alt) and _mod(a.oskey, b.oskey)
    )  # fmt: skip


def scope(keymap: str) -> frozenset[str]:
    return VIEW3D_KEYMAPS if keymap in VIEW3D_KEYMAPS else GLOBAL_KEYMAPS | {keymap}


def text(c: Chord) -> str:
    mods = [n for n, v in (("Ctrl", c.ctrl), ("Shift", c.shift), ("Alt", c.alt), ("OS", c.oskey)) if v == 1]
    return "+".join([*mods, c.type])


def _label(c: Chord) -> str:
    return f"{c.owner} «{c.keymap}» {text(c)} {c.idname}" + (f" ({c.menu})" if c.menu else "")


def conflicts(ours: Iterable[Chord], others: Iterable[Chord], allowed: dict | None = None) -> list[str]:
    """Sath yorliqlari to'qnashuvlari (bo'sh — yaxshi): boshqalar bilan (Sath yorlig'i keymapining ta'sir
    doirasida) va Sath ichida (turli amal — bir chord). allowed — ataylab ustun qo'yilganlar."""
    allowed = ALLOWED if allowed is None else allowed
    ours, others = list(ours), list(others)
    out = []
    for s in ours:
        sc = scope(s.keymap)
        for o in others:
            if o.keymap in sc and overlaps(s, o) and (o.keymap, o.idname) not in allowed:
                out.append(f"{_label(s)}  <->  {_label(o)}")
    for i, a in enumerate(ours):
        for b in ours[i + 1 :]:
            if b.keymap in scope(a.keymap) and overlaps(a, b) and (a.idname, a.menu) != (b.idname, b.menu):
                out.append(f"{_label(a)}  <->  {_label(b)}")
    return out
