from sqlalchemy.orm import Session

from .orm import AuditLog


def log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    project_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Audit yozuvi qo'shadi; commit chaqiruvchi zimmasida."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            detail=detail or {},
        )
    )
