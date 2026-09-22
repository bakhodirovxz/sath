from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .. import audit
from ..config import get_settings
from ..orm import User, UserSession
from ..ratelimit import LoginLimit, client_ip
from . import sessions, totp
from .deps import DB, AdminUser, CurrentUser, oauth2_scheme
from .security import (
    create_access_token,
    decode_token,
    hash_password,
    password_problems,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])

REFRESH_COOKIE = "sath_refresh"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # L2: soniyada; refresh_token — brauzer uchun HttpOnly cookie da ham (JS o'qiy olmaydi), desktop/gateway
    # uchun tanada
    expires_in: int = 0
    refresh_token: str = ""
    must_change_password: bool = False


def _set_refresh_cookie(response: Response, token: str, hours: float) -> None:
    """Refresh token HttpOnly + SameSite=Strict cookie (faqat /api/auth yo'li): XSS o'qiy olmaydi, CSRF
    boshqa saytdan yuborolmaydi; HTTPS da Secure."""
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(hours * 3600),
        httponly=True,
        samesite="strict",
        secure=s.public_url.lower().startswith("https://"),
        path="/api/auth",
    )


def _issue(db, response: Response, user: User, request: Request, client: str) -> Token:
    pair = sessions.open_session(
        db, user, ip=client_ip(request), user_agent=request.headers.get("user-agent", ""), client=client
    )
    _set_refresh_cookie(response, pair.refresh_token, get_settings().refresh_token_hours)
    return Token(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        refresh_token=pair.refresh_token,
        must_change_password=bool(user.must_change_password),
    )


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    email: str = ""
    is_admin: bool
    is_active: bool
    mfa_enabled: bool = False
    locked_until: datetime | None = None
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    # Administrator uchun MFA majburiy, lekin hali yoqilmagan — interfeys sozlashni taklif qiladi
    mfa_required: bool = False


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=128)
    full_name: str = ""
    email: str = ""
    is_admin: bool = False
    # Admin bergan parol birinchi kirishda almashtiriladi (L2); xizmat hisoblari uchun false
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = Field(default=None, min_length=1, max_length=128)
    is_admin: bool | None = None
    is_active: bool | None = None
    # Admin: foydalanuvchining MFA sini bekor qilish (telefon yo'qolganda) / blokni ochish
    mfa_reset: bool = False
    unlock: bool = False


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=1, max_length=128)


def _check_policy(password: str, username: str) -> None:
    problems = password_problems(password, username)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Parol talabga javob bermaydi: " + "; ".join(problems))


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
    request: Request,
    response: Response,
    otp: Annotated[str | None, Form(description="TOTP kodi (MFA yoqilgan bo'lsa)")] = None,
    client: Annotated[str, Form(description="web | desktop | gateway")] = "web",
):
    """Kirish. IP bo'yicha tezlik cheklovi (429), hisob bo'yicha bloklash (423, `login_max_failures`),
    MFA yoqilgan hisobda `otp` majburiy (bo'lmasa 401 + `X-MFA-Required: 1`). Javob: qisqa umrli access
    token + refresh token (cookie va tanada); `must_change_password` — avval parol almashtirish shart."""
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
    audit.log(db, user_id=user.id, action="login", target_type="user", target_id=user.id, detail={"mfa": user.mfa_enabled, "client": client[:16]})
    out = _issue(db, response, user, request, client)
    db.commit()
    return out


class RefreshIn(BaseModel):
    refresh_token: str = ""


@router.post("/auth/refresh", response_model=Token)
def refresh_session(db: DB, request: Request, response: Response, body: RefreshIn | None = None):
    """Refresh token (tanada yoki `sath_refresh` cookie) → yangi access + aylantirilgan refresh token.
    Bekor qilingan/eski token — 401; eski (allaqachon aylantirilgan) token takrori — hamma sessiya bekor."""
    tok = (body.refresh_token if body else "") or request.cookies.get(REFRESH_COOKIE, "")
    if not tok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token yo'q")
    res = sessions.refresh(db, tok)
    if res is None:
        response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessiya tugagan — qayta kiring")
    pair, user = res
    db.commit()
    _set_refresh_cookie(response, pair.refresh_token, get_settings().refresh_token_hours)
    return Token(access_token=pair.access_token, expires_in=pair.expires_in, refresh_token=pair.refresh_token, must_change_password=bool(user.must_change_password))


@router.post("/auth/logout", status_code=204)
def logout(user: CurrentUser, db: DB, response: Response, token: Annotated[str, Depends(oauth2_scheme)]):
    """Joriy sessiyani bekor qiladi (refresh token ishlamaydi; access token muddati tugaguncha ≤ 15 daqiqa)."""
    p = decode_token(token) or {}
    if p.get("sid"):
        sessions.revoke(db, user.id, jti=p["sid"])
    audit.log(db, user_id=user.id, action="auth.logout", target_type="user", target_id=user.id)
    db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@router.post("/auth/logout-all", status_code=204)
def logout_all(user: CurrentUser, db: DB, response: Response):
    """Barcha qurilmalardan chiqish: sessiyalar bekor + token versiyasi oshadi (access tokenlar ham darhol yaroqsiz)."""
    n = sessions.revoke_all(db, user.id, reason="logout_all")
    audit.log(db, user_id=user.id, action="auth.logout_all", target_type="user", target_id=user.id, detail={"sessions": n})
    db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


class SessionOut(BaseModel):
    id: int
    client: str
    ip: str
    user_agent: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool = False

    model_config = {"from_attributes": True}


@router.get("/auth/sessions", response_model=list[SessionOut])
def list_sessions(user: CurrentUser, db: DB, token: Annotated[str, Depends(oauth2_scheme)]):
    sid = (decode_token(token) or {}).get("sid")
    now = datetime.now(timezone.utc)
    out = []
    for row in db.query(UserSession).filter_by(user_id=user.id, revoked_at=None).order_by(UserSession.last_used_at.desc()).all():
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if exp <= now:
            continue
        o = SessionOut.model_validate(row)
        o.current = row.jti == sid
        out.append(o)
    return out


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_session(session_id: int, user: CurrentUser, db: DB):
    if not sessions.revoke(db, user.id, session_id=session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessiya topilmadi")
    audit.log(db, user_id=user.id, action="auth.session_revoked", target_type="user", target_id=user.id, detail={"session_id": session_id})
    db.commit()


class WsTicket(BaseModel):
    ticket: str
    expires_in: int = 60


@router.post("/auth/ws-ticket", response_model=WsTicket)
def ws_ticket(user: CurrentUser):
    """WebSocket uchun 60 s li bir maqsadli chipta (L2): sessiya tokeni URL/loglarga tushmaydi."""
    return WsTicket(ticket=create_access_token(user.id, minutes=1, scope="ws", ver=user.token_version))


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


@router.post("/auth/change-password", response_model=Token)
def change_password(body: PasswordChange, user: CurrentUser, db: DB, request: Request, response: Response):
    """Parolni almashtirish: siyosat tekshiruvi (422), barcha mavjud sessiyalar bekor (token versiyasi
    oshadi), joriy klientga yangi token juftligi qaytadi."""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eski parol noto'g'ri")
    _check_policy(body.new_password, user.username)
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Yangi parol eskisi bilan bir xil")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    n = sessions.revoke_all(db, user.id, reason="password_change")
    audit.log(
        db, user_id=user.id, action="auth.password_changed", target_type="user", target_id=user.id, detail={"sessions_revoked": n}
    )
    out = _issue(db, response, user, request, "web")
    db.commit()
    return out


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
    _check_policy(body.password, body.username)
    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        must_change_password=body.must_change_password,
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
    revoke_reason = ""
    if body.password is not None:
        _check_policy(body.password, user.username)
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
        user.password_changed_at = datetime.now(timezone.utc)
        revoke_reason = "password_reset"
    if body.is_admin is not None:
        if user.id == admin.id and not body.is_admin:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "O'zingizdan admin huquqini ololmaysiz"
            )
        if user.is_admin != body.is_admin:
            revoke_reason = "role_change"
        user.is_admin = body.is_admin
    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "O'zingizni o'chira olmaysiz")
        if user.is_active and not body.is_active:
            revoke_reason = "deactivated"
        user.is_active = body.is_active
    if revoke_reason:
        sessions.revoke_all(db, user.id, reason=revoke_reason)  # L2: huquq o'zgardi — barcha sessiyalar bekor
    if body.mfa_reset:
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_last_counter = None
        sessions.revoke_all(db, user.id, reason="mfa_reset")
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
