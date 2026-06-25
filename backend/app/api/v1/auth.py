"""
app/api/v1/auth.py
───────────────────────────────────────────────────────────────────────────────
Authentication endpoints: login, token refresh, current-user, viewer
self-registration, and password change.

Changes from previous version
──────────────────────────────
• POST /auth/register — after creating both User and Student, now writes
  user.student_id = student.id so that the viewer→student FK link is
  persisted in the database.  This is the single source of truth that
  GET /students/me and all ownership-gated capture endpoints rely on.
  No other behavioural change.

• POST /auth/change-password — unchanged.
• GET  /auth/me            — unchanged.
• POST /auth/login         — unchanged.
• POST /auth/refresh       — unchanged.

Login behaviour (enforced at the frontend via the role in the JWT claims):
  • role == 'admin'  → redirect to /dashboard
  • role == 'viewer' → redirect to /viewer
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_async_session
from app.models.user import User, UserRole
from app.repositories.student_repo import StudentRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRead,
    ViewerRegisterRequest,
    ViewerRegisterResponse,
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """
    Authenticate with username + password; receive access and refresh tokens.

    The `role` claim embedded in the access token is used by the frontend
    to redirect the user to the correct dashboard:
      admin  → /dashboard
      viewer → /viewer
    """
    repo = UserRepository(session)
    user = await repo.get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled.",
        )

    # Update last_login timestamp
    await repo.update(user, last_login=datetime.now(timezone.utc))
    await session.commit()

    extra = {"role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(str(user.id), extra_claims=extra),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ── Token Refresh ──────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    from jose import JWTError

    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token.",
        )

    user_id: str = claims["sub"]
    repo = UserRepository(session)
    user = await repo.get_by_id(int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    extra = {"role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(user_id, extra_claims=extra),
        refresh_token=create_refresh_token(user_id),
    )


# ── Current User ───────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user


# ── Public Viewer Self-Registration ───────────────────────────────────────────

@router.post(
    "/register",
    response_model=ViewerRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_viewer(
    payload: ViewerRegisterRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ViewerRegisterResponse:
    """
    Public self-registration endpoint for viewers (students).

    Step 1 of the viewer registration flow:
      1. Validate uniqueness of username, email, and student_code.
      2. Create User(role=VIEWER) — role is ALWAYS forced to VIEWER here,
         regardless of any client input (the schema has no role field).
      3. Create the linked Student record.
      4. Write user.student_id = student.id — this is the canonical FK link
         between the auth account and the student profile. It is the only
         field used by GET /students/me and ownership checks on capture
         endpoints. username and student_code remain independent free-text
         fields and are never compared against each other.
      5. Issue tokens so the frontend auto-logs the user in and can
         immediately proceed to Step 2 (face capture).

    Admin accounts CANNOT be created via this endpoint. Admins are created
    manually in the database or via the admin-only POST /api/v1/users endpoint.

    Returns:
        access_token, refresh_token, user_id, student_id
    """
    user_repo    = UserRepository(session)
    student_repo = StudentRepository(session)

    # ── Uniqueness guards ──────────────────────────────────────────────────

    if await user_repo.get_by_username(payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken.",
        )

    if await user_repo.get_by_email(str(payload.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered.",
        )

    if await student_repo.get_by_code(payload.student_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Student code '{payload.student_code}' is already registered.",
        )

    # ── Create User (role hard-coded to VIEWER — never escalatable) ────────

    user = await user_repo.create(
        username=payload.username,
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        role=UserRole.VIEWER,      # ← always VIEWER, not from payload
    )

    # ── Create linked Student record ───────────────────────────────────────

    student = await student_repo.create(
        name=payload.full_name,
        student_code=payload.student_code,
        email=str(payload.email),
        department=payload.department,
    )

    # ── Persist the FK link: user.student_id → student.id ─────────────────
    #
    # This is the authoritative join column.  GET /students/me resolves the
    # student via current_user.student_id — never via username/student_code
    # comparison.  Ownership guards on capture endpoints do the same.
    await user_repo.update(user, student_id=student.id)

    await session.commit()
    await session.refresh(user)
    await session.refresh(student)

    # ── Auto-login: issue tokens immediately ───────────────────────────────

    extra = {"role": user.role.value}
    return ViewerRegisterResponse(
        access_token=create_access_token(str(user.id), extra_claims=extra),
        refresh_token=create_refresh_token(str(user.id)),
        user_id=user.id,
        student_id=student.id,
    )


# ── Change Password (any authenticated user) ───────────────────────────────────

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Change the authenticated user's own password.

    Available to both admins and viewers. The current password is verified
    before the new one is stored. Returns 204 No Content on success.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    repo = UserRepository(session)
    await repo.update(current_user, hashed_password=hash_password(payload.new_password))
    await session.commit()
