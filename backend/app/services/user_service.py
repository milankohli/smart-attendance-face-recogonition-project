"""
app/services/user_service.py
───────────────────────────────────────────────────────────────────────────────
Business-logic layer for user management.

Sits between the /api/v1/users router and UserRepository, handling:
  • duplicate-username / duplicate-email guards
  • password hashing (delegates to app.core.security)
  • search filtering (username / email substring match)
  • role filtering (admin | viewer)
  • self-deletion prevention
  • pagination

All methods raise fastapi.HTTPException directly so the router can stay thin.
The session is passed in from the FastAPI dependency; commits are left to the
router (unit-of-work pattern).
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreateRequest, UserListResponse, UserResponse, UserUpdateRequest

log = get_logger(__name__)


class UserService:
    """Orchestrates user CRUD operations on top of UserRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    # ── List ──────────────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        role: str | None = None,
    ) -> UserListResponse:
        """
        Return a paginated, optionally filtered list of users.

        `search` performs a case-insensitive substring match on both
        username and email (OR semantics, matching UsersPage.jsx behaviour).
        `role` is an exact match against the UserRole enum value string
        ('admin' or 'viewer').
        """
        # Build the base statement with optional filters
        stmt_base = select(User)

        if search:
            pattern = f"%{search.lower()}%"
            stmt_base = stmt_base.where(
                or_(
                    func.lower(User.username).like(pattern),
                    func.lower(User.email).like(pattern),
                )
            )

        if role:
            # Validate that the role string maps to a known enum member;
            # return empty results rather than a 400 for an unknown role.
            try:
                role_enum = UserRole(role)
                stmt_base = stmt_base.where(User.role == role_enum)
            except ValueError:
                # Unknown role — no users can match; short-circuit.
                return UserListResponse(items=[], total=0)

        # Count matching rows for the total field
        count_stmt = select(func.count()).select_from(stmt_base.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        # Fetch the requested page
        offset = (page - 1) * page_size
        list_stmt = stmt_base.order_by(User.id).offset(offset).limit(page_size)
        list_result = await self._session.execute(list_stmt)
        users = list_result.scalars().all()

        return UserListResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
        )

    # ── Create ────────────────────────────────────────────────────────────

    async def create_user(self, payload: UserCreateRequest) -> UserResponse:
        """
        Create a new user account.

        Raises HTTP 409 if the username or email is already taken.
        `payload.password` is hashed before persisting.
        """
        if await self._repo.get_by_username(payload.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{payload.username}' already exists.",
            )

        if payload.email and await self._repo.get_by_email(str(payload.email)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{payload.email}' already exists.",
            )

        user = await self._repo.create(
            username=payload.username,
            email=str(payload.email) if payload.email else None,
            hashed_password=hash_password(payload.password),
            role=payload.role,
        )
        return UserResponse.model_validate(user)

    # ── Update ────────────────────────────────────────────────────────────

    async def update_user(self, user_id: int, payload: UserUpdateRequest) -> UserResponse:
        """
        Partially update a user account.

        Raises HTTP 404 if the user does not exist.
        Raises HTTP 409 on username / email collision with another account.
        `payload.password`, when provided, is hashed before persisting.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )

        update_kwargs: dict = {}

        if payload.username is not None:
            existing = await self._repo.get_by_username(payload.username)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Username '{payload.username}' already exists.",
                )
            update_kwargs["username"] = payload.username

        if payload.email is not None:
            existing = await self._repo.get_by_email(str(payload.email))
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email '{payload.email}' already exists.",
                )
            update_kwargs["email"] = str(payload.email)

        if payload.password is not None:
            update_kwargs["hashed_password"] = hash_password(payload.password)

        if payload.role is not None:
            update_kwargs["role"] = payload.role

        if payload.is_active is not None:
            update_kwargs["is_active"] = payload.is_active

        if update_kwargs:
            user = await self._repo.update(user, **update_kwargs)

        return UserResponse.model_validate(user)

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_user(self, user_id: int, *, current_user_id: int) -> None:
        """
        Hard-delete a user account.

        Raises HTTP 404 if the user does not exist.
        Raises HTTP 403 if the caller tries to delete their own account,
        preventing accidental admin lock-out.
        """
        if user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete your own account.",
            )

        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )

        await self._repo.delete(user)
        log.info(
            "User deleted via management API",
            extra={"ctx_user_id": user_id, "ctx_deleted_by": current_user_id},
        )
