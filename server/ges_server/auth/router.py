from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .. import audit
from ..config import get_settings
from ..orm import User
from ..ratelimit import LoginLimit
from . import totp
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
    mfa_enabled: bool = False
    locked_until: datetime | None = None

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    # Administrator uchun MFA majburiy, lekin hali yoqilmagan — interfeys sozlashni taklif qiladi
    mfa_required: bool = False


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
    # Admin: foydalanuvchining MFA sini bekor qilish (telefon yo'qolganda) / blokni ochish
    mfa_reset: bool = False
    unlock: bool = False


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4)


def _login_failed(db, user: User | None, username: str, reason: str) -> None:
    """Noto'g'ri urinish: audit (darhol) + hisob hisoblagichi; chegarada bloklash (L1)."""
    settings = get_settings()
    locked = False
    if user is not None:
        user.failed_logins = (user.failed_logins or 0) + 1
        if settings.login_max_failures > 0 and user.failed_logins >= settings.login_max_failures:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_logins = 0
            locked = True
        db.commit()
    audit.log_now(
        user_id=user.id if user else None,
        action="auth.account_locked" if locked else "auth.login_failed",
        target_type="user",
        target_id=user.id if user else None,
        detail={"username": username[:64], "reason": reason, "inactive": bool(user and not user.is_active)},
    )


def _lock_remaining(user: User) -> int:
    """Blok tugashigacha soniya (0 — bloklanmagan)."""
    if user.locked_until is None:
        return 0
    until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
    return max(0, int((until - datetime.now(timezone.utc)).total_seconds()))


@router.post("/auth/login", response_model=Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DB,
    _: LoginLimit,
    otp: Annotated[str | None, Form(description="TOTP kodi (MFA yoqilgan bo'lsa)")] = None,
):
    """Kirish. IP bo'yicha tezlik cheklovi (429), hisob bo'yicha bloklash (423, `login_max_failures`),
    MFA yoqilgan hisobda `otp` majburiy (bo'lmasa 401 + `X-MFA-Required: 1`)."""
    user = db.query(User).filter_by(username=form.username).one_or_none()
    if user is not None and (remaining := _lock_remaining(user)) > 0:
        audit.log_now(
            user_id=user.id, action="auth.login_locked", target_type="user", target_id=user.id,
            detail={"username": form.username[:64], "remaining_s": remaining},
        )
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Hisob vaqtincha bloklangan ({-(-remaining // 60)} daqiqa). Administratorga murojaat qiling",
            headers={"Retry-After": str(remaining)},
        )
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        _login_failed(db, user, form.username, "password")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login yoki parol noto'g'ri")
    if user.mfa_enabled:
        if not otp:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA kodi kerak", headers={"X-MFA-Required": "1"})
        counter = totp.verify(user.mfa_secret or "", otp, last_counter=user.mfa_last_counter)
        if counter is None:
            _login_failed(db, user, form.username, "otp")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA kodi noto'g'ri", headers={"X-MFA-Required": "1"})
        user.mfa_last_counter = counter
    user.failed_logins = 0
    user.locked_until = None
    audit.log(db, user_id=user.id, action="login", target_type="user", target_id=user.id, detail={"mfa": user.mfa_enabled})
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/auth/me", response_model=MeOut)
def me(user: CurrentUser):
    out = MeOut.model_validate(user)
    out.mfa_required = bool(user.is_admin and get_settings().mfa_required_for_admins and not user.mfa_enabled)
    return out


# --- MFA (TOTP, RFC 6238) ---


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_url: str


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisable(MfaCode):
    password: str


@router.post("/auth/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(user: CurrentUser, db: DB):
    """Yangi TOTP kaliti (hali yoqilmagan): ilovaga kiritib, `enable` da kod bilan tasdiqlanadi."""
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA allaqachon yoqilgan; avval o'chiring")
    user.mfa_secret = totp.new_secret()
    user.mfa_last_counter = None
    db.commit()
    return MfaSetupOut(secret=user.mfa_secret, otpauth_url=totp.otpauth_url(user.mfa_secret, user.username, get_settings().app_name))


@router.post("/auth/mfa/enable", status_code=204)
def mfa_enable(body: MfaCode, user: CurrentUser, db: DB):
    if user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avval /auth/mfa/setup")
    counter = totp.verify(user.mfa_secret, body.code)
    if counter is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kod noto'g'ri — ilovadagi vaqtni tekshiring")
    user.mfa_enabled = True
    user.mfa_last_counter = counter
    audit.log(db, user_id=user.id, action="auth.mfa_enabled", target_type="user", target_id=user.id)
    db.commit()


@router.post("/auth/mfa/disable", status_code=204)
def mfa_disable(body: MfaDisable, user: CurrentUser, db: DB):
    """O'chirish — parol va joriy kod bilan (o'g'irlangan sessiya MFA ni o'chira olmasin)."""
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA yoqilmagan")
    if not verify_password(body.password, user.password_hash) or totp.verify(user.mfa_secret or "", body.code, last_counter=user.mfa_last_counter) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Parol yoki kod noto'g'ri")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_last_counter = None
    audit.log(db, user_id=user.id, action="auth.mfa_disabled", target_type="user", target_id=user.id)
    db.commit()


@router.post("/auth/change-password", status_code=204)
def change_password(body: PasswordChange, user: CurrentUser, db: DB):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eski parol noto'g'ri")
    user.password_hash = hash_password(body.new_password)
    audit.log(
        db, user_id=user.id, action="auth.password_changed", target_type="user", target_id=user.id
    )
    db.commit()


# --- Admin: foydalanuvchilar boshqaruvi ---


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: AdminUser,
    db: DB,
    limit: int = Query(500, gt=0, le=5000),
    after_id: int | None = None,
    q: str | None = None,
):
    """Foydalanuvchilar: `limit` + kursor `after_id` (id tartibi), `q` — login/ism bo'yicha qidiruv."""
    base = db.query(User)
    if q:
        base = base.filter((User.username.ilike(f"%{q}%")) | (User.full_name.ilike(f"%{q}%")))
    if after_id is not None:
        return base.filter(User.id > after_id).order_by(User.id).limit(limit).all()
    return base.order_by(User.username, User.id).limit(limit).all()


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
    if body.mfa_reset:
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_last_counter = None
    if body.unlock:
        user.locked_until = None
        user.failed_logins = 0
    audit.log(
        db,
        user_id=admin.id,
        action="user.update",
        target_type="user",
        target_id=user.id,
        detail={
            **body.model_dump(exclude_none=True, exclude={"password"}, exclude_defaults=True),
            **({"password_changed": True} if body.password is not None else {}),
        },
    )
    db.commit()
    return user
