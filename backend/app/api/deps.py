"""
app/api/deps.py
───────────────────────────────────────────────────────────────────────────────
Shared FastAPI dependencies: JWT token extraction, current-user resolution,
and role-based access guards.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_async_session
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """
    Validate Bearer JWT and return the corresponding User row.

    Raises HTTP 401 for invalid/expired tokens; HTTP 403 if the account
    is inactive.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(credentials.credentials)
    except JWTError:
        raise credentials_exception

    if claims.get("type") != "access":
        raise credentials_exception

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise credentials_exception

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled.",
        )
    return user


def require_role(*roles: UserRole) -> Callable:
    """
    Dependency factory: requires the current user to have one of the given
    roles, raising HTTP 403 otherwise.

    Usage:
        @router.delete("/...", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in roles]}.",
            )
        return current_user

    return _check
