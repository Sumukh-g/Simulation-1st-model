"""Authentication and RBAC helpers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
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


async def _is_member(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    """True if the user has an active membership in the org.

    This is the authorization gate for org-scoped access: without it a caller
    could pass an arbitrary X-Org-Id and read/write another org's data (IDOR).
    """
    result = await db.execute(
        select(models.Membership.id).where(
            models.Membership.user_id == user_id,
            models.Membership.org_id == org_id,
            models.Membership.status == "active",
        )
    )
    return result.scalar_one_or_none() is not None


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


async def _resolve_demo_user(db: AsyncSession) -> tuple[models.User, uuid.UUID]:
    """Load the seeded demo user + org when GSIP_DEMO_AUTH is enabled."""
    user_result = await db.execute(
        select(models.User).where(models.User.email == settings.DEMO_USER_EMAIL)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Demo auth enabled but seed user not found. "
                "Run: python scripts/seed_data.py"
            ),
        )

    org_result = await db.execute(
        select(models.Org).where(models.Org.slug == settings.DEMO_ORG_SLUG)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo org not found. Run: python scripts/seed_data.py",
        )
    return user, org.id


async def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    # EventSource cannot set headers; allow demo query params for SSE.
    user_id: str | None = None,
    org_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    """Resolve current user and permissions from headers (or demo fallback)."""
    header_user = x_user_id or user_id
    header_org = x_org_id or org_id

    if not header_user:
        if not settings.GSIP_DEMO_AUTH:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-User-Id header required",
            )
        user, demo_org_id = await _resolve_demo_user(db)
        permissions = await _load_permissions(db, user.id, demo_org_id)
        return UserContext(user=user, org_id=demo_org_id, permissions=permissions)

    try:
        resolved_user_id = uuid.UUID(header_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user id"
        ) from exc

    user = await db.get(models.User, resolved_user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user"
        )

    org_uuid = None
    permissions: set[str] = set()
    if header_org:
        try:
            org_uuid = uuid.UUID(header_org)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org id"
            ) from exc
        if not await _is_member(db, resolved_user_id, org_uuid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of the requested organization",
            )
        permissions = await _load_permissions(db, resolved_user_id, org_uuid)
    elif settings.GSIP_DEMO_AUTH:
        _, demo_org_id = await _resolve_demo_user(db)
        org_uuid = demo_org_id
        permissions = await _load_permissions(db, resolved_user_id, org_uuid)

    return UserContext(user=user, org_id=org_uuid, permissions=permissions)


def require_permission(permission: str):
    """Dependency to enforce RBAC permission."""

    async def _checker(context: UserContext = Depends(get_current_user)) -> UserContext:
        if permission in context.permissions or "admin:all" in context.permissions:
            return context
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return _checker
