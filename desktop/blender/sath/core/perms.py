"""Rolga sezgir UI (spec §2): faol loyihadagi ruxsatlar. Manba — server `ProjectOut.permissions` (loyiha qatorining
`perms` maydoni); bo'sh bo'lsa (eski server) `shared/permissions.py` — server ROLE_PERMISSIONS ko'zgusi. Loyiha
ro'yxatda bo'lmasa (masalan skript s.project_id ni o'zi qo'ygan) — fonda `GET /api/projects/{id}`: javob yoki 403/404
(loyihada roli yo'q) keshlanadi; tarmoq/server xatosi keshlanmaydi — RETRY_S dan keyin qayta so'raladi.
Haqiqiy tekshiruv baribir serverda; bu faqat UI: panel yashiriladi, operator sababi bilan kulrang.

Faol loyiha: ochiq model loyihasi (`scene.ges.project_id`), bo'lmasa ro'yxatda tanlangani. bpy siz import qilinadi.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

from ..shared.permissions import role_permissions

_memo: dict[tuple[str, str], frozenset[str]] = {}
_fetched: dict[int, tuple[str, frozenset[str]]] = {}
_pending: set[int] = set()
_retry_at: dict[int, float] = {}  # vaqtinchalik xato: shu vaqtgacha (monotonic) qayta so'ralmaydi
_NONE: tuple[str, frozenset[str]] = ("", frozenset())
RETRY_S = 5.0  # tarmoq xatosidan keyin qayta urinish oralig'i (har chizishda so'rov yog'ilmasin)
_FINAL = (403, 404)  # loyihada roli yo'q / loyiha yo'q — javob shu, keshlanadi


def resolve(role: str | None, server_perms: Iterable[str] | None) -> frozenset[str]:
    """Server ro'yxati bo'lsa — o'sha; yo'q bo'lsa (eski server) rol bo'yicha zaxira xarita."""
    if server_perms is not None:
        return frozenset(server_perms)
    return role_permissions(role)


def clear() -> None:
    """Sessiya almashganda (session.login/logout): so'rab olingan loyihalar unutiladi."""
    _fetched.clear()
    _pending.clear()
    _retry_at.clear()


def _ges(context):
    if context is None:
        import bpy

        context = bpy.context
    return context.scene.ges


def active_project_id(s) -> int:
    if s.project_id:
        return s.project_id
    i = s.projects_index
    return s.projects[i].item_id if 0 <= i < len(s.projects) else 0


def _entry(s, pid: int) -> tuple[str, frozenset[str]] | None:
    row = next((r for r in s.projects if r.item_id == pid), None)
    if row is not None:
        key = (row.state, row.perms)
        hit = _memo.get(key)
        if hit is None:
            hit = _memo[key] = resolve(row.state or None, row.perms.split() if row.perms else None)
        return row.state, hit
    if pid not in _fetched and time.monotonic() >= _retry_at.get(pid, 0.0):
        _fetch(pid)
    return _fetched.get(pid)


def current(context=None, project_id: int | None = None) -> tuple[str, frozenset[str]]:
    """(rol, ruxsatlar) — kirilmagan yoki loyiha yo'q bo'lsa bo'sh."""
    from .. import session

    if not session.is_logged_in():
        return _NONE
    s = _ges(context)
    pid = project_id if project_id is not None else active_project_id(s)
    if not pid:
        return _NONE
    return _entry(s, pid) or _NONE


def can(perm: str, context=None, project_id: int | None = None) -> bool:
    return perm in current(context, project_id)[1]


def any_of(perms: Iterable[str], context=None, project_id: int | None = None) -> bool:
    have = current(context, project_id)[1]
    return any(p in have for p in perms)


def role(context=None) -> str:
    return current(context)[0]


def require(perm: str, context=None, project_id: int | None = None) -> None:
    if not can(perm, context, project_id):
        raise PermissionError(f"Ruxsat yo'q: {perm}")


def poll(cls, perm: str, context=None, project_id: int | None = None) -> bool:
    """Operator poll uchun: ruxsat bo'lmasa sababi tooltipda («Ruxsat yo'q: cr.approve»)."""
    if can(perm, context, project_id):
        return True
    pid = project_id if project_id is not None else active_project_id(_ges(context))
    cls.poll_message_set(f"Ruxsat yo'q: {perm}" if pid else "Avval loyihani tanlang")
    return False


def _fetch(pid: int) -> None:
    from .. import session
    from .tasks import TASKS

    if pid in _pending or not session.is_logged_in():
        return
    _pending.add(pid)
    client = session.client()

    def same_session() -> bool:
        return session.is_logged_in() and session.client() is client

    def done(d: dict) -> None:
        _pending.discard(pid)
        if same_session():
            _fetched[pid] = (d.get("my_role") or "", resolve(d.get("my_role"), d.get("permissions")))
            _redraw()

    def failed(e: BaseException) -> None:
        _pending.discard(pid)
        if same_session():
            if getattr(e, "status", None) in _FINAL:
                _fetched[pid] = _NONE  # loyihada roli yo'q — qayta so'ralmaydi
            else:  # tarmoq (ServerError status 0) yoki server xatosi: keshlanmaydi, keyingi chizishda qayta urinish
                _retry_at[pid] = time.monotonic() + RETRY_S
            _redraw()

    TASKS.run("Ruxsatlar", lambda ctx: client.project(pid), done, failed, key=f"perms.{pid}", quiet=True, cancellable=False)
    if not TASKS.inline:
        from .ui_tasks import ensure_pump

        ensure_pump()


def _redraw() -> None:
    try:
        import bpy

        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except Exception:  # noqa: BLE001 — pytest (bpy yo'q) yoki oyna yo'q
        pass
