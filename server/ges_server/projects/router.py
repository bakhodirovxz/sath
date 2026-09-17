from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, AdminUser, CurrentUser, get_project_role, require_project_role
from ..orm import Project, ProjectMember, Role, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    location: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    location: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    location: str
    my_role: Role | None = None
    model_count: int = 0

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


def _out(db, project: Project, user: User) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        location=project.location,
        my_role=get_project_role(db, project.id, user),
        model_count=len(project.models),
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(user: CurrentUser, db: DB):
    """Admin hammasini, boshqalar faqat a'zo bo'lgan loyihalarni ko'radi."""
    q = db.query(Project)
    if not user.is_admin:
        q = q.join(ProjectMember).filter(ProjectMember.user_id == user.id)
    return [_out(db, p, user) for p in q.order_by(Project.name).all()]


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
def list_members(project: ViewerProject):
    return [
        MemberOut(
            user_id=m.user_id, username=m.user.username, full_name=m.user.full_name, role=m.role
        )
        for m in project.members
    ]


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
        member = ProjectMember(project_id=project.id, user_id=body.user_id)
        db.add(member)
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
