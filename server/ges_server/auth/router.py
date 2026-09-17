from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .. import audit
from ..orm import User
from .deps import DB, AdminUser, CurrentUser
from .security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    email: str = ""
    is_admin: bool
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=4)
    full_name: str = ""
    email: str = ""
    is_admin: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = Field(default=None, min_length=4)
    is_admin: bool | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4)


@router.post("/auth/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    user = db.query(User).filter_by(username=form.username).one_or_none()
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login yoki parol noto'g'ri")
    audit.log(db, user_id=user.id, action="login", target_type="user", target_id=user.id)
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(body: PasswordChange, user: CurrentUser, db: DB):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eski parol noto'g'ri")
    user.password_hash = hash_password(body.new_password)
    db.commit()


# --- Admin: foydalanuvchilar boshqaruvi ---


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DB):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, admin: AdminUser, db: DB):
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Bunday login mavjud")
    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
    )
    db.add(user)
    db.flush()
    audit.log(db, user_id=admin.id, action="user.create", target_type="user", target_id=user.id)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, admin: AdminUser, db: DB):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None:
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.is_admin is not None:
        if user.id == admin.id and not body.is_admin:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "O'zingizdan admin huquqini ololmaysiz"
            )
        user.is_admin = body.is_admin
    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "O'zingizni o'chira olmaysiz")
        user.is_active = body.is_active
    audit.log(
        db,
        user_id=admin.id,
        action="user.update",
        target_type="user",
        target_id=user.id,
        detail=body.model_dump(exclude_none=True, exclude={"password"}),
    )
    db.commit()
    return user
