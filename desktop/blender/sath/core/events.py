"""Hodisalar shinasi (asosiy oqim): modullar bir-birini import qilmasdan xabar almashadi.

Mavzular: session.login {user}, session.logout {}, project.changed {project_id}, ifc.loaded {path}, scada.snapshot {data},
task.done|task.failed|task.cancelled {id, key, title}.

project.changed — loyihalar ro'yxatida tanlov o'zgarganda (projects_index update, kirilgan holatda); props.restore()
ham projects_index ni qayta o'rnatadi, shuning uchun Bonsai yangi sessiyasidan keyingi tiklashda (open_version,
pull_head) ham — o'sha loyiha bilan — keladi: obunachi takroriy hodisaga chidamli bo'lsin.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable

_subs: dict[str, list[Callable[[dict], None]]] = {}


def subscribe(topic: str, fn: Callable[[dict], None]) -> Callable[[], None]:
    _subs.setdefault(topic, []).append(fn)

    def off() -> None:
        lst = _subs.get(topic, [])
        if fn in lst:
            lst.remove(fn)

    return off


def publish(topic: str, **payload) -> None:
    for fn in list(_subs.get(topic, [])):
        try:
            fn(payload)
        except Exception:  # noqa: BLE001 — bitta obunachi boshqalarni to'xtatmasin
            print(f"[sath] hodisa {topic}: obunachi xatosi", flush=True)
            traceback.print_exc()


def clear() -> None:
    _subs.clear()
