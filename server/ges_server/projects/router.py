from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import audit
from ..auth import sessions
from ..auth.deps import DB, AdminUser, CurrentUser, get_project_role, has_role, require_project_role
from ..orm import Model, Project, ProjectMember, Role, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    location: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    location: str | None = None
    ids_required: bool | None = None  # G2: IDS yiqilgan versiya tasdiqlanmaydi


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    location: str
    my_role: Role | None = None
    model_count: int = 0
    ids_required: bool = False

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    user_id: int
    username: str
    full_name: str
    role: Role


class MemberSet(BaseModel):
    user_id: int
    role: Role


ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
ApproverProject = Annotated[Project, Depends(require_project_role(Role.approver))]


def _out(db, project: Project, user: User, role: Role | None = None, model_count: int | None = None) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        location=project.location,
        my_role=role if model_count is not None else get_project_role(db, project.id, user),
        model_count=model_count if model_count is not None else len(project.models),
        ids_required=bool(project.ids_required),
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user: CurrentUser,
    db: DB,
    limit: int = Query(500, gt=0, le=5000),
    after_id: int | None = None,
    q: str | None = None,
):
    """Admin hammasini, boshqalar faqat a'zo bo'lgan loyihalarni ko'radi. So'rovlar soni loyihalar
    sonidan mustaqil (D4): rollar va model soni ikkita agregat so'rov bilan. Kursor: `after_id`
    (id bo'yicha tartib), `q` — nom bo'yicha qidiruv."""
    base = db.query(Project)
    if not user.is_admin:
        base = base.join(ProjectMember).filter(ProjectMember.user_id == user.id)
    if q:
        base = base.filter(Project.name.ilike(f"%{q}%"))
    if after_id is not None:
        base = base.filter(Project.id > after_id).order_by(Project.id)
    else:
        base = base.order_by(Project.name, Project.id)
    projects = base.limit(limit).all()
    ids = [p.id for p in projects]
    if not ids:
        return []
    counts = dict(
        db.query(Model.project_id, func.count(Model.id)).filter(Model.project_id.in_(ids)).group_by(Model.project_id).all()
    )
    if user.is_admin:
        roles = {pid: Role.approver for pid in ids}
    else:
        roles = dict(
            db.query(ProjectMember.project_id, ProjectMember.role)
            .filter(ProjectMember.user_id == user.id, ProjectMember.project_id.in_(ids))
            .all()
        )
    return [_out(db, p, user, roles.get(p.id), counts.get(p.id, 0)) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, admin: AdminUser, db: DB):
    if db.query(Project).filter_by(name=body.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Bunday nomli loyiha mavjud")
    project = Project(**body.model_dump(), created_by=admin.id)
    db.add(project)
    db.flush()
    audit.log(
        db,
        user_id=admin.id,
        action="project.create",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
    )
    db.commit()
    return _out(db, project, admin)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: ViewerProject, user: CurrentUser, db: DB):
    return _out(db, project, user)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(body: ProjectUpdate, project: ApproverProject, user: CurrentUser, db: DB):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(project, k, v)
    audit.log(
        db,
        user_id=user.id,
        action="project.update",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail=body.model_dump(exclude_none=True),
    )
    db.commit()
    return _out(db, project, user)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, admin: AdminUser, db: DB):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    audit.log(
        db,
        user_id=admin.id,
        action="project.delete",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"name": project.name},
    )
    db.delete(project)
    db.commit()


# --- A'zolar ---


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(project: ViewerProject, db: DB, limit: int = Query(500, gt=0, le=5000), after_id: int | None = None):
    """A'zolar (bitta JOIN so'rov, N+1 yo'q); kursor `after_id` — user_id bo'yicha."""
    q = (
        db.query(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .filter(ProjectMember.project_id == project.id)
    )
    if after_id is not None:
        q = q.filter(ProjectMember.user_id > after_id)
    rows = q.order_by(ProjectMember.user_id).limit(limit).all()
    return [MemberOut(user_id=m.user_id, username=u.username, full_name=u.full_name, role=m.role) for m, u in rows]


@router.put("/{project_id}/members", response_model=MemberOut)
def set_member(body: MemberSet, project: ApproverProject, user: CurrentUser, db: DB):
    """A'zo qo'shish yoki rolini o'zgartirish."""
    target = db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    member = (
        db.query(ProjectMember).filter_by(project_id=project.id, user_id=body.user_id).one_or_none()
    )
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=body.user_id, role=body.role)
        db.add(member)
    elif not has_role(body.role, member.role) and not target.is_admin:
        # L2: rol pasaytirildi — ochiq WS/tokenlar eski huquq bilan qolmasin (ko'tarilganda shart emas)
        sessions.revoke_all(db, target.id, reason="role_change")
    member.role = body.role
    audit.log(
        db,
        user_id=user.id,
        action="project.member.set",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"user_id": body.user_id, "role": body.role.value},
    )
    db.commit()
    return MemberOut(
        user_id=target.id, username=target.username, full_name=target.full_name, role=member.role
    )


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(user_id: int, project: ApproverProject, user: CurrentUser, db: DB):
    member = db.query(ProjectMember).filter_by(project_id=project.id, user_id=user_id).one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "A'zo topilmadi")
    db.delete(member)
    sessions.revoke_all(db, user_id, reason="member_removed")
    audit.log(
        db,
        user_id=user.id,
        action="project.member.remove",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"user_id": user_id},
    )
    db.commit()
