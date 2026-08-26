"""Authorization tests for the org-membership gate in get_current_user.

These lock in the IDOR fix: supplying an X-Org-Id you are not a member of must
be rejected rather than silently granting org-scoped access.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.api.auth import get_current_user


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Minimal async session: `get` returns a user, `execute` pops a queue."""

    def __init__(self, *, user, execute_results):
        self._user = user
        self._results = list(execute_results)

    async def get(self, _model, _pk):
        return self._user

    async def execute(self, _stmt):
        if not self._results:
            return _FakeResult()
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_rejects_org_without_membership():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    active_user = SimpleNamespace(id=user_id, is_active=True)
    # First execute() is the membership check -> no row -> not a member.
    session = _FakeSession(user=active_user, execute_results=[_FakeResult(scalar=None)])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            x_user_id=str(user_id),
            x_org_id=str(org_id),
            user_id=None,
            org_id=None,
            db=session,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_allows_org_with_active_membership():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    active_user = SimpleNamespace(id=user_id, is_active=True)
    session = _FakeSession(
        user=active_user,
        execute_results=[
            _FakeResult(scalar=uuid.uuid4()),      # membership present
            _FakeResult(rows=[("runs:read",)]),    # permissions
        ],
    )

    ctx = await get_current_user(
        x_user_id=str(user_id),
        x_org_id=str(org_id),
        user_id=None,
        org_id=None,
        db=session,
    )
    assert ctx.org_id == org_id
    assert "runs:read" in ctx.permissions


@pytest.mark.asyncio
async def test_invalid_org_id_is_rejected():
    user_id = uuid.uuid4()
    active_user = SimpleNamespace(id=user_id, is_active=True)
    session = _FakeSession(user=active_user, execute_results=[])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            x_user_id=str(user_id),
            x_org_id="not-a-uuid",
            user_id=None,
            org_id=None,
            db=session,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_inactive_user_is_rejected():
    user_id = uuid.uuid4()
    inactive_user = SimpleNamespace(id=user_id, is_active=False)
    session = _FakeSession(user=inactive_user, execute_results=[])

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            x_user_id=str(user_id),
            x_org_id=str(uuid.uuid4()),
            user_id=None,
            org_id=None,
            db=session,
        )
    assert exc.value.status_code == 401
