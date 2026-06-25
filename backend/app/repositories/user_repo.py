"""
app/repositories/user_repo.py
───────────────────────────────────────────────────────────────────────────────
Repository for User CRUD operations.

Provides the data-access layer used by:
  • app/api/v1/auth.py  — login, register, refresh
  • app/api/deps.py     — get_current_user JWT resolution

Follows the same async/session pattern as AttendanceRepository and
StudentRepository: every method receives no session at call-time — the
session is injected at construction and kept for the lifetime of a single
request (unit-of-work pattern). Commits are left to the caller.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.user import User, UserRole

log = get_logger(__name__)


class UserRepository:
    """Data-access layer for the `users` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: int) -> User | None:
        """Fetch a User by primary key. Returns None if not found."""
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        """
        Fetch a User by username (case-sensitive).

        Used by the login flow and duplicate-username guard in registration.
        """
        stmt = select(User).where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """
        Fetch a User by email address (case-sensitive).

        Used by the duplicate-email guard in registration.
        """
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[User]:
        """
        List users with optional active-status filter and pagination.

        Args:
            is_active: If provided, filter to active (True) or inactive
                       (False) accounts only.
            skip:      Rows to skip (for offset pagination).
            limit:     Maximum rows to return.
        """
        stmt = select(User)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        stmt = stmt.order_by(User.id).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count(self, *, is_active: bool | None = None) -> int:
        """Count users, optionally filtered by active status."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(User)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # ── Write ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        username: str,
        email: str,
        hashed_password: str,
        role: UserRole = UserRole.VIEWER,
        is_active: bool = True,
    ) -> User:
        """
        Insert a new User row and flush to populate the auto-generated id.

        The caller is responsible for committing the transaction.
        `hashed_password` must already be the bcrypt hash — pass the result
        of `app.core.security.hash_password(plain_password)`.
        """
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            role=role,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.flush()
        log.info(
            "User created",
            extra={"ctx_user_id": user.id, "ctx_username": username, "ctx_role": role.value},
        )
        return user

    async def update(self, user: User, **kwargs) -> User:
        """
        Apply arbitrary field updates to a User instance and flush.

        Accepted kwargs match User column names:
            username, email, hashed_password, role, is_active, last_login,
            student_id

        `student_id` is the nullable FK that links a VIEWER account to its
        Student record. It is written once during POST /auth/register
        immediately after the Student row is created, and never changed
        afterward.

        Example:
            await repo.update(user, last_login=datetime.now(timezone.utc))
            await repo.update(user, role=UserRole.ADMIN, is_active=False)
            await repo.update(user, student_id=student.id)
        """
        _allowed_fields = {
            "username",
            "email",
            "hashed_password",
            "role",
            "is_active",
            "last_login",
            "student_id",   # nullable FK to students.id; set during viewer self-registration
        }
        for field, value in kwargs.items():
            if field not in _allowed_fields:
                raise ValueError(
                    f"UserRepository.update: unknown field {field!r}. "
                    f"Allowed: {_allowed_fields}"
                )
            setattr(user, field, value)

        await self._session.flush()
        log.info(
            "User updated",
            extra={"ctx_user_id": user.id, "ctx_fields": list(kwargs.keys())},
        )
        return user

    async def deactivate(self, user: User) -> User:
        """
        Soft-disable a user account (set is_active=False).

        Inactive users are rejected by `get_current_user` and cannot log in.
        """
        return await self.update(user, is_active=False)

    async def delete(self, user: User) -> None:
        """
        Hard-delete a user row. Prefer `deactivate` for audit-trail safety.

        The caller is responsible for committing the transaction.
        """
        await self._session.delete(user)
        await self._session.flush()
        log.warning("User hard-deleted", extra={"ctx_user_id": user.id})
