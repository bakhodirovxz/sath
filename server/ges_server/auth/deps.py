"""FastAPI dependency lar: joriy foydalanuvchi, admin, loyiha roli tekshiruvi."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..orm import Project, ProjectMember, Role, User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Rol ierarxiyasi: yuqori rol quyi rolning hamma huquqiga ega
_ROLE_RANK = {Role.viewer: 0, Role.operator: 1, Role.engineer: 2, Role.approver: 3}

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
    return actual is not None and _ROLE_RANK[actual] >= _ROLE_RANK[required]


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
