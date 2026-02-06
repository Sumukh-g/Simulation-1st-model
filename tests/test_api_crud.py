"""Integration tests for API CRUD, RBAC, and audit events."""
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from testcontainers.postgres import PostgresContainer
from sqlalchemy import select


async def _get_or_create(session, model, defaults=None, **kwargs):
    result = await session.execute(
        select(model).where(*[getattr(model, key) == value for key, value in kwargs.items()])
    )
    instance = result.scalar_one_or_none()
    if instance:
        return instance, False
    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    await session.flush()
    return instance, True


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(postgres_container):
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
    os.environ["DATABASE_URL"] = async_url
    return async_url


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(database_url):
    config = Config("services/api/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture
async def api_client(database_url):
    from services.api.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def seeded_admin(database_url):
    from services.api.db import models
    from services.api.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        org = models.Org(name="Test Org", slug=f"org-{uuid.uuid4()}")
        session.add(org)
        await session.flush()

        role = models.Role(name=f"admin-{uuid.uuid4()}", description="Admin")
        session.add(role)
        await session.flush()

        permission, _ = await _get_or_create(
            session,
            models.Permission,
            name="admin:all",
            defaults={"description": "All access"},
        )

        session.add(models.RolePermission(role_id=role.id, permission_id=permission.id))

        user = models.User(email=f"admin-{uuid.uuid4()}@example.com", name="Admin")
        session.add(user)
        await session.flush()

        session.add(models.Membership(org_id=org.id, user_id=user.id, role_id=role.id))
        await session.commit()

        return {"org_id": org.id, "user_id": user.id}


@pytest.fixture
async def seeded_viewer(database_url):
    from services.api.db import models
    from services.api.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        org = models.Org(name="Viewer Org", slug=f"org-{uuid.uuid4()}")
        session.add(org)
        await session.flush()

        role = models.Role(name=f"viewer-{uuid.uuid4()}", description="Viewer")
        user = models.User(email=f"viewer-{uuid.uuid4()}@example.com", name="Viewer")
        session.add_all([role, user])
        await session.flush()

        session.add(models.Membership(org_id=org.id, user_id=user.id, role_id=role.id))
        await session.commit()

        return {"org_id": org.id, "user_id": user.id}


@pytest.mark.asyncio
async def test_admin_crud_emits_audit(api_client, seeded_admin):
    headers = {
        "X-User-Id": str(seeded_admin["user_id"]),
        "X-Org-Id": str(seeded_admin["org_id"]),
    }
    payload = {"name": "Project Alpha", "description": "Test project"}
    create = await api_client.post("/admin/projects", json=payload, headers=headers)
    assert create.status_code == 200
    data = create.json()
    assert data["name"] == "Project Alpha"
    assert data["org_id"] == str(seeded_admin["org_id"])

    audits = await api_client.get("/admin/audit_events", headers=headers)
    assert audits.status_code == 200
    entries = audits.json()
    assert any(entry["entity_type"] == "projects" for entry in entries)


@pytest.mark.asyncio
async def test_rbac_forbidden(api_client, seeded_viewer):
    headers = {
        "X-User-Id": str(seeded_viewer["user_id"]),
        "X-Org-Id": str(seeded_viewer["org_id"]),
    }
    response = await api_client.get("/admin/projects", headers=headers)
    assert response.status_code == 403
