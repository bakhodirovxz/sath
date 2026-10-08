"""O'tish davri psevdo-moduli (spec §1 strangler, A qadam): hali modulga ko'chirilmagan fayllar — o'zgarishsiz va
avvalgi tartibda ro'yxatga olinadi. B qadamda har modul o'z faylini FILES dan oladi; ro'yxatda faqat yadro fayllari
(ops_server, ui) qolganda ular sath/__init__.py ga qaytadi va bu modul o'chiriladi (Task 13)."""

from __future__ import annotations

from ... import (
    demo_plant,
    ges_objects,
    ops_import,
    ops_server,
    ops_twin,
    ui,
)

FILES = [ges_objects, ops_server, ops_twin, demo_plant, ops_import, ui]


def register(api):
    api.adopt("legacy", *FILES)  # o'chirishda unregister() teskari tartibda — avvalgi sath.unregister bilan bir xil
