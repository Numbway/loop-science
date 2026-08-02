"""Unified project and experiment management API."""

from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.user import User
from app.schemas.project_dashboard import (
    ProjectDashboardItem,
    ProjectDashboardResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=ProjectDashboardResponse)
async def list_user_projects(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ProjectDashboardResponse:
    """Return every project owned by the current user with experiment counts."""
    projects = (
        await db.scalars(
            select(Project)
            .where(Project.user_id == current_user.id)
            .order_by(Project.updated_at.desc(), Project.created_at.desc())
        )
    ).all()
    if not projects:
        return ProjectDashboardResponse()

    project_ids = [project.id for project in projects]
    experiments = (
        await db.scalars(
            select(Experiment)
            .where(Experiment.project_id.in_(project_ids))
            .order_by(Experiment.created_at.desc())
        )
    ).all()
    by_project: dict[object, list[Experiment]] = defaultdict(list)
    for experiment in experiments:
        by_project[experiment.project_id].append(experiment)

    items: list[ProjectDashboardItem] = []
    for project in projects:
        project_experiments = by_project[project.id]
        latest = project_experiments[0] if project_experiments else None
        preparation = dict(project.preparation_config or {})
        workflow = (
            "existing_assets"
            if preparation.get("workflow") == "existing_assets"
            else "paper_reproduction"
        )
        data = preparation.get("data") or {}
        execution = preparation.get("execution") or {}
        code = preparation.get("code") or {}
        items.append(
            ProjectDashboardItem(
                id=project.id,
                name=project.name,
                workflow=workflow,
                status=project.status,
                paper_title=project.paper_title,
                created_at=project.created_at,
                updated_at=(
                    latest.created_at
                    if latest and latest.created_at > project.updated_at
                    else project.updated_at
                ),
                experiment_count=len(project_experiments),
                experiment_status_counts=dict(
                    Counter(
                        experiment.status for experiment in project_experiments
                    )
                ),
                latest_experiment_id=latest.id if latest else None,
                latest_experiment_status=latest.status if latest else None,
                latest_metrics=dict(latest.metrics or {}) if latest else {},
                data_name=str(data.get("selected_name") or "") or None,
                remote_host=str(execution.get("host") or "") or None,
                code_entrypoint=str(code.get("entrypoint") or "") or None,
            )
        )
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return ProjectDashboardResponse(projects=items)
