"""
app/schemas/auth.py
───────────────────────────────────────────────────────────────────────────────
Pydantic schemas for authentication: login, tokens, and user representations
exchanged with the /auth/* endpoints.

Changes from previous version
──────────────────────────────
• UserCreate          — kept for admin-only user creation via /users; role can
                        be 'admin' or 'viewer' (admin sets it explicitly).
• ViewerRegisterRequest — NEW public self-registration schema.  Role is NOT a
                          field; the endpoint always hard-codes role=VIEWER so
                          no caller can escalate to admin via the public API.
• ChangePasswordRequest — NEW schema used by the viewer's "change password" UI.

Role system: ADMIN and VIEWER only.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.user import UserRole


# ═══════════════════════════════════════════════════════════════════════════════
# Requests
# ═══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    """Credentials submitted to POST /auth/login."""
    username: str = Field(..., min_length=1, examples=["admin"])
    password: str = Field(..., min_length=1, examples=["StrongP@ssw0rd"])


class RefreshTokenRequest(BaseModel):
    """Body for POST /auth/refresh."""
    refresh_token: str


class UserCreate(BaseModel):
    """
    Payload for POST /users (admin-only user creation).

    `password` is plaintext on input; the service layer hashes it via
    app.core.security.hash_password before persisting.
    Role is explicitly set by the admin; defaults to VIEWER when omitted.
    """
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr | None = None
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.VIEWER


class ViewerRegisterRequest(BaseModel):
    """
    Payload for POST /auth/register (public, self-registration by viewer).

    Step 1 of the viewer registration flow:
        Full Name, Student Code, Email, Username, Password, Confirm Password,
        Department.

    The `role` field is intentionally absent — the endpoint always creates
    a VIEWER account. This cannot be overridden by any client payload.

    Face capture happens in Step 2 (POST /students/{id}/capture/frame) after
    this endpoint creates the User + Student records and returns a token.
    """
    full_name:        str      = Field(..., min_length=1, max_length=150,  examples=["Alice Smith"])
    student_code:     str      = Field(..., min_length=1, max_length=50,   examples=["CS-2024-001"])
    email:            EmailStr = Field(...,                                 examples=["alice@example.com"])
    username:         str      = Field(..., min_length=3, max_length=50,   examples=["alice_smith"])
    password:         str      = Field(..., min_length=6,                  examples=["S3cur3Pass!"])
    confirm_password: str      = Field(..., min_length=6,                  examples=["S3cur3Pass!"])
    department:       str | None = Field(default=None, max_length=100,     examples=["Computer Science"])

    @model_validator(mode="after")
    def passwords_must_match(self) -> "ViewerRegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match.")
        return self


class ChangePasswordRequest(BaseModel):
    """
    Payload for POST /auth/change-password.

    Used by the viewer's "Change Password" UI on the viewer dashboard.
    The current_password is verified before the new one is stored.
    """
    current_password:     str = Field(..., min_length=1)
    new_password:         str = Field(..., min_length=6)
    confirm_new_password: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def new_passwords_must_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("new_password and confirm_new_password do not match.")
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# Responses
# ═══════════════════════════════════════════════════════════════════════════════

class TokenResponse(BaseModel):
    """Response for POST /auth/login and POST /auth/refresh."""
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class ViewerRegisterResponse(BaseModel):
    """
    Response for POST /auth/register.

    Returns tokens (viewer is auto-logged-in) plus the newly created IDs so
    the frontend can immediately start the face-capture step without a
    separate /auth/me call.
    """
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    user_id:       int
    student_id:    int


class UserRead(BaseModel):
    """
    Public representation of a user account.

    Returned by GET /auth/me and admin user-management endpoints.
    Excludes `hashed_password`.
    """
    model_config = ConfigDict(from_attributes=True)

    id:         int
    username:   str
    email:      EmailStr | None = None
    role:       UserRole
    is_active:  bool
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime
