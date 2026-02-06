"""Generic admin CRUD endpoints with RBAC and audit events."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, get_current_user
from ..db import Base, models
from ..db.database import get_db

router = APIRouter()


RESOURCE_REGISTRY: dict[str, type[Base]] = {
    "orgs": models.Org,
    "users": models.User,
    "memberships": models.Membership,
    "roles": models.Role,
    "permissions": models.Permission,
    "role_permissions": models.RolePermission,
    "audit_events": models.AuditEvent,
    "projects": models.Project,
    "project_settings": models.ProjectSettings,
    "datasets": models.Dataset,
    "dataset_versions": models.DatasetVersion,
    "dataset_assets": models.DatasetAsset,
    "runs": models.Run,
    "run_stages": models.RunStage,
    "scenarios": models.Scenario,
    "scenario_instances": models.ScenarioInstance,
    "simulation_jobs": models.SimulationJob,
    "metric_results": models.MetricResult,
    "uncertainty_results": models.UncertaintyResult,
    "artifacts": models.Artifact,
    "optimizer_steps": models.OptimizerStep,
    "documents": models.Document,
    "doc_chunks": models.DocChunk,
    "embeddings_meta": models.EmbeddingsMeta,
    "evidence_packs": models.EvidencePack,
    "evidence_pack_items": models.EvidencePackItem,
    "benchmark_sources": models.BenchmarkSource,
    "benchmarks": models.Benchmark,
    "rubrics": models.Rubric,
    "rubric_versions": models.RubricVersion,
    "rubric_weights": models.RubricWeight,
    "judge_scores": models.JudgeScore,
    "judge_breakdowns": models.JudgeBreakdown,
    "domain_packs": models.DomainPack,
    "domain_pack_versions": models.DomainPackVersion,
    "pack_certifications": models.PackCertification,
    "models": models.Model,
    "model_versions": models.ModelVersion,
    "router_policies": models.RouterPolicy,
    "prompt_versions": models.PromptVersion,
}


def _get_model(resource: str) -> type[Base]:
    model = RESOURCE_REGISTRY.get(resource)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource")
    return model


def _column_names(model: type[Base]) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _filter_payload(model: type[Base], payload: dict[str, Any]) -> dict[str, Any]:
    allowed = _column_names(model) - {"id", "created_at", "updated_at"}
    return {key: value for key, value in payload.items() if key in allowed}


def _is_org_scoped(model: type[Base]) -> bool:
    return "org_id" in _column_names(model)


def _require_resource_permission(action: str):
    async def _checker(
        resource: str,
        context: UserContext = Depends(get_current_user),
    ) -> UserContext:
        permission = f"{resource}:{action}"
        if permission in context.permissions or "admin:all" in context.permissions:
            return context
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return _checker


async def _record_audit_event(
    db: AsyncSession,
    context: UserContext,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    audit = models.AuditEvent(
        org_id=context.org_id,
        actor_user_id=context.user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
    )
    db.add(audit)


def _apply_org_scope(
    stmt,
    model: type[Base],
    context: UserContext,
):
    if _is_org_scoped(model):
        if not context.org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Org-Id header"
            )
        stmt = stmt.where(model.org_id == context.org_id)
    return stmt


@router.get("/{resource}")
async def list_resources(
    resource: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    context: UserContext = Depends(_require_resource_permission("read")),
    db: AsyncSession = Depends(get_db),
):
    model = _get_model(resource)
    stmt = select(model)
    stmt = _apply_org_scope(stmt, model, context)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [row.to_dict() for row in result.scalars().all()]


@router.get("/{resource}/{resource_id}")
async def get_resource(
    resource: str,
    resource_id: uuid.UUID,
    context: UserContext = Depends(_require_resource_permission("read")),
    db: AsyncSession = Depends(get_db),
):
    model = _get_model(resource)
    stmt = select(model).where(model.id == resource_id)
    stmt = _apply_org_scope(stmt, model, context)
    result = await db.execute(stmt)
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return instance.to_dict()


@router.post("/{resource}")
async def create_resource(
    resource: str,
    payload: dict[str, Any] = Body(...),
    context: UserContext = Depends(_require_resource_permission("write")),
    db: AsyncSession = Depends(get_db),
):
    model = _get_model(resource)
    data = _filter_payload(model, payload)
    if _is_org_scoped(model):
        if not context.org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Org-Id header"
            )
        data["org_id"] = context.org_id
    instance = model(**data)
    db.add(instance)
    await db.flush()
    await _record_audit_event(
        db,
        context,
        resource,
        instance.id,
        "create",
        before=None,
        after=instance.to_dict(),
    )
    await db.commit()
    await db.refresh(instance)
    return instance.to_dict()


@router.patch("/{resource}/{resource_id}")
async def update_resource(
    resource: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    context: UserContext = Depends(_require_resource_permission("write")),
    db: AsyncSession = Depends(get_db),
):
    model = _get_model(resource)
    stmt = select(model).where(model.id == resource_id)
    stmt = _apply_org_scope(stmt, model, context)
    result = await db.execute(stmt)
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    before = instance.to_dict()
    updates = _filter_payload(model, payload)
    if _is_org_scoped(model):
        updates.pop("org_id", None)
    for key, value in updates.items():
        setattr(instance, key, value)
    await db.flush()
    await _record_audit_event(
        db,
        context,
        resource,
        instance.id,
        "update",
        before=before,
        after=instance.to_dict(),
    )
    await db.commit()
    await db.refresh(instance)
    return instance.to_dict()


@router.delete("/{resource}/{resource_id}")
async def delete_resource(
    resource: str,
    resource_id: uuid.UUID,
    context: UserContext = Depends(_require_resource_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    model = _get_model(resource)
    stmt = select(model).where(model.id == resource_id)
    stmt = _apply_org_scope(stmt, model, context)
    result = await db.execute(stmt)
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    before = instance.to_dict()
    await db.delete(instance)
    await db.flush()
    await _record_audit_event(
        db,
        context,
        resource,
        resource_id,
        "delete",
        before=before,
        after=None,
    )
    await db.commit()
    return {"status": "deleted", "id": str(resource_id)}
