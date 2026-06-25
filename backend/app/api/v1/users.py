"""
app/api/v1/users.py
───────────────────────────────────────────────────────────────────────────────
User management endpoints (admin-only).

Endpoints:
  GET    /users            — paginated list with search and role filter
  POST   /users            — create a new user
  PATCH  /users/{user_id}  — partial update of an existing user
  DELETE /users/{user_id}  — hard-delete a user (self-deletion blocked)

All four routes require the caller to be authenticated with the ADMIN role,
enforced via the existing `require_role` dependency from app.api.deps.

Router prefix is set here as /users; the parent api_router (app/api/v1/router.py)
already carries the /api/v1 prefix, so the full paths become /api/v1/users/*.
This matches the paths used by UsersPage.jsx:
  api.get("/users", ...)
  api.post("/users", ...)
  api.patch(`/users/${id}`, ...)
  api.delete(`/users/${id}`)

Roles in this system: ADMIN and VIEWER only.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_async_session
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])

# Dependency alias: every route in this router requires ADMIN.
_admin_only = Depends(require_role(UserRole.ADMIN))


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=UserListResponse, dependencies=[_admin_only])
async def list_users(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(default=20, ge=1, le=200, description="Items per page"),
    search: str | None = Query(default=None, description="Substring match on username or email"),
    role: str | None = Query(default=None, description="Exact role filter (admin, viewer)"),
    session: AsyncSession = Depends(get_async_session),
) -> UserListResponse:
    """
    Return a paginated list of users.

    Supports:
    - `page` / `page_size` for offset pagination
    - `search` for case-insensitive username or email substring match
    - `role` for exact role filtering ('admin' or 'viewer')

    Response shape: `{ "items": [...], "total": <int> }`
    """
    service = UserService(session)
    return await service.list_users(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
    )


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, dependencies=[_admin_only])
async def create_user(
    payload: UserCreateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> UserResponse:
    """
    Create a new user account.

    - `password` is hashed before storage; never returned in any response.
    - `role` must be 'admin' or 'viewer'.
    - Returns HTTP 409 if `username` or `email` is already in use.
    """
    service = UserService(session)
    user_response = await service.create_user(payload)
    await session.commit()
    return user_response


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{user_id}", response_model=UserResponse, dependencies=[_admin_only])
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> UserResponse:
    """
    Partially update a user account.

    All body fields are optional — send only what you want to change.
    If `password` is included it is treated as plaintext and hashed before
    storage; omitting it leaves the existing password unchanged.

    Returns HTTP 404 if the user does not exist.
    Returns HTTP 409 on username / email collision.
    """
    service = UserService(session)
    user_response = await service.update_user(user_id, payload)
    await session.commit()
    return user_response


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[])
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Hard-delete a user account.

    Returns HTTP 403 if the caller attempts to delete their own account.
    Returns HTTP 404 if the user does not exist.
    Returns HTTP 204 (No Content) on success.
    """
    service = UserService(session)
    await service.delete_user(user_id, current_user_id=current_user.id)
    await session.commit()
