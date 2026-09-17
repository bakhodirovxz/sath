"""Ikki IFC versiya farqi (ifcdiff o'rami). Natija: GUID lar ro'yxati — viewer da rang berish uchun."""

import contextlib
import io
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
from ifcdiff import IfcDiff

# "container" ifcdiff da turli fayl obyektlarini to'g'ridan-to'g'ri solishtiradi (har doim farq) —
# shuning uchun uni o'zimiz GUID bo'yicha tekshiramiz.
RELATIONSHIPS = ["geometry", "attributes", "property"]


def _elements(f: ifcopenshell.file) -> dict[str, ifcopenshell.entity_instance]:
    return {e.GlobalId: e for e in f.by_type("IfcElement") + f.by_type("IfcSpatialElement")}


def _container_guid(e: ifcopenshell.entity_instance) -> str | None:
    c = ifcopenshell.util.element.get_container(e)
    return c.GlobalId if c is not None else None


def compute(old_path: Path, new_path: Path) -> dict:
    old = ifcopenshell.open(str(old_path))
    new = ifcopenshell.open(str(new_path))
    d = IfcDiff(old, new, relationships=RELATIONSHIPS, is_shallow=True)
    with contextlib.redirect_stdout(io.StringIO()):  # ifcdiff print qiladi
        d.diff()

    old_el, new_el = _elements(old), _elements(new)
    register = {g: dict(c) for g, c in d.change_register.items()}
    for guid in new_el.keys() & old_el.keys():
        if _container_guid(old_el[guid]) != _container_guid(new_el[guid]):
            register.setdefault(guid, {})["container_changed"] = True

    def info(guid: str, source: dict) -> dict:
        e = source.get(guid)
        return {"guid": guid, "type": e.is_a() if e else "", "name": (e.Name or "") if e else ""}

    changed = [
        {**info(g, new_el), "changes": sorted(k for k, v in c.items() if v)}
        for g, c in register.items()
    ]
    return {
        "added": sorted((info(g, new_el) for g in d.added_elements), key=lambda x: x["guid"]),
        "deleted": sorted((info(g, old_el) for g in d.deleted_elements), key=lambda x: x["guid"]),
        "changed": sorted(changed, key=lambda x: x["guid"]),
        "summary": {
            "added": len(d.added_elements),
            "deleted": len(d.deleted_elements),
            "changed": len(register),
        },
    }
