"""
app/schemas/user.py
───────────────────────────────────────────────────────────────────────────────
Pydantic v2 request/response schemas for the /api/v1/users CRUD endpoints.

Kept deliberately separate from app/schemas/auth.py (which owns LoginRequest,
TokenResponse, and the UserCreate / UserRead used by the /auth/* router) so
that the auth flow is never disturbed by changes here.

Schemas defined here:
  UserCreateRequest  — POST /users body (username, email, password, role)
  UserUpdateRequest  — PATCH /users/{id} body (all fields optional)
  UserResponse       — shape of a single user in list / detail responses
  UserListResponse   — paginated { items, total } list response

Role system: ADMIN and VIEWER only.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


# ── Request schemas ───────────────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """
    Body for POST /api/v1/users.

    `password` is the plaintext password; the service layer hashes it before
    persisting. `role` defaults to VIEWER when omitted.
    """

    username: str = Field(..., min_length=1, max_length=50, examples=["johndoe"])
    email: Optional[EmailStr] = Field(default=None, examples=["john@example.com"])
    password: str = Field(..., min_length=6, examples=["supersecret"])
    role: UserRole = Field(default=UserRole.VIEWER)


class UserUpdateRequest(BaseModel):
    """
    Body for PATCH /api/v1/users/{id}.

    Every field is optional so callers can send only the fields they want to
    change. `password`, when present, is treated as plaintext and hashed by
    the service layer; omitting it leaves the existing hash unchanged.
    """

    username: Optional[str] = Field(default=None, min_length=1, max_length=50)
    email: Optional[EmailStr] = Field(default=None)
    password: Optional[str] = Field(default=None, min_length=6)
    role: Optional[UserRole] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)


# ── Response schemas ──────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """
    Single user representation returned by list / create / update endpoints.

    Field names intentionally match the column names on the User ORM model so
    that Pydantic's `model_validate(user, from_attributes=True)` works without
    any field aliasing.

    `created_at` is exposed so the frontend table can display the join date.
    `hashed_password` is deliberately excluded.
    """

    id: int
    username: str
    email: Optional[str] = None
    role: UserRole
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """
    Paginated response for GET /api/v1/users.

    Shape expected by UsersPage.jsx:
        { "items": [...], "total": <int> }
    """

    items: list[UserResponse]
    total: int
