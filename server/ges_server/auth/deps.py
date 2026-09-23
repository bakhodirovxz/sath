"""FastAPI dependency lar: joriy foydalanuvchi, admin, loyiha roli va ruxsat (permission) tekshiruvi."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..orm import Project, ProjectMember, Role, User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Rollar qisman tartibi (eski `require_project_role` endpointlari uchun): rol o'zini va shu to'plamdagi
# rollarni "qoplaydi". Smena boshlig'i dispetcherni qoplaydi, lekin muhandisni emas (va aksincha).
_ROLE_IMPLIES: dict[Role, frozenset[Role]] = {
    Role.viewer: frozenset({Role.viewer}),
    Role.operator: frozenset({Role.viewer, Role.operator}),
    Role.shift_supervisor: frozenset({Role.viewer, Role.operator, Role.shift_supervisor}),
    Role.engineer: frozenset({Role.viewer, Role.operator, Role.engineer}),
    Role.approver: frozenset({Role.viewer, Role.operator, Role.engineer, Role.approver}),
}

# ---------- Ruxsatlar (FEAT-ROLE yadrosi, SCADA-01) ----------
# Loyihalash va ekspluatatsiya ruxsatlari kesishmaydi: buyruq (scada.command*) faqat dispetcher va smena
# boshlig'ida; nuqtani boshqaruvga ochish/manzil/chegaralar (sensor.configure) — faqat muhandis/tasdiqlovchida.
P_PROJECT_READ = "project.read"
P_SCADA_READ = "scada.read"
P_SCADA_ACK = "scada.ack"  # alarm kvitlash (eski ierarxiya bo'yicha muhandis ham kvitlay oladi)
P_SCADA_COMMAND = "scada.command"  # select/execute/cancel
P_SCADA_COMMAND_APPROVE = "scada.command.approve"  # ikki kishi qoidasida ikkinchi imzo
P_SCADA_INTERLOCK_OVERRIDE = "scada.interlock.override"  # blokirovkani chetlab o'tish (sabab + audit)
P_SCADA_MANUAL_ENTRY = "scada.manual_entry"  # qo'lda o'lchov / CSV import (source=manual)
P_SENSOR_CONFIGURE = "sensor.configure"  # writable, address, buyruq chegaralari, interlock
P_MODEL_WRITE = "model.write"
P_VERSION_RESTORE = "version.restore"
P_CR_CREATE = "cr.create"
P_CR_REVIEW = "cr.review"
P_CR_APPROVE = "cr.approve"
P_CR_MERGE = "cr.merge"
P_ISSUE_WRITE = "issue.write"
P_SIM_RUN = "sim.run"
P_SIM_CFD = "sim.cfd"
P_MEMBER_MANAGE = "member.manage"
P_AUDIT_READ = "audit.read"
P_GATEWAY_KEYS = "gateway.keys"  # gateway ingest/command kalitlarini yaratish/almashtirish

_VIEW = frozenset({P_PROJECT_READ, P_SCADA_READ})
_OPERATE = _VIEW | {P_SCADA_ACK, P_SCADA_COMMAND}
_DESIGN = _VIEW | {
    P_SCADA_ACK,
    P_MODEL_WRITE,
    P_CR_CREATE,
    P_ISSUE_WRITE,
    P_SIM_RUN,
    P_SIM_CFD,
    P_SENSOR_CONFIGURE,
}
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.viewer: _VIEW,
    Role.operator: frozenset(_OPERATE),
    Role.shift_supervisor: frozenset(
        _OPERATE | {P_SCADA_COMMAND_APPROVE, P_SCADA_INTERLOCK_OVERRIDE, P_SCADA_MANUAL_ENTRY}
    ),
    Role.engineer: frozenset(_DESIGN),
    Role.approver: frozenset(
        _DESIGN
        | {P_VERSION_RESTORE, P_CR_REVIEW, P_CR_APPROVE, P_CR_MERGE, P_MEMBER_MANAGE, P_AUDIT_READ, P_GATEWAY_KEYS}
    ),
}

# Parolni majburiy almashtirish rejimida ruxsat etilgan yo'llar (L2)
_MUST_CHANGE_ALLOW = ("/api/auth/me", "/api/auth/change-password", "/api/auth/logout", "/api/auth/mfa/", "/api/auth/sessions")


def user_from_token(db: Session, token: str, scope: str = "session") -> User | None:
    """To'liq tekshiruv (L2): imzo/muddat/iss/aud/scope, foydalanuvchi faol, token versiyasi mos
    (parol/rol o'zgarganda barcha eski tokenlar yaroqsiz)."""
    p = decode_token(token, scope)
    if p is None:
        return None
    user = db.get(User, p["sub"])
    if user is None or not user.is_active or p.get("ver", 0) != (user.token_version or 0):
        return None
    return user


def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token yaroqsiz yoki foydalanuvchi faol emas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.must_change_password and not request.url.path.startswith(_MUST_CHANGE_ALLOW):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Parolni almashtirish shart (Profil → Parol)",
            headers={"X-Password-Change-Required": "1"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat administrator uchun")
    if get_settings().mfa_required_for_admins and not user.mfa_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Administrator uchun ikki bosqichli kirish (MFA) yoqilishi shart — Profil → MFA"
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_project_role(db: Session, project_id: int, user: User) -> Role | None:
    """Foydalanuvchining loyihadagi roli. Admin hamma loyihada approver."""
    if user.is_admin:
        return Role.approver
    member = db.query(ProjectMember).filter_by(project_id=project_id, user_id=user.id).one_or_none()
    return member.role if member else None


def has_role(actual: Role | None, required: Role) -> bool:
    return actual is not None and required in _ROLE_IMPLIES[actual]


def role_permissions(role: Role | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset()) if role is not None else frozenset()


def has_permission(db: Session, project_id: int, user: User, perm: str) -> bool:
    """Admin loyihada tasdiqlovchi ruxsatlariga ega (buyruq yubora olmaydi — SCADA-01)."""
    return perm in role_permissions(get_project_role(db, project_id, user))


def require_project_role(required: Role):
    """`project_id` path parametrli endpointlar uchun dependency fabrikasi."""

    def _dep(project_id: int, user: CurrentUser, db: DB) -> Project:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
        if not has_role(get_project_role(db, project_id, user), required):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")
        return project

    return _dep


def check_project_role(db: Session, project_id: int, user: User, required: Role) -> None:
    """Path da project_id bo'lmagan hollarda (model_id, version_id) qo'lda tekshirish."""
    if not has_role(get_project_role(db, project_id, user), required):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")


def require_project_permission(perm: str):
    """`project_id` path parametrli endpointlar uchun: ruxsat bo'lmasa 403 (FEAT-ROLE)."""

    def _dep(project_id: int, user: CurrentUser, db: DB) -> Project:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
        if not has_permission(db, project_id, user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Bu loyihada ruxsat yo'q ({perm})")
        return project

    return _dep


def check_project_permission(db: Session, project_id: int, user: User, perm: str) -> None:
    if not has_permission(db, project_id, user, perm):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Bu loyihada ruxsat yo'q ({perm})")


def member_ids_with_permission(
    db: Session, project_id: int, perm: str, exclude: int | None = None
) -> list[int]:
    """Loyihaning shu ruxsatga ega faol a'zolari (bildirishnoma qabul qiluvchilari)."""
    rows = db.query(ProjectMember).filter_by(project_id=project_id).all()
    return sorted(
        {
            m.user_id
            for m in rows
            if m.user.is_active and m.user_id != exclude and perm in role_permissions(m.role)
        }
    )
