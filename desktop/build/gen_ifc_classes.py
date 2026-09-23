"""common/sath_common/ifc_classes.py ni ifcopenshell sxemasidan qayta generatsiya qiladi (G1).
python desktop/build/gen_ifc_classes.py  (server .venv da); keyin sync_blender.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from ges_server.models import ifc_schema  # noqa: E402

OUT = ROOT / "common" / "sath_common" / "ifc_classes.py"  # kanonik manba (CODE-01)


def main() -> None:
    src = OUT.read_text(encoding="utf-8")
    head = src.split("IFC4 = frozenset((")[0]
    tail = "SCHEMAS = {" + src.split("SCHEMAS = {", 1)[1]
    body = ""
    for sc in ifc_schema.SCHEMAS:
        names = "".join(f'    "{n}",\n' for n in sorted(ifc_schema.element_classes(sc)))
        body += f"{sc} = frozenset((\n{names}))\n\n"
    OUT.write_text(head + body + tail, encoding="utf-8", newline="\n")
    print("yozildi:", OUT)


if __name__ == "__main__":
    main()
