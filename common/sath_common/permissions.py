"""Loyiha rollari ruxsatlari — server `ges_server/auth/deps.py::ROLE_PERMISSIONS` ning ko'zgusi (FEAT-ROLE, P3).

Desktop ruxsatlarni serverdan oladi (`ProjectOut.permissions`); eski server bu maydonni yubormasa shu xarita
ishlatiladi. Tenglik `server/tests/test_permissions_mirror.py` da tekshiriladi. Nusxa:
desktop/blender/sath/shared/permissions.py (`python desktop/build/sync_blender.py`) — nusxani qo'lda tahrirlamang.
Python 3.10 mos, bog'liqliksiz.
"""

from __future__ import annotations

PROJECT_READ = "project.read"
SCADA_READ = "scada.read"
SCADA_ACK = "scada.ack"
SCADA_COMMAND = "scada.command"
SCADA_COMMAND_APPROVE = "scada.command.approve"
SCADA_INTERLOCK_OVERRIDE = "scada.interlock.override"
SCADA_MANUAL_ENTRY = "scada.manual_entry"
SENSOR_CONFIGURE = "sensor.configure"
MODEL_WRITE = "model.write"
VERSION_RESTORE = "version.restore"
CR_CREATE = "cr.create"
CR_REVIEW = "cr.review"
CR_APPROVE = "cr.approve"
CR_MERGE = "cr.merge"
ISSUE_WRITE = "issue.write"
SIM_RUN = "sim.run"
SIM_CFD = "sim.cfd"
MEMBER_MANAGE = "member.manage"
AUDIT_READ = "audit.read"
GATEWAY_KEYS = "gateway.keys"

_VIEW = frozenset({PROJECT_READ, SCADA_READ})
_OPERATE = _VIEW | {SCADA_ACK, SCADA_COMMAND}
_DESIGN = _VIEW | {SCADA_ACK, MODEL_WRITE, CR_CREATE, ISSUE_WRITE, SIM_RUN, SIM_CFD, SENSOR_CONFIGURE}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": _VIEW,
    "operator": frozenset(_OPERATE),
    "shift_supervisor": frozenset(_OPERATE | {SCADA_COMMAND_APPROVE, SCADA_INTERLOCK_OVERRIDE, SCADA_MANUAL_ENTRY}),
    "engineer": frozenset(_DESIGN),
    "approver": frozenset(
        _DESIGN | {VERSION_RESTORE, CR_REVIEW, CR_APPROVE, CR_MERGE, MEMBER_MANAGE, AUDIT_READ, GATEWAY_KEYS}
    ),
}

ALL: frozenset[str] = frozenset().union(*ROLE_PERMISSIONS.values())


def role_permissions(role: str | None) -> frozenset[str]:
    """Rol nomi bo'yicha ruxsatlar; noma'lum yoki yo'q rol — bo'sh to'plam."""
    return ROLE_PERMISSIONS.get(role or "", frozenset())
