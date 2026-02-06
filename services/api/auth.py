"""Authentication and RBAC helpers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import models
from .db.database import get_db


@dataclass
class UserContext:
    user: models.User
    org_id: uuid.UUID | None
    permissions: set[str]

    async def get_projects(self, session: AsyncSession) -> list[models.Project]:
        """Return projects for the current org."""
        if self.org_id is None:
            return []
        result = await session.execute(
            select(models.Project).where(models.Project.org_id == self.org_id)
        )
        return list(result.scalars().all())


async def _load_permissions(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
) -> set[str]:
    query = (
        select(models.Permission.name)
        .join(models.RolePermission, models.Permission.id == models.RolePermission.permission_id)
        .join(models.Role, models.Role.id == models.RolePermission.role_id)
        .join(models.Membership, models.Membership.role_id == models.Role.id)
        .where(models.Membership.user_id == user_id)
        .where(models.Membership.org_id == org_id)
    )
    result = await db.execute(query)
    return {row[0] for row in result.fetchall()}


async def get_current_user(
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    """Resolve current user and permissions from headers."""
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user id") from exc

    user = await db.get(models.User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    org_id = None
    permissions: set[str] = set()
    if x_org_id:
        try:
            org_id = uuid.UUID(x_org_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org id"
            ) from exc
        permissions = await _load_permissions(db, user_id, org_id)

    return UserContext(user=user, org_id=org_id, permissions=permissions)


def require_permission(permission: str):
    """Dependency to enforce RBAC permission."""

    async def _checker(context: UserContext = Depends(get_current_user)) -> UserContext:
        if permission in context.permissions or "admin:all" in context.permissions:
            return context
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return _checker
