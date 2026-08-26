"""Database models for GSIP."""
from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class Org(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "orgs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255))


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255))


class RolePermission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False
    )

    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)


class Membership(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "memberships"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="active")

    __table_args__ = (UniqueConstraint("org_id", "user_id"),)


class AuditEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class ProjectSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, unique=True
    )
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Dataset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "datasets"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class DatasetVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dataset_versions"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    is_immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (UniqueConstraint("dataset_id", "version"),)


class DatasetAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dataset_assets"

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(128))


class Run(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "runs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id")
    )
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dataset_versions.id")
    )
    domain_pack_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_pack_versions.id")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    run_spec: Mapped[dict | None] = mapped_column(JSONB)
    seed_policy: Mapped[str | None] = mapped_column(String(255))

    @classmethod
    async def get_by_id_and_org(
        cls, session: AsyncSession, run_id: uuid.UUID, org_id: uuid.UUID
    ) -> Run | None:
        result = await session.execute(
            select(cls).where(cls.id == run_id, cls.org_id == org_id)
        )
        return result.scalars().first()

    @classmethod
    async def list_for_org(
        cls,
        session: AsyncSession,
        org_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        q = select(cls).where(cls.org_id == org_id)
        if project_id is not None:
            q = q.where(cls.project_id == project_id)
        if not include_archived:
            q = q.where(cls.status != "archived")
        q = q.order_by(cls.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        return list(result.scalars().all())


class RunStage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "run_stages"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Scenario(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    scenario_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    input_state: Mapped[dict | None] = mapped_column(JSONB)
    actions: Mapped[dict | None] = mapped_column(JSONB)
    fidelity: Mapped[str | None] = mapped_column(String(50))
    seed: Mapped[int | None] = mapped_column(Integer)


class ScenarioInstance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scenario_instances"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    instance_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("scenario_id", "instance_index"),)


class SimulationJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "simulation_jobs"

    scenario_instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_instances.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="queued")
    worker_id: Mapped[str | None] = mapped_column(String(255))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetricResult(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "metric_results"

    scenario_instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenario_instances.id"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))


class UncertaintyResult(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "uncertainty_results"

    scenario_instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenario_instances.id"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    p50: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    p95: Mapped[float | None] = mapped_column(Float)


class Artifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    scenario_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenario_instances.id")
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String(100))
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)


class OptimizerStep(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "optimizer_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("run_id", "step_index"),)


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_type: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(128))


class DocChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "doc_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)


class EmbeddingsMeta(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "embeddings_meta"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("doc_chunks.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(255), nullable=False)


class EvidencePack(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "evidence_packs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class EvidencePackItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "evidence_pack_items"

    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence_packs.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id")
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("doc_chunks.id")
    )
    relevance_score: Mapped[float | None] = mapped_column(Float)


class BenchmarkSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "benchmark_sources"

    org_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id"))
    domain_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_packs.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512))
    citation: Mapped[str | None] = mapped_column(Text)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Benchmark(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "benchmarks"

    domain_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_packs.id")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("benchmark_sources.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="approved")

    @classmethod
    async def get_all_approved_for_domain_pack(
        cls, session: AsyncSession, domain_pack_name: str
    ) -> list[Benchmark]:
        pack = await DomainPack.get_by_name(session, domain_pack_name)
        if not pack:
            return []
        result = await session.execute(
            select(cls).where(
                cls.domain_pack_id == pack.id,
                cls.status == "approved",
            )
        )
        return list(result.scalars().all())


class Rubric(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rubrics"

    org_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id"))
    domain_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_packs.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class RubricVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rubric_versions"

    rubric_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="draft")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )

    __table_args__ = (UniqueConstraint("rubric_id", "version"),)


class RubricWeight(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rubric_weights"

    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rubric_versions.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    aggregation_method: Mapped[str | None] = mapped_column(String(50))
    constraint_penalties: Mapped[dict | None] = mapped_column(JSONB)
    feasibility_weight: Mapped[float | None] = mapped_column(Float)
    confidence_penalty_rate: Mapped[float | None] = mapped_column(Float)


class JudgeScore(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "judge_scores"

    run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runs.id"))
    scenario_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenario_instances.id")
    )
    rubric_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rubric_versions.id")
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)


class JudgeBreakdown(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "judge_breakdowns"

    judge_score_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("judge_scores.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    contribution: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSONB)


class DomainPack(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "domain_packs"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    @classmethod
    async def get_by_name(cls, session: AsyncSession, name: str) -> DomainPack | None:
        """Look up a domain pack by registry name (e.g. toy-pack)."""
        result = await session.execute(select(cls).where(cls.name == name))
        return result.scalars().first()


class DomainPackVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "domain_pack_versions"

    domain_pack_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_packs.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    pack_hash: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="active")

    __table_args__ = (UniqueConstraint("domain_pack_id", "version"),)

    @classmethod
    async def get_latest_approved_version(
        cls, session: AsyncSession, domain_pack_id: uuid.UUID
    ) -> DomainPackVersion | None:
        result = await session.execute(
            select(cls)
            .where(
                cls.domain_pack_id == domain_pack_id,
                cls.status.in_(["active", "approved"]),
            )
            .order_by(cls.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()


class PackCertification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pack_certifications"

    domain_pack_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("domain_pack_versions.id"), nullable=False
    )
    certified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Model(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


class ModelVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"

    model_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("models.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("model_id", "version"),)


class RouterPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "router_policies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    policy: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PromptVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prompt_versions"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (UniqueConstraint("name", "version"),)
