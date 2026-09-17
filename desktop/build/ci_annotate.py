"""pytest junit XML dagi xatolarni GitHub annotatsiyasi (::error::) qilib chiqaradi — loglarsiz ham ko'rinadi.

pytest --junitxml=report.xml ... ; python desktop/build/ci_annotate.py report.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    n = 0
    for tc in root.iter("testcase"):
        for kind in ("failure", "error"):
            el = tc.find(kind)
            if el is None:
                continue
            n += 1
            msg = (el.get("message") or (el.text or "").strip().splitlines()[-1:] or [""])[0]
            msg = str(msg).replace("\n", " ")[:600]
            print(f"::error file={tc.get('file', '')},title={tc.get('classname', '')}.{tc.get('name', '')}::{msg}")
    print(f"{n} ta xato" if n else "hammasi o'tdi")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
