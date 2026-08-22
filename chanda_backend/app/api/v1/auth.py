from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jose import JWTError

from app.db.session import get_db
from app.core.security import (
    hash_password, verify_password, create_token, decode_token, generate_reset_token,
)
from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.models import User, PasswordResetToken
from app.schemas.auth import (
    SignupIn, LoginIn, TokenOut, UserOut, RefreshIn,
    ForgotPasswordIn, ResetPasswordIn, UserRoleUpdate,
)
from typing import List
from app.services.audit import log_login, log_activity
from app.services.email_service import send_password_reset_email
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])

VALID_ROLES = {"admin", "store_manager", "purchase", "production", "management", "quality"}
# Public /auth/signup can only create these — "admin" is deliberately excluded.
# Admin accounts are created only via seed_admin.py or by an existing admin.
SIGNUP_ALLOWED_ROLES = VALID_ROLES - {"admin"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=UserOut, status_code=201)
@limiter.limit("20/minute")
def signup(
    request: Request,
    payload: SignupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """
    Point 6 (security upgrade): this is NO LONGER a public self-registration page.
    Only an authenticated admin can create employee accounts, and the admin
    explicitly picks the correct role for each employee -- nobody can grant
    themselves elevated access anymore.
    """
    if payload.role not in SIGNUP_ALLOWED_ROLES | {"admin"}:
        raise HTTPException(400, f"role must be one of {SIGNUP_ALLOWED_ROLES | {'admin'}}")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(409, "Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        department=payload.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_activity(db, current_user.id, f"Created employee account '{user.username}' with role '{user.role.value}'", "auth")
    return user


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    """Admin-only: see every employee account that has been created, with role/status."""
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Admin-only: change an employee's role or activate/deactivate their login."""
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if payload.role is not None:
        if payload.role not in SIGNUP_ALLOWED_ROLES | {"admin"}:
            raise HTTPException(400, f"role must be one of {SIGNUP_ALLOWED_ROLES | {'admin'}}")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    log_activity(db, current_user.id, f"Updated user '{user.username}' (role={user.role.value}, active={user.is_active})", "auth")
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """
    Point 2: Admin-only, permanent delete (not just disable).

    Only actually possible when the account has no history (no purchases,
    issues, requests, approvals, etc. tied to it) -- the database itself
    enforces this via foreign keys, so it's impossible to silently orphan
    old records. If the user has any history, we return a clear 409 instead
    of a confusing database error, and the admin should use Disable instead.
    """
    if user_id == current_user.id:
        raise HTTPException(400, "You cannot delete your own account")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    username = user.username
    try:
        db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            f"'{username}' has existing history (purchases, issues, requests, or approvals) "
            f"and can't be permanently deleted without losing that record. Use Disable instead "
            f"to block their login while keeping the history intact.",
        )
    log_activity(db, current_user.id, f"Deleted user '{username}'", "auth")
    return None


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2-form login (username + password) so the standard Swagger 'Authorize' button works.
    Rate-limited to 10 attempts/minute per IP to blunt brute-force/credential-stuffing."""
    user = db.query(User).filter(User.username == form.username).first()
    ip = _client_ip(request)

    if not user or not verify_password(form.password, user.password_hash):
        log_login(db, user.id if user else None, form.username, False, ip, request.headers.get("user-agent"))
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been disabled. Contact admin.")

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    log_login(db, user.id, form.username, True, ip, request.headers.get("user-agent"))
    log_activity(db, user.id, "Logged in", "auth", ip)

    access = create_token(user.id, user.role.value, "access")
    refresh = create_token(user.id, user.role.value, "refresh")
    return TokenOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenOut)
def refresh_token(payload: RefreshIn, db: Session = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(401, "Not a refresh token")
    except JWTError:
        raise HTTPException(401, "Invalid or expired refresh token")

    user = db.query(User).filter(User.id == int(data["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or disabled")

    access = create_token(user.id, user.role.value, "access")
    new_refresh = create_token(user.id, user.role.value, "refresh")
    return TokenOut(access_token=access, refresh_token=new_refresh, user=UserOut.model_validate(user))


@router.post("/forgot-password", status_code=202)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Always return 202 regardless of whether the email exists, to avoid leaking
    # which emails are registered.
    if user:
        token = generate_reset_token()
        expires = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        db.add(PasswordResetToken(user_id=user.id, token=token, expires_at=expires))
        db.commit()
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        send_password_reset_email(user.email, reset_link)
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == payload.token, PasswordResetToken.used == False)  # noqa: E712
        .first()
    )
    if not row or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset link is invalid or has expired")

    user = db.query(User).filter(User.id == row.user_id).first()
    user.password_hash = hash_password(payload.new_password)
    row.used = True
    db.commit()
    return {"message": "Password has been reset. You can now log in."}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
