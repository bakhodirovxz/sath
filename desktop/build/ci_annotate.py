"""pytest junit XML dagi xatolarni GitHub annotatsiyasi (::error::) qilib chiqaradi — loglarsiz ham ko'rinadi.

pytest --junitxml=report.xml ... ; python desktop/build/ci_annotate.py report.xml
"""

from __future__ import annotations

import sys

try:
    from defusedxml import ElementTree as ET  # XXE dan himoya (server bog'liqligi)
except ImportError:  # noqa: SIM105
    import xml.etree.ElementTree as ET  # noqa: S405 — faqat o'z junit faylimiz


def _clean(text: str) -> str:
    """Workflow-command qiymati: bir qator, `%`/`:` belgilari xavfsiz."""
    out = text.replace("\r", "").replace("\n", " ").replace("%", "%25")
    return out.replace("::", ": :")[:900]


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    n = 0
    for tc in root.iter("testcase"):
        for kind in ("failure", "error"):
            el = tc.find(kind)
            if el is None:
                continue
            n += 1
            lines = (el.text or "").strip().splitlines()
            tail = " | ".join(lines[-6:])  # traceback oxiri (xato joyi va matni)
            title = f"{tc.get('classname', '')}.{tc.get('name', '')}"
            msg = _clean(f"{el.get('message') or ''} || {tail}")
            print(f"::error title={title}::{msg}")
            print(f"XATO {title}: {msg}")
    print(f"{n} ta xato" if n else "hammasi o'tdi")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
