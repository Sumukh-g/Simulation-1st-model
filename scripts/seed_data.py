#!/usr/bin/env python3
"""Load seed data into the database."""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.api.db.database import AsyncSessionLocal  # noqa: E402
from services.api.db import models  # noqa: E402


async def get_or_create(session, model, defaults=None, **kwargs):
    stmt = select(model).filter_by(**kwargs)
    result = await session.execute(stmt)
    instance = result.scalar_one_or_none()
    if instance:
        return instance, False
    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    await session.flush()
    return instance, True


async def load_domain_packs(session, admin_user_id):
    seed_file = Path(__file__).parent.parent / "seed" / "domain_packs.json"
    with open(seed_file) as f:
        packs = json.load(f)

    created = 0
    for pack in packs:
        domain_pack, _ = await get_or_create(
            session,
            models.DomainPack,
            name=pack["name"],
            defaults={"description": pack.get("description")},
        )
        version, created_version = await get_or_create(
            session,
            models.DomainPackVersion,
            domain_pack_id=domain_pack.id,
            version=pack["version"],
            defaults={"pack_hash": pack.get("id"), "status": pack.get("status", "active")},
        )
        if pack.get("is_certified") and created_version:
            session.add(
                models.PackCertification(
                    domain_pack_version_id=version.id,
                    certified_by_user_id=admin_user_id,
                    status="certified",
                    notes="Seed certification",
                )
            )
        created += 1
    return created


async def load_rubrics(session, org_id, admin_user_id, domain_pack_map):
    created = 0

    generic_rubric, _ = await get_or_create(
        session,
        models.Rubric,
        org_id=org_id,
        name="Generic Impact/Cost/Feasibility/Confidence",
        defaults={
            "description": "Template rubric for general evaluations across domains."
        },
    )
    generic_version, _ = await get_or_create(
        session,
        models.RubricVersion,
        rubric_id=generic_rubric.id,
        version="1.0",
        defaults={"status": "approved", "created_by_user_id": admin_user_id},
    )
    weights = {
        "impact": 0.35,
        "cost": 0.25,
        "feasibility": 0.25,
        "confidence": 0.15,
    }
    for metric, weight in weights.items():
        await get_or_create(
            session,
            models.RubricWeight,
            rubric_version_id=generic_version.id,
            metric_name=metric,
            defaults={
                "weight": weight,
                "aggregation_method": "weighted_sum",
                "feasibility_weight": 1.0,
                "confidence_penalty_rate": 0.1,
            },
        )
    created += 1

    domain_rubrics = [
        ("SpatialPack Standard", "spatial-pack"),
        ("FinancePack Standard", "finance-pack"),
    ]
    for name, pack_key in domain_rubrics:
        pack_id = domain_pack_map.get(pack_key)
        rubric, _ = await get_or_create(
            session,
            models.Rubric,
            org_id=org_id,
            domain_pack_id=pack_id,
            name=name,
            defaults={"description": f"Approved rubric for {pack_key}"},
        )
        await get_or_create(
            session,
            models.RubricVersion,
            rubric_id=rubric.id,
            version="1.0",
            defaults={"status": "approved", "created_by_user_id": admin_user_id},
        )
        created += 1

    return created


async def load_benchmarks(session, org_id, domain_pack_map):
    created = 0
    now = datetime.now(timezone.utc)

    spatial_source, _ = await get_or_create(
        session,
        models.BenchmarkSource,
        org_id=org_id,
        domain_pack_id=domain_pack_map.get("spatial-pack"),
        name="SpatialPack Environmental Guidelines 2024",
        defaults={
            "url": "https://example.org/spatial-guidelines",
            "citation": "Environmental Guidelines 2024",
            "accessed_at": now,
        },
    )

    finance_source, _ = await get_or_create(
        session,
        models.BenchmarkSource,
        org_id=org_id,
        domain_pack_id=domain_pack_map.get("finance-pack"),
        name="FinancePack Risk Benchmarks 2024",
        defaults={
            "url": "https://example.org/finance-benchmarks",
            "citation": "Risk Benchmarks 2024",
            "accessed_at": now,
        },
    )

    spatial_benchmarks = [
        ("Minimum Safe Area Coverage", "safe_area_ratio", 0.8, "min"),
        ("Critical Area Limit", "critical_area_ratio", 0.05, "max"),
    ]
    for name, metric, value, threshold_type in spatial_benchmarks:
        await get_or_create(
            session,
            models.Benchmark,
            domain_pack_id=domain_pack_map.get("spatial-pack"),
            source_id=spatial_source.id,
            name=name,
            metric_name=metric,
            threshold_value=value,
            threshold_type=threshold_type,
            defaults={"metadata_": {"domain": "SpatialPack"}, "status": "approved"},
        )
        created += 1

    finance_benchmarks = [
        ("Minimum Sharpe Ratio", "sharpe_ratio", 0.5, "min"),
        ("Maximum Drawdown Limit", "max_drawdown", 0.2, "max"),
    ]
    for name, metric, value, threshold_type in finance_benchmarks:
        await get_or_create(
            session,
            models.Benchmark,
            domain_pack_id=domain_pack_map.get("finance-pack"),
            source_id=finance_source.id,
            name=name,
            metric_name=metric,
            threshold_value=value,
            threshold_type=threshold_type,
            defaults={"metadata_": {"domain": "FinancePack"}, "status": "approved"},
        )
        created += 1

    return created


async def main():
    print("=" * 50)
    print("GSIP Seed Data Loader")
    print("=" * 50)

    async with AsyncSessionLocal() as session:
        org, _ = await get_or_create(
            session,
            models.Org,
            slug="gsip-demo",
            defaults={"name": "GSIP Demo Org"},
        )
        admin_role, _ = await get_or_create(
            session,
            models.Role,
            name="admin",
            defaults={"description": "Full access"},
        )
        admin_permission, _ = await get_or_create(
            session,
            models.Permission,
            name="admin:all",
            defaults={"description": "Administrator full access"},
        )
        await get_or_create(
            session,
            models.RolePermission,
            role_id=admin_role.id,
            permission_id=admin_permission.id,
        )
        admin_user, _ = await get_or_create(
            session,
            models.User,
            email="admin@gsip.local",
            defaults={"name": "GSIP Admin", "hashed_password": "change-me"},
        )
        await get_or_create(
            session,
            models.Membership,
            org_id=org.id,
            user_id=admin_user.id,
            defaults={"role_id": admin_role.id},
        )

        project, _ = await get_or_create(
            session,
            models.Project,
            org_id=org.id,
            name="Demo Project",
            defaults={"description": "Default project for local GSIP demos"},
        )

        packs_created = await load_domain_packs(session, admin_user.id)
        domain_pack_map = {}
        result = await session.execute(select(models.DomainPack))
        for pack in result.scalars().all():
            domain_pack_map[pack.name] = pack.id

        rubrics_created = await load_rubrics(session, org.id, admin_user.id, domain_pack_map)
        benchmarks_created = await load_benchmarks(session, org.id, domain_pack_map)

        await session.commit()

    print()
    print("=" * 50)
    print(
        "Loaded: "
        f"{packs_created} domain packs, {rubrics_created} rubrics, "
        f"{benchmarks_created} benchmarks, project={project.name}"
    )
    print(f"Demo X-User-Id: {admin_user.id}")
    print(f"Demo X-Org-Id:  {org.id}")
    print(f"Demo project:   {project.id}")
    print("Pack names:     toy-pack | finance-pack | spatial-pack")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
